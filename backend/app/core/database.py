"""Expose the lifespan-owned Mongo database and auth query indexes."""
from fastapi import Request
from pymongo.asynchronous.database import AsyncDatabase


async def create_indexes(db: AsyncDatabase) -> None:
    """Create unique natural keys and bounded audit-query indexes idempotently."""
    await db.users.create_index("email", unique=True)
    await db.guards.update_one({"_id": "active-administrators"}, {"$setOnInsert": {"version": 0}}, upsert=True)
    await db.roles.create_index("name", unique=True)
    await db.portfolios.create_index("name", unique=True)
    await db.portfolios.create_index("seedKey", unique=True, sparse=True)
    await db.portfolios.create_index([("status", 1), ("productArea", 1), ("name", 1)])
    await db.applications.create_index([("portfolioId", 1), ("name", 1)])
    await db.applications.create_index("name", unique=True)
    await db.applications.create_index("seedKey", unique=True, sparse=True)
    await db.applications.create_index([("criticality", 1), ("riskLevel", 1), ("lifecycleStatus", 1)])
    await db.audit_logs.create_index([("timestamp", -1), ("_id", -1)])
    await db.audit_logs.create_index([("userId", 1), ("timestamp", -1)])
    await db.audit_logs.create_index([("action", 1), ("timestamp", -1)])


def get_database(request: Request) -> AsyncDatabase:
    """Return the shared database initialized on this application's event loop."""
    return request.app.state.db
