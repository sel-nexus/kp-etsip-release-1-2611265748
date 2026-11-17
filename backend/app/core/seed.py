"""Insert missing six-role local demo identities without overwriting edits."""
from datetime import UTC, datetime
from pymongo.asynchronous.database import AsyncDatabase
from app.core.config import Settings
from app.core.security import hash_password

ROLE_PERMISSIONS = {
    "Administrator": ["view", "create", "edit", "delete", "export", "administer"],
    "Executive": ["view", "export"],
    "Portfolio Leader": ["view", "create", "edit", "export"],
    "Engineer": ["view", "create", "edit", "export"],
    "Auditor": ["view", "export"],
    "Read Only": ["view"],
}
ACCOUNTS = {
    "Administrator": ("admin@ketsip.local", "Demo Administrator"),
    "Executive": ("executive@ketsip.local", "Demo Executive"),
    "Portfolio Leader": ("leader@ketsip.local", "Demo Portfolio Leader"),
    "Engineer": ("engineer@ketsip.local", "Demo Engineer"),
    "Auditor": ("auditor@ketsip.local", "Demo Auditor"),
    "Read Only": ("readonly@ketsip.local", "Demo Read Only"),
}


async def seed_database(db: AsyncDatabase, settings: Settings) -> None:
    """Insert roles and users by natural-key upsert; retain all edited records.

    Notes:
        Scoped roles initially have empty access until portfolios are seeded.
        Administrator password completion is mandatory for business guards.
    """
    now = datetime.now(UTC)
    for role, permissions in ROLE_PERMISSIONS.items():
        await db.roles.update_one({"name": role}, {"$setOnInsert": {
            "name": role, "description": f"Local {role} role", "permissions": permissions,
            "createdAt": now, "updatedAt": now,
        }}, upsert=True)
        email, name = ACCOUNTS[role]
        if await db.users.find_one({"email": email}, {"_id": 1}) is not None:
            continue
        admin = role == "Administrator"
        password_hash = await hash_password((settings.SEED_ADMIN_PASSWORD if admin else settings.SEED_DEMO_PASSWORD).get_secret_value())
        await db.users.update_one({"email": email}, {"$setOnInsert": {
            "name": name, "email": email, "passwordHash": password_hash, "role": role,
            "portfolioAccess": [], "status": "Active", "lastLogin": None, "authSource": "local",
            "managerName": None, "vendorIndicator": False, "defaultLandingPage": None,
            "mustChangePassword": admin, "tokenVersion": 0, "createdAt": now, "updatedAt": now,
        }}, upsert=True)
