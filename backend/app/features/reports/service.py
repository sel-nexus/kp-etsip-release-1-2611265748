"""Reuse scoped inventory services for paginated reports and CSV exports."""
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from app.core.access import require_permission
from app.features.applications.service import ApplicationService
from app.features.portfolios.service import PortfolioService
from app.features.audit.repository import AuditRepository
from app.features.audit.schemas import AuditEvent
from app.features.auth.schemas import Session
from app.features.reports.csv_export import csv_line
from app.features.reports.schemas import APPLICATION_COLUMNS, PORTFOLIO_COLUMNS, ReportKind


class ReportService:
    """Apply inventory visibility and export guards without widening scope."""
    def __init__(self, applications: ApplicationService, portfolios: PortfolioService, audit: AuditRepository) -> None:
        """Bind the existing lifespan-owned services and audit repository."""
        self.applications = applications
        self.portfolios = portfolios
        self.audit = audit

    async def listing(self, actor: Session, kind: ReportKind, filters: dict, page: int, page_size: int):
        """Return the corresponding inventory page under its existing view guard."""
        if kind == "applications":
            return await self.applications.listing(actor, page=page, page_size=page_size, **filters)
        return await self.portfolios.listing(actor, page=page, page_size=page_size, **filters)

    async def export(self, actor: Session, kind: ReportKind, filters: dict) -> AsyncIterator[str]:
        """Validate permissions and filters before returning a bounded streaming iterator."""
        resource = "application" if kind == "applications" else "portfolio"
        require_permission(actor, "view", resource)
        require_permission(actor, "export", resource)
        first = await self.listing(actor, kind, filters, 1, 100)

        async def rows() -> AsyncIterator[str]:
            """Audit once at stream start, then emit every matching inventory row."""
            now = datetime.now(UTC)
            await self.audit.append(AuditEvent(timestamp=now, userId=actor.user.id, userName=actor.user.name,
                action="export", entityType=resource, entityId=None,
                details=f"{resource.title()} report export succeeded", createdAt=now, updatedAt=now))
            columns = APPLICATION_COLUMNS if kind == "applications" else PORTFOLIO_COLUMNS
            yield csv_line(columns)
            result = first
            page = 1
            while True:
                for item in result.items:
                    yield csv_line([getattr(item, field) for field in columns])
                if not result.items or page * 100 >= result.total:
                    break
                page += 1
                result = await self.listing(actor, kind, filters, page, 100)
        return rows()
