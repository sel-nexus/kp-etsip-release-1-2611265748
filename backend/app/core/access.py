"""Provide reusable immutable business guards without adding business routes."""
from typing import Annotated, Literal
from fastapi import Depends
from bson import ObjectId
from app.core.errors import DomainError
from app.core.security import get_current_user
from app.features.auth.service import Session
from app.features.auth.schemas import Permission


async def get_business_session(session: Annotated[Session, Depends(get_current_user)]) -> Session:
    """Require password completion before any future business endpoint."""
    if session.user.mustChangePassword:
        raise DomainError(403, "Password change required before business access")
    return session


def require_permission(session: Session, permission: Permission, resource: Literal["application", "portfolio", "administration", "audit"]) -> None:
    """Enforce generic permissions only inside fixed role/resource boundaries."""
    user = session.user
    if user.mustChangePassword:
        raise DomainError(403, "Password change required before business access")
    allowed = permission in user.permissions
    if resource == "administration":
        allowed = allowed and user.role == "Administrator" and "administer" in user.permissions
    if resource == "audit":
        allowed = allowed and user.role in ("Administrator", "Auditor") and permission in ("view", "export")
    if permission in ("delete", "administer"):
        allowed = allowed and user.role == "Administrator"
    if permission in ("create", "edit"):
        allowed = allowed and user.role in ("Administrator", "Portfolio Leader", "Engineer")
        if resource == "portfolio":
            allowed = allowed and (user.role == "Administrator" or (permission == "edit" and user.role == "Portfolio Leader"))
    if permission == "export":
        allowed = allowed and user.role != "Read Only"
    if not allowed:
        raise DomainError(403, "Access denied")


def portfolio_scope(session: Session) -> list[ObjectId] | None:
    """Return None for unrestricted visibility, otherwise explicit BSON IDs."""
    user = session.user
    if not user.portfolioAccess and user.role in ("Administrator", "Executive", "Auditor"):
        return None
    return [ObjectId(identifier) for identifier in user.portfolioAccess]
