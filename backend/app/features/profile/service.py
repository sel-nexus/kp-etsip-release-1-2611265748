"""Persist self-service profile edits and atomically rotate credentials."""
from datetime import UTC, datetime
from app.core.errors import DomainError
from app.core.security import hash_password, verify_password
from app.features.audit.repository import AuditRepository
from app.features.audit.schemas import AuditEvent
from app.features.auth.service import AuthService
from app.features.auth.schemas import PublicUser, Session
from app.features.profile.schemas import ChangePasswordRequest, ProfileRequest


class ProfileService:
    """Coordinate live identity writes with fixed credential-free audit events."""
    def __init__(self, auth: AuthService, audit: AuditRepository) -> None:
        """Reuse the real user repository and append-only audit repository."""
        self.auth = auth
        self.repository = auth.repository
        self.audit = audit

    async def record_edit(self, session: Session, details: str) -> None:
        """Append a fixed summary without passwords, hashes, tokens, or email."""
        now = datetime.now(UTC)
        await self.audit.append(AuditEvent(
            timestamp=now, userId=session.user.id, userName=session.user.name,
            action="edit", entityType="user", entityId=session.user.id,
            details=details, createdAt=now, updatedAt=now,
        ))

    async def update_profile(self, session: Session, payload: ProfileRequest) -> PublicUser:
        """Return persisted safe identity after a version-checked preference write."""
        updated = await self.repository.update_landing(
            session.user.id, session.token_version, payload.defaultLandingPage,
        )
        if updated is None:
            raise DomainError(401, "Invalid or expired session")
        identity = await self.auth.public_user(updated)
        await self.record_edit(session, "Landing preference updated")
        return identity

    async def change_password(self, session: Session, payload: ChangePasswordRequest) -> None:
        """Require current password and atomically revoke every earlier bearer.

        Raises:
            DomainError: For stale sessions, incorrect current credentials, or reuse.
        """
        user = await self.repository.by_id(session.user.id)
        if not user or user["status"] != "Active" or user["tokenVersion"] != session.token_version:
            raise DomainError(401, "Invalid or expired session")
        current = payload.currentPassword.get_secret_value()
        new = payload.newPassword.get_secret_value()
        if not await verify_password(current, user["passwordHash"]):
            raise DomainError(400, "Current password is incorrect")
        if current == new or await verify_password(new, user["passwordHash"]):
            raise DomainError(422, "New password must differ from current password")
        replacement = await hash_password(new)
        if not await self.repository.change_password(
            session.user.id, session.token_version, user["passwordHash"], replacement,
        ):
            raise DomainError(401, "Invalid or expired session")
        await self.record_edit(session, "Password changed; prior sessions revoked")
