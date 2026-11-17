"""Persist fixed roles in the shared Mongo database."""
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase


class RoleRepository:
    """Provide bounded reads and transactional role writes."""
    def __init__(self, db: AsyncDatabase) -> None:
        """Bind the application database."""
        self.db = db

    async def listing(self, page: int, size: int) -> tuple[list[dict], int]:
        """Return a stable page and its total."""
        total = await self.db.roles.count_documents({})
        rows = await self.db.roles.find({}).sort([("name", 1), ("_id", 1)]).skip((page - 1) * size).limit(size).to_list(None)
        return rows, total

    async def get(self, identifier: ObjectId, session):
        """Read a role inside the caller's transaction."""
        return await self.db.roles.find_one({"_id": identifier}, session=session)

    async def insert(self, document: dict, session):
        """Insert a role in the caller's transaction."""
        result = await self.db.roles.insert_one(document, session=session)
        return await self.get(result.inserted_id, session)

    async def update(self, identifier: ObjectId, fields: dict, session):
        """Persist changes and return the transactional post-image."""
        await self.db.roles.update_one({"_id": identifier}, {"$set": fields}, session=session)
        return await self.get(identifier, session)
