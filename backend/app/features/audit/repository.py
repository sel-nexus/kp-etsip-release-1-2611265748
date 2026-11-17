"""Persist audit events through the pooled native async Mongo database."""
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase
from app.features.audit.schemas import AuditEvent


class AuditRepository:
    """Provide append-only persistence and explicitly projected reads."""
    def __init__(self, db: AsyncDatabase) -> None:
        """Bind to the application's shared audit collection."""
        self.collection = db.audit_logs
        self.db = db

    async def append(self, event: AuditEvent, session=None) -> str:
        """Persist a validated event with BSON references and return its ID."""
        document = event.model_dump()
        for field in ("userId", "entityId"):
            if document[field] is not None:
                document[field] = ObjectId(document[field])
        result = await self.collection.insert_one(document, session=session)
        return str(result.inserted_id)

    def cursor(self, query):
        """Read public fields in stable newest-first order, never stored extras."""
        fields = ("timestamp", "userId", "userName", "action", "entityType", "entityId", "details", "createdAt", "updatedAt")
        return self.collection.find(query, {field: 1 for field in fields}).sort([("timestamp", -1), ("_id", -1)])

    async def listing(self, query, page: int, page_size: int):
        """Read one bounded page and its filtered count."""
        total = await self.collection.count_documents(query)
        rows = await self.cursor(query).skip((page - 1) * page_size).limit(page_size).to_list(None)
        return rows, total
