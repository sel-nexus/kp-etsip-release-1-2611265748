"""Exercise role service invariants using an isolated Mongo replica set."""
import pytest
from bson import ObjectId
from pydantic import ValidationError
from app.core.errors import DomainError
from app.features.roles.schemas import RoleCreate, RoleWrite
from conftest import PASSWORD


async def test_role_service_updates_and_rechecks_authority(application, client, db):
    """Persist a role and reject a stale actor after permission revocation."""
    await db.users.update_one({"email": "admin@ketsip.local"}, {"$set": {"mustChangePassword": False}})
    token = (await client.post("/api/auth/login", json={"email": "admin@ketsip.local", "password": PASSWORD})).json()["token"]
    actor = await application.state.auth.authenticate(token)
    service = application.state.roles
    roles = await service.listing(actor, 1, 100)
    assert roles.total == 6
    role = next(item for item in roles.items if item.name == "Engineer")
    updated = await service.update(actor, role.id, RoleWrite(description="Updated", permissions=["view"]))
    assert updated.permissions == ["view"]
    assert (await db.roles.find_one({"_id": ObjectId(role.id)}))["description"] == "Updated"
    await db.roles.update_one({"name": "Administrator"}, {"$pull": {"permissions": "administer"}})
    with pytest.raises(DomainError) as error:
        await service.update(actor, role.id, RoleWrite(description="Forbidden", permissions=[]))
    assert error.value.status == 403
    assert (await db.roles.find_one({"_id": ObjectId(role.id)}))["description"] == "Updated"


def test_role_schema_rejects_unknown_names_permissions_duplicates_and_extra():
    """Reject vocabulary violations, duplicates and attempted name updates."""
    for data in (
        {"name": "Root", "description": "", "permissions": []},
        {"name": "Engineer", "description": "", "permissions": ["root"]},
        {"name": "Engineer", "description": "", "permissions": ["view", "view"]},
    ):
        with pytest.raises(ValidationError):
            RoleCreate(**data)
    with pytest.raises(ValidationError):
        RoleWrite(description="", permissions=[], name="Administrator")
