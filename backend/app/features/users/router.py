"""Expose authenticated user administration endpoints."""
from typing import Annotated
from fastapi import APIRouter, Depends, Path, Query, Request, Response
from app.core.access import get_business_session
from app.core.pagination import Page, Pagination
from app.features.auth.schemas import Session
from app.features.users.schemas import ManagedUser, UserCreate, UserWrite
from app.features.users.service import UserService

router = APIRouter(prefix="/api/users", tags=["Users"])
Business = Annotated[Session, Depends(get_business_session)]
Identifier = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]
Paging = Annotated[Pagination, Depends()]


def get_service(request: Request) -> UserService:
    """Retrieve the lifespan-owned service."""
    return request.app.state.users


Service = Annotated[UserService, Depends(get_service)]


@router.get("", response_model=Page[ManagedUser])
async def listing(actor: Business, service: Service, paging: Paging, search: Annotated[str, Query(max_length=200)] = "") -> Page[ManagedUser]:
    """Search visible accounts with bounded pagination."""
    return await service.listing(actor, search, paging.page, paging.pageSize)


@router.post("", response_model=ManagedUser, status_code=201)
async def create(payload: UserCreate, actor: Business, service: Service) -> ManagedUser:
    """Create an account with a valid initial password."""
    return await service.create(actor, payload)


@router.get("/{id}", response_model=ManagedUser)
async def get(id: Identifier, actor: Business, service: Service) -> ManagedUser:
    """Read one visible account."""
    return await service.get(actor, id)


@router.put("/{id}", response_model=ManagedUser)
async def update(id: Identifier, payload: UserWrite, actor: Business, service: Service) -> ManagedUser:
    """Replace maintained account fields."""
    return await service.mutate(actor, id, payload)


@router.delete("/{id}", status_code=204)
async def delete(id: Identifier, actor: Business, service: Service) -> Response:
    """Deactivate the account without erasing its identity."""
    await service.mutate(actor, id, None)
    return Response(status_code=204)
