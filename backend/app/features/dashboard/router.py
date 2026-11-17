"""Expose scoped executive inventory insight."""
from typing import Annotated
from fastapi import APIRouter, Depends, Query, Request
from app.core.access import get_business_session
from app.features.applications.schemas import RiskLevel
from app.features.auth.schemas import Session
from app.features.dashboard.schemas import ExecutiveDashboard
from app.features.dashboard.service import DashboardService

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])
Business = Annotated[Session, Depends(get_business_session)]


def get_service(request: Request) -> DashboardService:
    """Retrieve the service owned by the current lifespan."""
    return request.app.state.dashboard


@router.get("/executive", response_model=ExecutiveDashboard, summary="Summarize visible inventory")
async def executive(session: Business, service: Annotated[DashboardService, Depends(get_service)],
                    portfolioId: Annotated[str | None, Query(pattern=r"^[0-9a-fA-F]{24}$")] = None,
                    productArea: Annotated[str | None, Query(min_length=1, max_length=2000)] = None,
                    riskLevel: RiskLevel | None = None) -> ExecutiveDashboard:
    """Return exact metrics for authorized matching inventory."""
    return await service.executive(session, portfolioId, productArea, riskLevel)
