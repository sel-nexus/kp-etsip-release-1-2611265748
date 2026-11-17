"""Load environment configuration without opening external resources."""
from typing import Literal
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validate runtime settings and reject publicly known signing keys."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    APP_ENV: Literal["development", "production", "test"] = "development"
    MONGODB_URI: str = "mongodb://127.0.0.1:27017"
    MONGODB_DB: str = Field(default="etsip", pattern=r"^[a-zA-Z0-9_-]+$")
    JWT_SECRET: SecretStr
    JWT_EXPIRY_HOURS: int = Field(default=8, ge=1, le=24)
    CORS_ORIGINS: str = ""
    SEED_ON_STARTUP: bool = True
    SEED_ADMIN_PASSWORD: SecretStr
    SEED_DEMO_PASSWORD: SecretStr
    HOST: str = "0.0.0.0"
    PORT: int = Field(default=8000, ge=1, le=65535)

    @field_validator("SEED_ADMIN_PASSWORD", "SEED_DEMO_PASSWORD")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        """Reject passwords bcrypt would truncate or that are too short."""
        if not 12 <= len(value.get_secret_value().encode("utf-8")) <= 72:
            raise ValueError("Seed passwords must contain 12–72 UTF-8 bytes")
        return value

    @model_validator(mode="after")
    def validate_secret(self) -> "Settings":
        """Fail closed on weak or known dummy keys outside isolated tests."""
        secret = self.JWT_SECRET.get_secret_value()
        if self.APP_ENV != "test" and (
            len(secret) < 32 or any(word in secret.lower() for word in ("change-me", "change-in-production", "dev-secret", "dummy"))
        ):
            raise ValueError("JWT_SECRET requires a random secret of at least 32 characters")
        return self

    @property
    def cors_origins(self) -> list[str]:
        """Return explicit origins without empty entries."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
