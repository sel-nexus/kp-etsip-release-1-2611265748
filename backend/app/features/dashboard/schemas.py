"""Define the executive inventory summary contract."""
from app.features.auth.schemas import MongoId, StrictSchema


class PortfolioMetric(StrictSchema):
    """Describe one visible portfolio and its matching application metrics."""
    id: MongoId
    name: str
    applicationCount: int
    qualityScore: int | None
    highRiskCount: int


class ExecutiveDashboard(StrictSchema):
    """Expose only metrics derived from visible inventory."""
    enterpriseQualityScore: int | None
    applicationHealthScore: int | None
    automationMaturityScore: int | None
    openCriticalDefects: int
    applicationsAtRisk: int
    totalApplications: int
    totalPortfolios: int
    portfolios: list[PortfolioMetric]
