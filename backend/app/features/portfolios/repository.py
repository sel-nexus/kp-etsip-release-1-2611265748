"""Persist portfolios and read linked applications using native async Mongo."""
import re
from datetime import UTC, datetime
from typing import Any
from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase


class PortfolioRepository:
    """Own inventory queries with explicit BSON scope and stable pagination."""
    def __init__(self, db: AsyncDatabase) -> None:
        """Bind shared collections without opening another client."""
        self.collection = db.portfolios
        self.applications = db.applications
        self.db = db

    def query(self, scope: list[ObjectId] | None, identifier: ObjectId | None = None) -> dict[str, Any]:
        """Build visibility even for an empty assignment list."""
        query: dict[str, Any] = {} if scope is None else {"_id": {"$in": scope}}
        if identifier is not None:
            query = {"$and": [query, {"_id": identifier}]}
        return query

    async def listing(self, scope: list[ObjectId] | None, search: str, status: str | None, product_area: str | None,
                      page: int, page_size: int) -> tuple[list[dict[str, Any]], int]:
        """Filter literal user text in Mongo and paginate in deterministic name order."""
        query = self.query(scope)
        if search:
            query["$or"] = [{field: {"$regex": re.escape(search), "$options": "i"}} for field in ("name", "owner", "description")]
        if status:
            query["status"] = status
        if product_area is not None:
            query["productArea"] = product_area
        total = await self.collection.count_documents(query)
        rows = await self.collection.find(query).sort([("name", 1), ("_id", 1)]).skip((page - 1) * page_size).limit(page_size).to_list(None)
        return rows, total

    async def get(self, identifier: ObjectId, scope: list[ObjectId] | None) -> dict[str, Any] | None:
        """Read a portfolio only within the caller's visibility."""
        return await self.collection.find_one(self.query(scope, identifier))

    async def metrics(self, identifiers: list[ObjectId]) -> dict[ObjectId, dict[str, Any]]:
        """Aggregate all linked lifecycle states for only the requested portfolios."""
        cursor = await self.applications.aggregate([
            {"$match": {"portfolioId": {"$in": identifiers}}},
            {"$group": {"_id": "$portfolioId", "count": {"$sum": 1}, "scoreSum": {"$sum": "$qualityScore"}}},
        ])
        return {row["_id"]: row async for row in cursor}

    async def linked(self, identifier: ObjectId, page: int, page_size: int) -> tuple[list[dict[str, Any]], int]:
        """Read actual applications with a bounded public projection."""
        query = {"portfolioId": identifier}
        projection = {field: 1 for field in ("name", "portfolioId", "productArea", "lifecycleStatus", "qualityScore", "riskLevel")}
        rows = await self.applications.find(query, projection).sort([("name", 1), ("_id", 1)]).skip((page - 1) * page_size).limit(page_size).to_list(None)
        return rows, await self.applications.count_documents(query)

    async def create(self, fields: dict[str, Any]) -> dict[str, Any]:
        """Insert validated fields; uniqueness is enforced by the database index."""
        now = datetime.now(UTC)
        document = {**fields, "createdAt": now, "updatedAt": now}
        result = await self.collection.insert_one(document)
        return await self.collection.find_one({"_id": result.inserted_id})

    async def update(self, previous: dict[str, Any], scope: list[ObjectId] | None, fields: dict[str, Any]) -> dict[str, Any] | None:
        """Compare prior fields to avoid overwriting a concurrent edit or deletion."""
        query = self.query(scope, previous["_id"])
        query["updatedAt"] = previous["updatedAt"]
        for field in ("name", "owner", "description", "productArea", "status"):
            query[field] = previous[field]
        return await self.collection.find_one_and_update(query, {"$set": {**fields, "updatedAt": datetime.now(UTC)}}, return_document=ReturnDocument.AFTER)

    async def has_links(self, identifier: ObjectId) -> bool:
        """Check every linked application, including retired records."""
        return await self.applications.find_one({"portfolioId": identifier}, {"_id": 1}) is not None

    async def delete(self, previous: dict[str, Any], scope: list[ObjectId] | None) -> bool:
        """Delete only the unchanged scoped portfolio; never fabricate success."""
        query = self.query(scope, previous["_id"])
        query["updatedAt"] = previous["updatedAt"]
        for field in ("name", "owner", "description", "productArea", "status"):
            query[field] = previous[field]
        return (await self.collection.delete_one(query)).deleted_count == 1
