"""Validate self-service preferences and secret password inputs strictly."""
from typing import Literal
from pydantic import SecretStr, field_validator
from app.features.auth.schemas import StrictSchema


class ProfileRequest(StrictSchema):
    """Accept only the approved persisted landing preference."""
    defaultLandingPage: Literal["dashboard", "applications"]


class ChangePasswordRequest(StrictSchema):
    """Require the current credential and a byte-bounded replacement."""
    currentPassword: SecretStr
    newPassword: SecretStr

    @field_validator("currentPassword")
    @classmethod
    def bound_current(cls, value: SecretStr) -> SecretStr:
        """Prevent empty credentials and bcrypt's silent byte truncation."""
        if not 1 <= len(value.get_secret_value().encode("utf-8")) <= 72:
            raise ValueError("Current password must contain 1–72 UTF-8 bytes")
        return value

    @field_validator("newPassword")
    @classmethod
    def bound_new(cls, value: SecretStr) -> SecretStr:
        """Enforce the replacement policy before any password work."""
        if not 12 <= len(value.get_secret_value().encode("utf-8")) <= 72:
            raise ValueError("New password must contain 12–72 UTF-8 bytes")
        return value
