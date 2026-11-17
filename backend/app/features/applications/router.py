"""Expose read-only application inventory endpoints."""
from typing import Annotated
from fastapi import APIRouter, Depends, Path, Query, Request, Response
from app.core.access import get_business_session
from app.core.pagination import Page, Pagination
from app.features.auth.schemas import Session
from app.features.applications.schemas import Application, ApplicationWrite, Criticality, Lifecycle, RiskLevel
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


@router.post("", response_model=Application, status_code=201)
async def create(payload: ApplicationWrite, session: Business, service: Service) -> Application:
    """Create a scoped application and its audit event atomically."""
    return await service.mutate(session, payload, None, "create")


@router.put("/{id}", response_model=Application)
async def update(id: Identifier, payload: ApplicationWrite, session: Business, service: Service) -> Application:
    """Update an existing scoped application."""
    return await service.mutate(session, payload, id, "edit")


@router.delete("/{id}", status_code=204)
async def delete(id: Identifier, session: Business, service: Service) -> Response:
    """Delete an application only for an authorized administrator."""
    await service.mutate(session, None, id, "delete")
    return Response(status_code=204)
