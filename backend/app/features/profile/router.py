"""Expose authenticated self-service profile and password operations."""
from typing import Annotated
from fastapi import APIRouter, Depends, Request, Response
from app.core.security import get_current_user
from app.features.auth.schemas import PublicUser, Session
from app.features.profile.schemas import ChangePasswordRequest, ProfileRequest

router = APIRouter(prefix="/api/auth", tags=["My Profile"])


@router.put("/profile", response_model=PublicUser, summary="Save landing preference")
async def update_profile(payload: ProfileRequest, request: Request,
                         session: Annotated[Session, Depends(get_current_user)]) -> PublicUser:
    """Allow current-account preferences even during mandatory password change."""
    return await request.app.state.profile.update_profile(session, payload)


@router.post("/change-password", status_code=204, summary="Change password and revoke prior sessions")
async def change_password(payload: ChangePasswordRequest, request: Request,
                          session: Annotated[Session, Depends(get_current_user)]) -> Response:
    """Rotate credentials and require a new login instead of issuing a token."""
    await request.app.state.profile.change_password(session, payload)
    return Response(status_code=204)
