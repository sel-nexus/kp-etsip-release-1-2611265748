"""Define stable report formats and inventory CSV column contracts."""
from typing import Literal

ReportKind = Literal["applications", "portfolios"]
APPLICATION_COLUMNS = ("name", "portfolioName", "criticality", "tier", "lifecycleStatus", "applicationHealthScore", "automationCoverage", "openCriticalDefects", "riskLevel")
PORTFOLIO_COLUMNS = ("name", "owner", "productArea", "applicationCount", "qualityScore", "status")
