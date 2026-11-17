"""Enforce application visibility and project safe public records."""
from typing import Any
from bson import ObjectId
from app.core.access import portfolio_scope, require_permission
from app.core.errors import DomainError
from app.core.pagination import Page
from app.features.auth.schemas import Session
from app.features.applications.repository import ApplicationRepository
from app.features.applications.schemas import Application


class ApplicationService:
    """Coordinate scoped application reads without exposing internal fields."""
    def __init__(self, repository: ApplicationRepository) -> None:
        """Bind a real inventory repository."""
        self.repository = repository

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
