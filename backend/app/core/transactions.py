"""Coordinate portfolio references using retryable Mongo transactions."""
from collections.abc import Awaitable, Callable
from typing import TypeVar
from bson import ObjectId
from pymongo.errors import OperationFailure, ConfigurationError, ServerSelectionTimeoutError
from pymongo.asynchronous.database import AsyncDatabase
from app.core.errors import DomainError

T = TypeVar("T")


async def transaction(db: AsyncDatabase, callback: Callable[..., Awaitable[T]]) -> T:
    """Run a retryable transaction, refusing deployments without transaction support."""
    try:
        async with db.client.start_session() as session:
            return await session.with_transaction(callback)
    except (ConfigurationError, ServerSelectionTimeoutError) as exc:
        raise DomainError(503, "MongoDB transactions are unavailable") from exc
    except OperationFailure as exc:
        if exc.code in (20, 263, 303, 40573):
            raise DomainError(503, "MongoDB transactions are unavailable") from exc
        raise


async def touch_portfolio(db: AsyncDatabase, identifier: ObjectId, scope, session):
    """Write the parent to conflict with concurrent deletion, then return it."""
    query = {"_id": identifier}
    if scope is not None:
        query["_id"] = {"$eq": identifier, "$in": scope}
    result = await db.portfolios.find_one_and_update(query, {"$inc": {"referenceVersion": 1}}, session=session)
    if result is None:
        raise DomainError(404, "Portfolio not found")
    return result
