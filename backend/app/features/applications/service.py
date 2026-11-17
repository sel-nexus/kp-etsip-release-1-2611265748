"""Enforce application visibility and project safe public records."""
from typing import Any
from datetime import UTC, datetime
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from app.core.transactions import transaction, touch_portfolio
from app.features.audit.repository import AuditRepository
from app.features.audit.schemas import AuditEvent
from app.core.access import portfolio_scope, require_permission
from app.core.errors import DomainError
from app.core.pagination import Page
from app.features.auth.schemas import Session
from app.features.applications.repository import ApplicationRepository
from app.features.applications.schemas import Application, ApplicationWrite


class ApplicationService:
    """Coordinate scoped application reads without exposing internal fields."""
    def __init__(self, repository: ApplicationRepository, audit: AuditRepository | None = None) -> None:
        """Bind real inventory and audit repositories."""
        self.repository = repository
        self.audit = audit or AuditRepository(repository.db)

    def identifier(self, value: str) -> ObjectId:
        """Reject malformed IDs for callers outside HTTP validation."""
        if not isinstance(value, str) or len(value) != 24 or not ObjectId.is_valid(value):
            raise DomainError(422, "Invalid identifier")
        return ObjectId(value)

    def project(self, row: dict[str, Any]) -> Application:
        """Return only the public schema and current portfolio name."""
        fields = {key: row[key] for key in Application.model_fields if key not in ("id", "portfolioName")}
        return Application(id=row["_id"], portfolioName=row["portfolio"]["name"], **fields)

    async def listing(self, session: Session, search: str = "", portfolio_id: str | None = None,
                      criticality: str | None = None, risk: str | None = None, lifecycle: str | None = None,
                      page: int = 1, page_size: int = 25) -> Page[Application]:
        """Filter visible applications and preserve the requested page envelope."""
        require_permission(session, "view", "application")
        if not 1 <= page <= 21474836 or not 1 <= page_size <= 100:
            raise DomainError(422, "Invalid pagination")
        portfolio = self.identifier(portfolio_id) if portfolio_id is not None else None
        query = self.repository.query(portfolio_scope(session), search.strip(), portfolio, criticality, risk, lifecycle)
        rows, total = await self.repository.listing(query, page, page_size)
        return Page(items=[self.project(row) for row in rows], total=total, page=page, pageSize=page_size)

    async def get(self, session: Session, identifier: str) -> Application:
        """Conceal missing and out-of-scope records behind the same 404."""
        require_permission(session, "view", "application")
        row = await self.repository.get(self.identifier(identifier), portfolio_scope(session))
        if row is None:
            raise DomainError(404, "Application not found")
        return self.project(row)

    async def mutate(self, actor: Session, payload: ApplicationWrite | None, identifier: str | None, action: str) -> Application | None:
        """Atomically enforce scope, update inventory, and append an audit event."""
        require_permission(actor, "view", "application")
        require_permission(actor, {"create": "create", "edit": "edit", "delete": "delete"}[action], "application")
        db = self.repository.db
        scope = portfolio_scope(actor)
        object_id = self.identifier(identifier) if identifier else ObjectId()

        async def work(session):
            """Serialize the target portfolio against deletion and apply the change."""
            previous = None
            if action != "create":
                query = {"_id": object_id}
                if scope is not None:
                    query["portfolioId"] = {"$in": scope}
                previous = await db.applications.find_one(query, session=session)
                if previous is None:
                    raise DomainError(404, "Application not found")
            now = datetime.now(UTC)
            if payload is not None:
                fields = payload.model_dump()
                fields["portfolioId"] = self.identifier(fields["portfolioId"])
                parent = await touch_portfolio(db, fields["portfolioId"], scope, session)
                if action == "create":
                    row = {**fields, "_id": object_id, "createdAt": now, "updatedAt": now}
                    await db.applications.insert_one(row, session=session)
                else:
                    row = {**previous, **fields, "updatedAt": now}
                    await db.applications.update_one({"_id": object_id}, {"$set": {**fields, "updatedAt": now}}, session=session)
                row["portfolio"] = parent
            else:
                await db.applications.delete_one({"_id": object_id}, session=session)
                row = None
            await self.audit.append(AuditEvent(timestamp=now, userId=actor.user.id, userName=actor.user.name,
                action=action, entityType="application", entityId=str(object_id), details=f"Application {action} succeeded",
                createdAt=now, updatedAt=now), session=session)
            return self.project(row) if row else None
        try:
            return await transaction(db, work)
        except DuplicateKeyError as exc:
            raise DomainError(409, "Application name already exists") from exc
