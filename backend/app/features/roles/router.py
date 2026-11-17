"""Expose bounded fixed-role administration endpoints."""
from typing import Annotated
from fastapi import APIRouter, Depends, Path, Request
from app.core.access import get_business_session
from app.core.pagination import Page, Pagination
from app.features.auth.schemas import Session
from app.features.roles.schemas import Role, RoleCreate, RoleWrite
from app.features.roles.service import RoleService

router = APIRouter(prefix="/api/roles", tags=["Roles"])
Business = Annotated[Session, Depends(get_business_session)]
Identifier = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]
Paging = Annotated[Pagination, Depends()]


def get_service(request: Request) -> RoleService:
    """Return the lifespan-owned role service."""
    return request.app.state.roles


Service = Annotated[RoleService, Depends(get_service)]


@router.get("", response_model=Page[Role])
async def listing(actor: Business, service: Service, paging: Paging) -> Page[Role]:
    """Read a bounded page of fixed roles."""
    return await service.listing(actor, paging.page, paging.pageSize)


@router.post("", response_model=Role, status_code=201)
async def create(payload: RoleCreate, actor: Business, service: Service) -> Role:
    """Create a missing fixed role."""
    return await service.create(actor, payload)


@router.put("/{id}", response_model=Role)
async def update(id: Identifier, payload: RoleWrite, actor: Business, service: Service) -> Role:
    """Update the description and generic permissions of one role."""
    return await service.update(actor, id, payload)
