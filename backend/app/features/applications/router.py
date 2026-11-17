"""Expose read-only application inventory endpoints."""
from typing import Annotated
from fastapi import APIRouter, Depends, Path, Query, Request
from app.core.access import get_business_session
from app.core.pagination import Page, Pagination
from app.features.auth.schemas import Session
from app.features.applications.schemas import Application, Criticality, Lifecycle, RiskLevel
from app.features.applications.service import ApplicationService

router = APIRouter(prefix="/api/applications", tags=["Applications"])
Business = Annotated[Session, Depends(get_business_session)]
Identifier = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]


def get_service(request: Request) -> ApplicationService:
    """Retrieve the service attached to the current lifespan."""
    return request.app.state.applications


Service = Annotated[ApplicationService, Depends(get_service)]
Paging = Annotated[Pagination, Depends()]


@router.get("", response_model=Page[Application], summary="Search visible applications")
async def listing(session: Business, service: Service, paging: Paging,
                  search: Annotated[str, Query(max_length=200)] = "",
                  portfolioId: Annotated[str | None, Query(pattern=r"^[0-9a-fA-F]{24}$")] = None,
                  criticality: Criticality | None = None, riskLevel: RiskLevel | None = None,
                  lifecycleStatus: Lifecycle | None = None) -> Page[Application]:
    """Apply literal search, validated filters, and scope before pagination."""
    return await service.listing(session, search, portfolioId, criticality, riskLevel, lifecycleStatus, paging.page, paging.pageSize)


@router.get("/{id}", response_model=Application, summary="Read a visible application")
async def get(id: Identifier, session: Business, service: Service) -> Application:
    """Return full maintained details for a visible application."""
    return await service.get(session, id)
