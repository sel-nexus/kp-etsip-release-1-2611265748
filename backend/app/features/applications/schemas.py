"""Define the public application inventory contract."""
from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit
from pydantic import Field, StringConstraints, field_validator
from app.features.auth.schemas import MongoId, StrictSchema

Criticality = Literal["Low", "Medium", "High", "Critical"]
RiskLevel = Literal["Low", "Medium", "High"]
Lifecycle = Literal["Active", "Deprecated", "Retired"]
Text = Annotated[str, StringConstraints(max_length=2000)]


class ApplicationWrite(StrictSchema):
    """Validate every user-maintained inventory field."""
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    description: Text
    portfolioId: Annotated[str, StringConstraints(pattern=r"^[0-9a-fA-F]{24}$")]
    productArea: Text
    businessOwner: Text
    technologyOwner: Text
    etsOwner: Text
    criticality: Criticality
    tier: int = Field(ge=1, le=4)
    lifecycleStatus: Lifecycle
    technologyStack: Text
    repositoryLink: str | None
    pipelineLink: str | None
    applicationHealthScore: int = Field(ge=0, le=100)
    qualityScore: int = Field(ge=0, le=100)
    automationCoverage: int = Field(ge=0, le=100)
    unitTestCoverage: int = Field(ge=0, le=100)
    openDefects: int = Field(ge=0)
    openCriticalDefects: int = Field(ge=0)
    riskLevel: RiskLevel

    @field_validator("repositoryLink", "pipelineLink")
    @classmethod
    def safe_link(cls, value: str | None) -> str | None:
        """Reject links that cannot safely be offered as web navigation."""
        if value is not None:
            parts = urlsplit(value)
            if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
                raise ValueError("Only HTTP(S) links without credentials are allowed")
        return value


class Application(ApplicationWrite):
    """Expose maintained fields and the current linked portfolio name."""
    id: MongoId
    portfolioId: MongoId
    portfolioName: str
    createdAt: datetime
    updatedAt: datetime
