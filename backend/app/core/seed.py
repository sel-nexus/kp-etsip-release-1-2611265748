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
        Scoped demo identities receive Payments once; subsequent edits are retained.
        Administrator password completion is mandatory for business guards.
    """
    now = datetime.now(UTC)
    portfolios = []
    for name, owner, area, description in [
        ("Payments", "Demo Payments Leader", "Financial Services", "Payment processing and settlement inventory."),
        ("Customer Platform", "Demo Customer Leader", "Customer Experience", "Customer-facing platform inventory."),
        ("Data & Analytics", "Demo Data Leader", "Data", "Data and analytics platform inventory."),
    ]:
        # Keep a stable identity when a seeded portfolio is renamed by a user.
        portfolio = await db.portfolios.find_one({"seedKey": name})
        if portfolio is None:
            portfolio = await db.portfolios.find_one({"name": name})
            if portfolio is not None and "seedKey" not in portfolio:
                await db.portfolios.update_one({"_id": portfolio["_id"], "seedKey": {"$exists": False}}, {"$set": {"seedKey": name}})
            elif portfolio is None:
                await db.portfolios.update_one({"seedKey": name}, {"$setOnInsert": {
                    "name": name, "owner": owner, "productArea": area,
                    "description": description, "status": "Active", "createdAt": now, "updatedAt": now,
                }}, upsert=True)
                portfolio = await db.portfolios.find_one({"seedKey": name})
        portfolios.append(portfolio["_id"])
    # Stable seed keys survive renamed records; existing data is never overwritten.
    inventory = [
        ("Payment Gateway", 0, "Critical", 1, "Active", 82, 78, 73, 69, 12, 2, "High"),
        ("Settlement Engine", 0, "High", 1, "Active", 88, 85, 80, 76, 8, 1, "Medium"),
        ("Fraud Review", 0, "High", 2, "Active", 74, 72, 61, 65, 18, 3, "High"),
        ("Billing Archive", 0, "Medium", 3, "Deprecated", 67, 70, 52, 58, 11, 0, "Medium"),
        ("Customer Portal", 1, "Critical", 1, "Active", 91, 89, 84, 81, 5, 0, "Low"),
        ("Identity Directory", 1, "High", 2, "Active", 85, 83, 78, 74, 9, 1, "Medium"),
        ("Contact Preferences", 1, "Medium", 3, "Active", 92, 90, 88, 86, 3, 0, "Low"),
        ("Analytics Warehouse", 2, "High", 2, "Active", 79, 81, 70, 72, 14, 2, "High"),
        ("Data Catalog", 2, "Medium", 3, "Active", 87, 86, 77, 79, 6, 0, "Low"),
        ("Legacy Extracts", 2, "Low", 4, "Retired", 58, 62, 35, 40, 7, 0, "Medium"),
    ]
    areas = ["Financial Services", "Customer Experience", "Data"]
    for name, index, criticality, tier, lifecycle, health, quality, automation, unit, defects, critical, risk in inventory:
        existing = await db.applications.find_one({"$or": [{"seedKey": name}, {"name": name}]})
        if existing is not None:
            continue
        await db.applications.update_one({"seedKey": name}, {"$setOnInsert": {
            "name": name, "description": f"Manually maintained inventory for {name}.",
            "portfolioId": portfolios[index], "productArea": areas[index],
            "businessOwner": "Business Operations", "technologyOwner": "Platform Engineering", "etsOwner": "Enterprise Testing Services",
            "criticality": criticality, "tier": tier, "lifecycleStatus": lifecycle,
            "technologyStack": "Cloud services and APIs", "repositoryLink": None, "pipelineLink": None,
            "applicationHealthScore": health, "qualityScore": quality, "automationCoverage": automation,
            "unitTestCoverage": unit, "openDefects": defects, "openCriticalDefects": critical,
            "riskLevel": risk, "createdAt": now, "updatedAt": now,
        }}, upsert=True)
    for role, permissions in ROLE_PERMISSIONS.items():
        await db.roles.update_one({"name": role}, {"$setOnInsert": {
            "name": role, "description": f"Local {role} role", "permissions": permissions,
            "createdAt": now, "updatedAt": now,
        }}, upsert=True)
        email, name = ACCOUNTS[role]
        existing = await db.users.find_one({"email": email})
        if existing is not None:
            # Migrate only pristine identities from the earlier identity-only seed.
            # lastLogin and updatedAt protect intentionally edited assignments.
            if role in ("Portfolio Leader", "Engineer", "Read Only") and existing["portfolioAccess"] == [] and existing["lastLogin"] is None and existing["createdAt"] == existing["updatedAt"]:
                await db.users.update_one({"_id": existing["_id"], "portfolioAccess": [], "lastLogin": None, "updatedAt": existing["updatedAt"], "portfolioSeedInitialized": {"$exists": False}},
                    {"$set": {"portfolioAccess": [portfolios[0]], "portfolioSeedInitialized": True}})
            continue
        admin = role == "Administrator"
        password_hash = await hash_password((settings.SEED_ADMIN_PASSWORD if admin else settings.SEED_DEMO_PASSWORD).get_secret_value())
        await db.users.update_one({"email": email}, {"$setOnInsert": {
            "name": name, "email": email, "passwordHash": password_hash, "role": role,
            "portfolioAccess": [portfolios[0]] if role in ("Portfolio Leader", "Engineer", "Read Only") else [], "portfolioSeedInitialized": True, "status": "Active", "lastLogin": None, "authSource": "local",
            "managerName": None, "vendorIndicator": False, "defaultLandingPage": None,
            "mustChangePassword": admin, "tokenVersion": 0, "createdAt": now, "updatedAt": now,
        }}, upsert=True)
