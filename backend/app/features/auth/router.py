"""Expose only the approved local login, logout, and current-user endpoints."""
from typing import Annotated
from fastapi import APIRouter, Depends, Request, Response
from app.core.security import get_current_user
from app.features.auth.schemas import LoginRequest, LoginResponse, PublicUser
from app.features.auth.service import Session

router = APIRouter(prefix="/api/auth", tags=["Identity"])


@router.post("/login", response_model=LoginResponse, summary="Establish a local session")
async def login(credentials: LoginRequest, request: Request) -> LoginResponse:
    """Establish an audited local session using strict JSON credentials."""
    return await request.app.state.auth.login(credentials)


@router.get("/me", response_model=PublicUser, summary="Read current identity")
async def me(session: Annotated[Session, Depends(get_current_user)]) -> PublicUser:
    """Return live account/access information without internal credentials."""
    return session.user


@router.post("/logout", status_code=204, summary="Revoke prior sessions")
async def logout(request: Request, session: Annotated[Session, Depends(get_current_user)]) -> Response:
    """Revoke all earlier tokens and return an empty success response."""
    await request.app.state.auth.logout(session)
    return Response(status_code=204)
