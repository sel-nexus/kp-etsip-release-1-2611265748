"""Define credential-free append-only audit records."""
from datetime import datetime
from typing import Literal
from pydantic import Field
from app.features.auth.schemas import MongoId, StrictSchema

AuditAction = Literal["login", "create", "edit", "delete", "roleChange", "permissionChange", "export"]

class AuditEvent(StrictSchema):
    """Describe an immutable activity with nullable unknown-login identity."""
    timestamp: datetime
    userId: MongoId | None
    userName: str = Field(min_length=1, max_length=200)
    action: AuditAction
    entityType: str = Field(min_length=1, max_length=80)
    entityId: MongoId | None
    details: str = Field(min_length=1, max_length=300)
    createdAt: datetime
    updatedAt: datetime


class AuditRecord(AuditEvent):
    """Expose the validated public event identity and fields only."""
    id: MongoId
