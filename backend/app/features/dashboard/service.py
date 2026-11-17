"""Calculate exact dashboard metrics from MongoDB aggregates."""
from bson import ObjectId
from app.core.access import portfolio_scope, require_permission
from app.core.errors import DomainError
from app.features.auth.schemas import Session
from app.features.dashboard.repository import DashboardRepository
from app.features.dashboard.schemas import ExecutiveDashboard, PortfolioMetric


def mean_half_up(total: int, count: int) -> int | None:
    """Round nonnegative integer means half up; return None without observations."""
    return (2 * total + count) // (2 * count) if count else None


class DashboardService:
    """Apply view authorization and calculate inventory summaries."""
    def __init__(self, repository: DashboardRepository) -> None:
        """Use the shared Mongo repository."""
        self.repository = repository

    async def executive(self, session: Session, portfolio_id: str | None = None,
                        product_area: str | None = None, risk: str | None = None) -> ExecutiveDashboard:
        """Return metrics over the intersection of scope and selected filters."""
        require_permission(session, "view", "application")
        if portfolio_id is not None and not ObjectId.is_valid(portfolio_id):
            raise DomainError(422, "Invalid portfolio identifier")
        if risk is not None and risk not in ("Low", "Medium", "High"):
            raise DomainError(422, "Invalid risk level")
        rows = await self.repository.metrics(portfolio_scope(session), ObjectId(portfolio_id) if portfolio_id else None,
                                             product_area, risk)
        count = quality = health = automation = defects = high = 0
        portfolios: list[PortfolioMetric] = []
        for row in rows:
            metric = row.get("metrics") or {}
            n = metric.get("count", 0)
            count += n
            quality += metric.get("quality", 0)
            health += metric.get("health", 0)
            automation += metric.get("automation", 0)
            defects += metric.get("defects", 0)
            high += metric.get("highRisk", 0)
            portfolios.append(PortfolioMetric(id=row["_id"], name=row["name"], applicationCount=n,
                                              qualityScore=mean_half_up(metric.get("quality", 0), n),
                                              highRiskCount=metric.get("highRisk", 0)))
        return ExecutiveDashboard(enterpriseQualityScore=mean_half_up(quality, count),
                                  applicationHealthScore=mean_half_up(health, count),
                                  automationMaturityScore=mean_half_up(automation, count),
                                  openCriticalDefects=defects, applicationsAtRisk=high, totalApplications=count,
                                  totalPortfolios=len(portfolios), portfolios=portfolios)
