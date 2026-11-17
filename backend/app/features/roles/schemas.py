"""Validate fixed roles and their editable generic permissions."""
from datetime import datetime
from pydantic import Field, field_validator
from app.features.auth.schemas import MongoId, Permission, RoleName, StrictSchema


class RoleWrite(StrictSchema):
    """Accept a description and a distinct bounded permission set."""
    description: str = Field(max_length=500)
    permissions: list[Permission] = Field(max_length=6)

    @field_validator("permissions")
    @classmethod
    def distinct_permissions(cls, value: list[Permission]) -> list[Permission]:
        """Reject repeated permissions instead of silently normalizing them."""
        if len(value) != len(set(value)):
            raise ValueError("Permissions must be distinct")
        return value


class RoleCreate(RoleWrite):
    """Require a fixed role name when creating a missing role."""
    name: RoleName


class Role(RoleWrite):
    """Expose persisted role metadata without internal BSON fields."""
    id: MongoId
    name: RoleName
    createdAt: datetime
    updatedAt: datetime
