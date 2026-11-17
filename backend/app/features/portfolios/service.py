"""Enforce portfolio business gates and derive live inventory metrics."""
from decimal import Decimal, ROUND_HALF_UP
from datetime import UTC, datetime
from typing import Any, Literal
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from app.core.access import portfolio_scope, require_permission
from app.core.errors import DomainError
from app.core.pagination import Page
from app.features.auth.schemas import Session
from app.features.audit.repository import AuditRepository
from app.features.audit.schemas import AuditEvent
from app.features.portfolios.repository import PortfolioRepository
from app.features.portfolios.schemas import LinkedApplication, Portfolio, PortfolioWrite
from app.core.transactions import transaction, touch_portfolio


class PortfolioService:
    """Coordinate scoped persistence and successful-mutation audit events."""
    def __init__(self, repository: PortfolioRepository, audit: AuditRepository) -> None:
        """Bind real repositories owned by the current lifespan."""
        self.repository = repository
        self.audit = audit

    def identifier(self, value: str) -> ObjectId:
        """Reject malformed identifiers consistently for direct service callers."""
        if not ObjectId.is_valid(value):
            raise DomainError(422, "Invalid portfolio identifier")
        return ObjectId(value)

    async def project(self, documents: list[dict[str, Any]]) -> list[Portfolio]:
        """Compute half-up averages from integer sums, with null for empty portfolios."""
        metrics = await self.repository.metrics([row["_id"] for row in documents])
        result = []
        for row in documents:
            values = metrics.get(row["_id"], {"count": 0, "scoreSum": 0})
            count = values["count"]
            score = int((Decimal(values["scoreSum"]) / Decimal(count)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if count else None
            fields = {name: row[name] for name in PortfolioWrite.model_fields}
            result.append(Portfolio(id=row["_id"], **fields, createdAt=row["createdAt"], updatedAt=row["updatedAt"], applicationCount=count, qualityScore=score))
        return result

    async def visible(self, session: Session, identifier: str) -> dict[str, Any]:
        """Hide absent and invisible portfolios behind the same response."""
        require_permission(session, "view", "portfolio")
        row = await self.repository.get(self.identifier(identifier), portfolio_scope(session))
        if row is None:
            raise DomainError(404, "Portfolio not found")
        return row

    async def listing(self, session: Session, search: str = "", status: str | None = None, product_area: str | None = None,
                      page: int = 1, page_size: int = 25) -> Page[Portfolio]:
        """List only visible records with filtered totals and bounded pagination."""
        require_permission(session, "view", "portfolio")
        self.bounds(page, page_size)
        rows, total = await self.repository.listing(portfolio_scope(session), search.strip(), status, product_area, page, page_size)
        return Page(items=await self.project(rows), total=total, page=page, pageSize=page_size)

    def bounds(self, page: int, page_size: int) -> None:
        """Protect direct service use from invalid or overflowing offsets."""
        if not 1 <= page <= 21474836 or not 1 <= page_size <= 100:
            raise DomainError(422, "Invalid pagination")

    async def get(self, session: Session, identifier: str) -> Portfolio:
        """Return a visible portfolio with live metrics."""
        return (await self.project([await self.visible(session, identifier)]))[0]

    async def linked(self, session: Session, identifier: str, page: int = 1, page_size: int = 25) -> Page[LinkedApplication]:
        """Read linked applications only after proving parent visibility."""
        row = await self.visible(session, identifier)
        self.bounds(page, page_size)
        rows, total = await self.repository.linked(row["_id"], page, page_size)
        items = [LinkedApplication(id=value["_id"], **{key: value[key] for key in LinkedApplication.model_fields if key != "id"}) for value in rows]
        return Page(items=items, total=total, page=page, pageSize=page_size)

    async def event(self, session: Session, identifier: str, action: Literal["create", "edit", "delete"]) -> None:
        """Append fixed credential-free summaries after successful mutations."""
        now = datetime.now(UTC)
        await self.audit.append(AuditEvent(timestamp=now, userId=session.user.id, userName=session.user.name,
            action=action, entityType="portfolio", entityId=identifier, details=f"Portfolio {action} succeeded",
            createdAt=now, updatedAt=now))

    async def create(self, session: Session, payload: PortfolioWrite) -> Portfolio:
        """Allow only unrestricted Administrators to create a visible new portfolio.

        Notes:
            Restricted Administrators cannot create outside their explicit assignments.
        """
        require_permission(session, "view", "portfolio")
        require_permission(session, "create", "portfolio")
        if portfolio_scope(session) is not None:
            raise DomainError(403, "Cannot create outside assigned portfolio scope")
        try:
            row = await self.repository.create(payload.model_dump())
        except DuplicateKeyError as exc:
            raise DomainError(409, "Portfolio name already exists") from exc
        result = (await self.project([row]))[0]
        await self.event(session, result.id, "create")
        return result

    async def update(self, session: Session, identifier: str, payload: PortfolioWrite) -> Portfolio:
        """Allow Administrators or assigned Portfolio Leaders to edit visible records."""
        previous = await self.visible(session, identifier)
        require_permission(session, "edit", "portfolio")
        try:
            row = await self.repository.update(previous, portfolio_scope(session), payload.model_dump())
        except DuplicateKeyError as exc:
            raise DomainError(409, "Portfolio name already exists") from exc
        if row is None:
            await self.visible(session, identifier)
            raise DomainError(409, "Portfolio changed; reload before editing")
        result = (await self.project([row]))[0]
        await self.event(session, identifier, "edit")
        return result

    async def delete(self, session: Session, identifier: str) -> None:
        """Delete only an unreferenced portfolio in a retryable transaction."""
        previous = await self.visible(session, identifier)
        require_permission(session, "delete", "portfolio")
        db = self.repository.db
        async def work(tx):
            """Conflict with concurrent reference writers, then verify and delete."""
            await touch_portfolio(db, previous["_id"], portfolio_scope(session), tx)
            if await db.applications.find_one({"portfolioId": previous["_id"]}, session=tx):
                raise DomainError(409, "Portfolio has linked applications and cannot be deleted")
            if await db.users.find_one({"portfolioAccess": previous["_id"]}, session=tx):
                raise DomainError(409, "Portfolio has assigned users and cannot be deleted")
            await db.portfolios.delete_one({"_id": previous["_id"]}, session=tx)
            now = datetime.now(UTC)
            await self.audit.append(AuditEvent(timestamp=now, userId=session.user.id, userName=session.user.name,
                action="delete", entityType="portfolio", entityId=identifier, details="Portfolio delete succeeded",
                createdAt=now, updatedAt=now), session=tx)
        await transaction(db, work)
