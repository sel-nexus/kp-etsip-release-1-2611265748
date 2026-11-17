"""Read and write managed users in the shared Mongo database."""
import re
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase


class UserRepository:
    """Provide bounded, scope-aware account queries."""
    def __init__(self, db: AsyncDatabase) -> None:
        """Bind the pooled application database."""
        self.db = db

    def scope_query(self, scope: list[ObjectId] | None) -> dict:
        """Hide accounts whose effective scope extends outside the caller's scope."""
        if scope is None:
            return {}
        return {"$and": [
            {"portfolioAccess": {"$not": {"$elemMatch": {"$nin": scope}}}},
            {"$or": [{"portfolioAccess.0": {"$exists": True}},
                     {"role": {"$nin": ["Administrator", "Executive", "Auditor"]}}]},
        ]}

    async def listing(self, scope: list[ObjectId] | None, search: str, page: int, size: int):
        """Return a stable bounded page without interpreting search operators."""
        query = self.scope_query(scope)
        if search:
            query = {"$and": [query, {"$or": [{"name": {"$regex": re.escape(search), "$options": "i"}},
                                               {"email": {"$regex": re.escape(search), "$options": "i"}}]}]}
        total = await self.db.users.count_documents(query)
        rows = await self.db.users.find(query).sort([("name", 1), ("_id", 1)]).skip((page - 1) * size).limit(size).to_list(None)
        return rows, total

    async def get(self, identifier: ObjectId, scope: list[ObjectId] | None, session=None):
        """Find one visible account within an optional transaction."""
        return await self.db.users.find_one({"$and": [{"_id": identifier}, self.scope_query(scope)]}, session=session)
