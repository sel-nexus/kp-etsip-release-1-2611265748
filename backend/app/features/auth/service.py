"""Establish audited local sessions and enforce live identity/version checks."""
from typing import Any
from app.core.config import Settings
from app.core.errors import DomainError
from app.core.security import create_token, decode_token, verify_password
from app.core.transactions import transaction
from app.features.audit.service import AuditService
from app.features.auth.repository import AuthRepository
from app.features.auth.schemas import LoginRequest, LoginResponse, PublicUser, Session


class AuthService:
    """Coordinate real identity persistence with credential-free audit writes."""
    def __init__(self, repository: AuthRepository, audit: AuditService, settings: Settings, dummy_hash: str) -> None:
        """Bind shared dependencies and a cost-matched unknown-user hash."""
        self.repository = repository
        self.audit = audit
        self.settings = settings
        self.dummy_hash = dummy_hash

    async def public_user(self, document: dict[str, Any]) -> PublicUser:
        """Project safe fields and re-read the current role permission record."""
        role = await self.repository.role(document["role"])
        if role is None:
            raise DomainError(401, "Invalid or expired session")
        fields = {name: document[name] for name in PublicUser.model_fields if name not in ("id", "permissions")}
        return PublicUser(id=str(document["_id"]), permissions=role["permissions"], **fields)

    async def login(self, credentials: LoginRequest) -> LoginResponse:
        """Audit every credential attempt and return persisted active identity.

        Raises:
            DomainError: When credentials, status, or role cannot establish a session.
        """
        user = await self.repository.by_email(credentials.email)
        valid = await verify_password(credentials.password.get_secret_value(), user["passwordHash"] if user else self.dummy_hash)
        user_id = str(user["_id"]) if user else None
        user_name = user["name"] if user else None
        if not user or not valid or user["status"] != "Active":
            await self.audit.login(user_id, user_name, False)
            raise DomainError(401, "Invalid email or password")
        role = await self.repository.role(user["role"])
        if role is None:
            await self.audit.login(user_id, user_name, False)
            raise DomainError(401, "Invalid email or password")
        async def work(tx):
            """Commit the successful login timestamp and its event together."""
            updated = await self.repository.mark_login(user_id, user["tokenVersion"], user["passwordHash"], session=tx)
            if updated is not None:
                await self.audit.login(user_id, user_name, True, session=tx)
            return updated
        updated = await transaction(self.repository.db, work)
        if updated is None:
            await self.audit.login(user_id, user_name, False)
            raise DomainError(401, "Invalid email or password")
        identity = await self.public_user(updated)

        token = create_token(user_id, identity.role, updated["tokenVersion"], self.settings)
        return LoginResponse(token=token, user=identity)

    async def authenticate(self, token: str) -> Session:
        """Reject expired/revoked/inactive sessions and use live role and access."""
        claims = decode_token(token, self.settings)
        user = await self.repository.by_id(claims.sub)
        if not user or user["status"] != "Active" or user["tokenVersion"] != claims.tokenVersion:
            raise DomainError(401, "Invalid or expired session")
        return Session(user=await self.public_user(user), token_version=user["tokenVersion"])

    async def logout(self, session: Session) -> None:
        """Revoke every prior bearer for this user, including concurrent logins."""
        if not await self.repository.revoke(session.user.id, session.token_version):
            raise DomainError(401, "Invalid or expired session")
