"""Expose scoped audit inspection and CSV export."""
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from app.core.access import get_business_session
from app.core.errors import DomainError
from app.core.pagination import Page, Pagination
from app.features.audit.schemas import AuditAction, AuditRecord
from app.features.audit.service import AuditService
from app.features.auth.schemas import Session

router = APIRouter(prefix="/api/audit-logs", tags=["Audit"])


def get_service(request: Request) -> AuditService:
    """Return the lifespan-owned audit service."""
    return request.app.state.auth.audit


def utc_timestamp(value: str | None) -> datetime | None:
    """Accept an ISO timestamp with an explicit UTC offset."""
    if value is None:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DomainError(422, "Invalid UTC timestamp") from exc
    if result.tzinfo is None or result.utcoffset() != timedelta(0):
        raise DomainError(422, "Timestamp must specify UTC")
    return result.astimezone(UTC)


@router.get("", response_model=Page[AuditRecord], summary="Inspect or export audit events")
async def listing(
    session: Annotated[Session, Depends(get_business_session)],
    service: Annotated[AuditService, Depends(get_service)],
    paging: Annotated[Pagination, Depends()],
    userId: Annotated[str | None, Query(min_length=24, max_length=24, pattern=r"^[0-9a-fA-F]{24}$")] = None,
    action: AuditAction | None = None,
    from_date: Annotated[str | None, Query(alias="from", min_length=1, max_length=40)] = None,
    to_date: Annotated[str | None, Query(alias="to", min_length=1, max_length=40)] = None,
    format: Literal["json", "csv"] = "json",
):
    """Apply validated UTC filters and role/permission gates."""
    start, end = utc_timestamp(from_date), utc_timestamp(to_date)
    if format == "csv":
        stream = await service.export(session, userId, action, start, end)
        return StreamingResponse(stream, media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="audit-logs.csv"'})
    return await service.listing(session, userId, action, start, end, paging.page, paging.pageSize)
