"""Aggregate dashboard inputs within the caller's MongoDB scope."""
from typing import Any
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase


class DashboardRepository:
    """Read grouped metrics without materializing raw applications."""
    def __init__(self, db: AsyncDatabase) -> None:
        """Bind the lifespan-owned portfolio collection."""
        self.portfolios = db.portfolios

    async def metrics(self, scope: list[ObjectId] | None, portfolio: ObjectId | None,
                      product_area: str | None, risk: str | None) -> list[dict[str, Any]]:
        """Group matching applications within each visible portfolio in MongoDB."""
        clauses: list[dict[str, Any]] = []
        if scope is not None:
            clauses.append({"_id": {"$in": scope}})
        if portfolio is not None:
            clauses.append({"_id": portfolio})
        app_match: dict[str, Any] = {"$expr": {"$eq": ["$portfolioId", "$$portfolio"]}}
        if product_area is not None:
            app_match["productArea"] = product_area
        if risk is not None:
            app_match["riskLevel"] = risk
        pipeline: list[dict[str, Any]] = [
            {"$match": {"$and": clauses} if clauses else {}},
            {"$lookup": {"from": "applications", "let": {"portfolio": "$_id"}, "pipeline": [
                {"$match": app_match},
                {"$group": {"_id": None, "count": {"$sum": 1}, "quality": {"$sum": "$qualityScore"},
                            "health": {"$sum": "$applicationHealthScore"}, "automation": {"$sum": "$automationCoverage"},
                            "defects": {"$sum": "$openCriticalDefects"},
                            "highRisk": {"$sum": {"$cond": [{"$eq": ["$riskLevel", "High"]}, 1, 0]}}}},
            ], "as": "metrics"}},
            {"$set": {"metrics": {"$arrayElemAt": ["$metrics", 0]}}},
        ]
        if portfolio is not None or product_area is not None or risk is not None:
            pipeline.append({"$match": {"metrics.count": {"$gt": 0}}})
        pipeline.extend([{"$project": {"name": 1, "metrics": 1}}, {"$sort": {"name": 1, "_id": 1}}])
        cursor = await self.portfolios.aggregate(pipeline)
        return [row async for row in cursor]
