"""Define strict credential, public identity, and signed claim contracts."""
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal
from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, SecretStr, field_validator

RoleName = Literal["Administrator", "Executive", "Portfolio Leader", "Engineer", "Auditor", "Read Only"]
Permission = Literal["view", "create", "edit", "delete", "export", "administer"]


def stringify_id(value: object) -> str:
    """Convert only BSON identifiers or canonical identifier strings."""
    if not isinstance(value, (str, ObjectId)) or not ObjectId.is_valid(value):
        raise ValueError("Invalid identifier")
    return str(value)


MongoId = Annotated[str, BeforeValidator(stringify_id)]


class StrictSchema(BaseModel):
    """Reject extra fields and implicit scalar coercion."""
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


class LoginRequest(StrictSchema):
    """Accept local credentials without exposing the password in representations."""
    email: str = Field(min_length=3, max_length=254)
    password: SecretStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        """Normalize local demo emails and reject query objects or malformed text."""
        value = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+", value):
            raise ValueError("Enter a valid email address")
        return value

    @field_validator("password")
    @classmethod
    def bound_password(cls, value: SecretStr) -> SecretStr:
        """Reject empty or oversized credentials without bcrypt truncation."""
        if not 1 <= len(value.get_secret_value().encode("utf-8")) <= 72:
            raise ValueError("Password must contain 1–72 UTF-8 bytes")
        return value


class PublicUser(StrictSchema):
    """Expose only account fields safe for the current user to inspect."""
    id: MongoId
    name: str
    email: str
    role: RoleName
    permissions: list[Permission]
    portfolioAccess: list[MongoId]
    status: Literal["Active", "Inactive"]
    lastLogin: datetime | None
    authSource: Literal["local"]
    managerName: str | None
    vendorIndicator: bool
    defaultLandingPage: Literal["dashboard", "applications"] | None
    mustChangePassword: bool
    createdAt: datetime
    updatedAt: datetime


class LoginResponse(StrictSchema):
    """Return the signed bearer and its safe current identity."""
    token: str
    user: PublicUser


@dataclass(frozen=True)
class Session:
    """Carry safe identity and internal revocation state separately."""
    user: PublicUser
    token_version: int


class TokenClaims(StrictSchema):
    """Validate required claims after signature and expiration checks."""
    sub: MongoId
    userId: MongoId
    role: RoleName
    tokenVersion: int = Field(ge=0)
    exp: int
    iat: int
    jti: str = Field(min_length=1)
