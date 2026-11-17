"""Write login events from fixed summaries, never submitted credentials."""
from datetime import UTC, datetime
from app.features.audit.repository import AuditRepository
from app.features.audit.schemas import AuditEvent


class AuditService:
    """Construct identity-safe login events before appending them."""
    def __init__(self, repository: AuditRepository) -> None:
        """Bind the real append-only repository."""
        self.repository = repository

    async def login(self, user_id: str | None, user_name: str | None, success: bool) -> None:
        """Record known or unknown identity with no email, password, or token.

        Args:
            user_id: Resolved user ID, or None for an unknown account.
            user_name: Resolved display name, never submitted email.
            success: Whether credentials established an active session.
        """
        now = datetime.now(UTC)
        await self.repository.append(AuditEvent(
            timestamp=now, userId=user_id, userName=user_name or "Unknown user",
            action="login", entityType="user", entityId=user_id,
            details="Login succeeded" if success else "Login failed",
            createdAt=now, updatedAt=now,
        ))
