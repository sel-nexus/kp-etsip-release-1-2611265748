"""Read local users and live roles; persist login and revocation atomically."""
from datetime import UTC, datetime
from typing import Any
from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase


class AuthRepository:
    """Own all Mongo access for local identity and session state."""
    def __init__(self, db: AsyncDatabase) -> None:
        """Bind shared user and role collections."""
        self.users = db.users
        self.roles = db.roles
        self.db = db

    async def by_email(self, email: str) -> dict[str, Any] | None:
        """Find a normalized literal email without accepting query operators."""
        return await self.users.find_one({"email": email})

    async def by_id(self, user_id: str) -> dict[str, Any] | None:
        """Read current identity by its validated BSON identifier."""
        return await self.users.find_one({"_id": ObjectId(user_id)})

    async def role(self, name: str) -> dict[str, Any] | None:
        """Read current persisted permissions rather than trusting token claims."""
        return await self.roles.find_one({"name": name})

    async def mark_login(self, user_id: str, version: int, password_hash: str, session=None) -> dict[str, Any] | None:
        """Update lastLogin only if identity has not changed during hashing."""
        now = datetime.now(UTC)
        return await self.users.find_one_and_update(
            {"_id": ObjectId(user_id), "status": "Active", "tokenVersion": version, "passwordHash": password_hash},
            {"$set": {"lastLogin": now, "updatedAt": now}}, return_document=ReturnDocument.AFTER, session=session,
        )

    async def revoke(self, user_id: str, version: int) -> bool:
        """Increment a matching session version so all prior tokens are rejected."""
        result = await self.users.update_one(
            {"_id": ObjectId(user_id), "status": "Active", "tokenVersion": version},
            {"$inc": {"tokenVersion": 1}, "$set": {"updatedAt": datetime.now(UTC)}},
        )
        return result.modified_count == 1

    async def update_landing(self, user_id: str, version: int, landing: str, session=None) -> dict[str, Any] | None:
        """Persist a preference only while the requesting session remains active."""
        return await self.users.find_one_and_update(
            {"_id": ObjectId(user_id), "status": "Active", "tokenVersion": version},
            {"$set": {"defaultLandingPage": landing, "updatedAt": datetime.now(UTC)}},
            return_document=ReturnDocument.AFTER, session=session,
        )

    async def change_password(self, user_id: str, version: int, previous_hash: str, replacement_hash: str, session=None) -> bool:
        """Compare credentials/version and rotate all credential state in one write."""
        result = await self.users.update_one(
            {"_id": ObjectId(user_id), "status": "Active", "tokenVersion": version, "passwordHash": previous_hash},
            {"$set": {"passwordHash": replacement_hash, "mustChangePassword": False, "updatedAt": datetime.now(UTC)},
             "$inc": {"tokenVersion": 1}}, session=session,
        )
        return result.modified_count == 1
