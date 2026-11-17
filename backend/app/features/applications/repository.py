"""Read application inventory from native MongoDB."""
import re
from typing import Any
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase


class ApplicationRepository:
    """Join applications to existing portfolios inside scoped Mongo queries."""
    def __init__(self, db: AsyncDatabase) -> None:
        """Bind the lifespan-owned collection."""
        self.collection = db.applications

    def query(self, scope: list[ObjectId] | None, search: str, portfolio: ObjectId | None,
              criticality: str | None, risk: str | None, lifecycle: str | None) -> dict[str, Any]:
        """Escape literal search and combine filters without allowing scope override."""
        clauses: list[dict[str, Any]] = []
        if scope is not None:
            clauses.append({"portfolioId": {"$in": scope}})
        if portfolio is not None:
            clauses.append({"portfolioId": portfolio})
        if search:
            clauses.append({"$or": [{key: {"$regex": re.escape(search), "$options": "i"}}
                                    for key in ("name", "description")]})
        for key, value in (("criticality", criticality), ("riskLevel", risk), ("lifecycleStatus", lifecycle)):
            if value is not None:
                clauses.append({key: value})
        return {"$and": clauses} if clauses else {}

    async def listing(self, query: dict[str, Any], page: int, page_size: int) -> tuple[list[dict[str, Any]], int]:
        """Return bounded stable rows and total, excluding orphaned references."""
        pipeline = [
            {"$match": query},
            {"$lookup": {"from": "portfolios", "localField": "portfolioId", "foreignField": "_id", "as": "portfolio"}},
            {"$unwind": "$portfolio"},
            {"$sort": {"name": 1, "_id": 1}},
            {"$facet": {"items": [{"$skip": (page - 1) * page_size}, {"$limit": page_size}], "count": [{"$count": "total"}]}},
        ]
        cursor = await self.collection.aggregate(pipeline)
        result = await cursor.to_list(None)
        batch = result[0] if result else {"items": [], "count": []}
        return batch["items"], batch["count"][0]["total"] if batch["count"] else 0

    async def get(self, identifier: ObjectId, scope: list[ObjectId] | None) -> dict[str, Any] | None:
        """Return only a visible record whose portfolio still exists."""
        query = self.query(scope, "", None, None, None, None)
        query = {"$and": [query, {"_id": identifier}]}
        cursor = await self.collection.aggregate([
            {"$match": query},
            {"$lookup": {"from": "portfolios", "localField": "portfolioId", "foreignField": "_id", "as": "portfolio"}},
            {"$unwind": "$portfolio"}, {"$limit": 1},
        ])
        rows = await cursor.to_list(None)
        return rows[0] if rows else None
