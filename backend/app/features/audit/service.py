"""Write login events from fixed summaries, never submitted credentials."""
from datetime import UTC, datetime
import csv
import io
from bson import ObjectId

from app.core.errors import DomainError
from app.core.pagination import Page
from app.features.audit.repository import AuditRepository
from app.features.audit.schemas import AuditEvent, AuditRecord


class AuditService:
    """Construct identity-safe login events before appending them."""
    def __init__(self, repository: AuditRepository) -> None:
        """Bind the real append-only repository."""
        self.repository = repository

    async def login(self, user_id: str | None, user_name: str | None, success: bool, session=None) -> None:
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
        ), session=session)

    def query(self, actor, user_id, action, start, end):
        """Build literal filters, conservatively excluding unscoped historical events."""
        from app.core.access import portfolio_scope, require_permission
        require_permission(actor, "view", "audit")
        query = {}
        if user_id is not None:
            if not isinstance(user_id, str) or len(user_id) != 24 or not ObjectId.is_valid(user_id):
                raise DomainError(422, "Invalid user identifier")
            query["userId"] = ObjectId(user_id)
        if action:
            query["action"] = action
        if start and end and start > end:
            raise DomainError(422, "Start must not be after end")
        if start or end:
            query["timestamp"] = {}
            if start:
                query["timestamp"]["$gte"] = start
            if end:
                query["timestamp"]["$lte"] = end
        scope = portfolio_scope(actor)
        if scope is not None:
            # Legacy events lack historical portfolio references; don't infer them
            # from an application's current association after reassignment.
            query.update({"entityType": "portfolio", "entityId": {"$in": scope}})
        return query

    def project(self, row):
        """Construct an allowlisted response even if stored documents have extras."""
        return AuditRecord(id=row["_id"], **{field: row[field] for field in AuditEvent.model_fields})

    async def listing(self, actor, user_id, action, start, end, page, page_size):
        """Return a scoped page with stable pagination and filtered total."""
        if not 1 <= page <= 21474836 or not 1 <= page_size <= 100:
            raise DomainError(422, "Invalid pagination")
        rows, total = await self.repository.listing(self.query(actor, user_id, action, start, end), page, page_size)
        return Page[AuditRecord](items=[self.project(row) for row in rows], total=total, page=page, pageSize=page_size)

    async def export(self, actor, user_id, action, start, end):
        """Record the export before streaming all matching, visible events."""
        from app.core.access import require_permission
        require_permission(actor, "export", "audit")
        query = self.query(actor, user_id, action, start, end)
        now = datetime.now(UTC)
        event = AuditEvent(timestamp=now, userId=actor.user.id, userName=actor.user.name,
                           action="export", entityType="audit", entityId=None,
                           details="Audit export succeeded", createdAt=now, updatedAt=now)
        event_id = await self.repository.append(event)
        query["_id"] = {"$ne": ObjectId(event_id)}
        return self.csv_rows(query)

    async def csv_rows(self, query):
        """Stream escaped CSV records without loading the complete result into memory."""
        fields = ("timestamp", "userId", "userName", "action", "entityType", "entityId", "details")
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        writer.writerow(fields)
        yield buffer.getvalue()
        async for row in self.repository.cursor(query):
            record = self.project(row)
            buffer.seek(0)
            buffer.truncate(0)
            writer.writerow([csv_safe(getattr(record, field)) for field in fields])
            yield buffer.getvalue()


def csv_safe(value):
    """Neutralize spreadsheet formula and control-character prefixes."""
    text = "" if value is None else value.isoformat() if isinstance(value, datetime) else str(value)
    if text and (text[0] in "\t\r\n" or text.lstrip().startswith(("=", "+", "-", "@"))):
        return "'" + text
    return text
