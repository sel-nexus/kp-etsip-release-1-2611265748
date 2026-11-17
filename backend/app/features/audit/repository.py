"""Persist audit events through the pooled native async Mongo database."""
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase
from app.features.audit.schemas import AuditEvent


class AuditRepository:
    """Provide append-only persistence without read/export capabilities."""
    def __init__(self, db: AsyncDatabase) -> None:
        """Bind to the application's shared audit collection."""
        self.collection = db.audit_logs

    async def append(self, event: AuditEvent) -> str:
        """Persist a validated event with BSON references and return its ID."""
        document = event.model_dump()
        for field in ("userId", "entityId"):
            if document[field] is not None:
                document[field] = ObjectId(document[field])
        result = await self.collection.insert_one(document)
        return str(result.inserted_id)
