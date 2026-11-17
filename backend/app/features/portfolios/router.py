"""Expose the exact portfolio CRUD and linked-inventory API paths."""
from typing import Annotated
from fastapi import APIRouter, Depends, Path, Query, Request, Response
from app.core.access import get_business_session
from app.core.pagination import Page, Pagination
from app.features.auth.schemas import Session
from app.features.portfolios.schemas import LinkedApplication, Portfolio, PortfolioStatus, PortfolioWrite
from app.features.portfolios.service import PortfolioService

router = APIRouter(prefix="/api/portfolios", tags=["Portfolios"])
Business = Annotated[Session, Depends(get_business_session)]
Identifier = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]
Paging = Annotated[Pagination, Depends()]


def get_service(request: Request) -> PortfolioService:
    """Retrieve the lifespan's repository-backed business service."""
    return request.app.state.portfolios


Service = Annotated[PortfolioService, Depends(get_service)]


@router.get("", response_model=Page[Portfolio], summary="Search visible portfolios")
async def listing(session: Business, service: Service, paging: Paging,
                  search: Annotated[str, Query(max_length=200)] = "",
                  status: PortfolioStatus | None = None,
                  productArea: Annotated[str | None, Query(max_length=200)] = None) -> Page[Portfolio]:
    """Apply search, exact filters and explicit scope before pagination."""
    return await service.listing(session, search, status, productArea, paging.page, paging.pageSize)


@router.post("", response_model=Portfolio, status_code=201, summary="Create a portfolio")
async def create(payload: PortfolioWrite, session: Business, service: Service) -> Portfolio:
    """Persist maintained fields after Administrator and generic permission gates."""
    return await service.create(session, payload)


@router.get("/{id}", response_model=Portfolio, summary="Read a visible portfolio")
async def get(id: Identifier, session: Business, service: Service) -> Portfolio:
    """Return metadata plus actual linked application metrics."""
    return await service.get(session, id)


@router.put("/{id}", response_model=Portfolio, summary="Edit a portfolio")
async def update(id: Identifier, payload: PortfolioWrite, session: Business, service: Service) -> Portfolio:
    """Update all maintained fields within assignment and role boundaries."""
    return await service.update(session, id, payload)


@router.delete("/{id}", status_code=204, summary="Delete an unlinked portfolio")
async def delete(id: Identifier, session: Business, service: Service) -> Response:
    """Reject linked or invisible deletion and return no content on success."""
    await service.delete(session, id)
    return Response(status_code=204)


@router.get("/{id}/applications", response_model=Page[LinkedApplication], summary="Read actual linked applications")
async def linked(id: Identifier, session: Business, service: Service, paging: Paging) -> Page[LinkedApplication]:
    """Paginate real Mongo application references after checking portfolio scope."""
    return await service.linked(session, id, paging.page, paging.pageSize)
