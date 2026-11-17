"""Validate portfolio writes and project inventory reads without internal fields."""
from datetime import datetime
from typing import Annotated, Literal
from pydantic import Field, StringConstraints
from app.features.auth.schemas import MongoId, StrictSchema

PortfolioStatus = Literal["Active", "Archived"]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]


class PortfolioWrite(StrictSchema):
    """Accept only maintained fields; never accept derived scores or counts."""
    name: Name
    owner: Text = ""
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] = ""
    productArea: Text = ""
    status: PortfolioStatus = "Active"


class Portfolio(PortfolioWrite):
    """Expose persisted metadata and live application-derived metrics."""
    id: MongoId
    applicationCount: int = Field(ge=0)
    qualityScore: int | None = Field(ge=0, le=100)
    createdAt: datetime
    updatedAt: datetime


class LinkedApplication(StrictSchema):
    """Project actual linked application inventory, not speculative detail data."""
    id: MongoId
    name: str
    portfolioId: MongoId
    productArea: str
    lifecycleStatus: Literal["Active", "Deprecated", "Retired"]
    qualityScore: int = Field(ge=0, le=100)
    riskLevel: Literal["Low", "Medium", "High"]
