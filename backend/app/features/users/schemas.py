"""Define strict user administration inputs and safe output models."""
from typing import Literal
from pydantic import Field, SecretStr, field_validator
from app.features.auth.schemas import LoginRequest, MongoId, PublicUser, RoleName, StrictSchema


class UserWrite(StrictSchema):
    """Accept only maintained account fields; credentials remain secret."""
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=254)
    role: RoleName
    portfolioAccess: list[MongoId] = Field(default_factory=list, max_length=100)
    status: Literal["Active", "Inactive"] = "Active"
    managerName: str | None = Field(default=None, max_length=200)
    vendorIndicator: bool = False
    password: SecretStr | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """Reject whitespace-only names."""
        value = value.strip()
        if not value:
            raise ValueError("Name is required")
        return value

    @field_validator("managerName")
    @classmethod
    def normalize_manager(cls, value: str | None) -> str | None:
        """Normalize empty manager names to null."""
        return value.strip() or None if value is not None else None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        """Apply the same email normalization as login."""
        return LoginRequest.normalize_email(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: SecretStr | None) -> SecretStr | None:
        """Prevent weak credentials and bcrypt truncation."""
        if value is not None and not 12 <= len(value.get_secret_value().encode("utf-8")) <= 72:
            raise ValueError("Password must contain 12–72 UTF-8 bytes")
        return value

    @field_validator("portfolioAccess")
    @classmethod
    def unique_portfolios(cls, value: list[str]) -> list[str]:
        """Reject duplicate identifiers after canonicalization."""
        normalized = [item.lower() for item in value]
        if len(set(normalized)) != len(normalized):
            raise ValueError("Duplicate portfolio assignment")
        return normalized


class UserCreate(UserWrite):
    """Require an initial password for a new local account."""
    password: SecretStr


class ManagedUser(PublicUser):
    """Expose the existing credential-free identity contract."""
