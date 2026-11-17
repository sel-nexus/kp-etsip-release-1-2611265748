"""Expose the application and portfolio report endpoints."""
from typing import Annotated
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from app.core.access import get_business_session
from app.core.errors import DomainError
from app.core.pagination import Page, Pagination
from app.features.auth.schemas import Session
from app.features.applications.schemas import Application, Criticality, Lifecycle, RiskLevel
from app.features.portfolios.schemas import Portfolio, PortfolioStatus
from app.features.reports.service import ReportService

router = APIRouter(prefix="/api/reports", tags=["Reports"])
Business = Annotated[Session, Depends(get_business_session)]
Paging = Annotated[Pagination, Depends()]


def get_service(request: Request) -> ReportService:
    """Return the lifespan-owned report service."""
    return request.app.state.reports


Service = Annotated[ReportService, Depends(get_service)]


def check_format(value: str) -> None:
    """Reject unsupported representations rather than silently defaulting."""
    if value not in ("json", "csv"):
        raise DomainError(400, "Unsupported report format")


@router.get("/applications", response_model=Page[Application])
async def applications(session: Business, service: Service, paging: Paging,
    search: Annotated[str, Query(max_length=200)] = "",
    portfolioId: Annotated[str | None, Query(pattern=r"^[0-9a-fA-F]{24}$")] = None,
    criticality: Criticality | None = None, riskLevel: RiskLevel | None = None,
    lifecycleStatus: Lifecycle | None = None, format: str = "json"):
    """List or export visible applications with all inventory filters."""
    check_format(format)
    filters = dict(search=search, portfolio_id=portfolioId, criticality=criticality, risk=riskLevel, lifecycle=lifecycleStatus)
    if format == "csv":
        stream = await service.export(session, "applications", filters)
        return StreamingResponse(stream, media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="applications.csv"'})
    return await service.listing(session, "applications", filters, paging.page, paging.pageSize)


@router.get("/portfolios", response_model=Page[Portfolio])
async def portfolios(session: Business, service: Service, paging: Paging,
    search: Annotated[str, Query(max_length=200)] = "", status: PortfolioStatus | None = None,
    productArea: Annotated[str | None, Query(max_length=200)] = None, format: str = "json"):
    """List or export visible portfolios with derived inventory metrics."""
    check_format(format)
    filters = dict(search=search, status=status, product_area=productArea)
    if format == "csv":
        stream = await service.export(session, "portfolios", filters)
        return StreamingResponse(stream, media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="portfolios.csv"'})
    return await service.listing(session, "portfolios", filters, paging.page, paging.pageSize)
