"""Exercise direct user service invariants with real Mongo persistence."""
import pytest
from bson import ObjectId
from app.core.errors import DomainError
from app.core.security import verify_password
from app.features.users.schemas import UserCreate, UserWrite
from conftest import PASSWORD


async def test_service_create_and_last_admin_protection(application, client, db):
    """Create a user through the service and reject the last admin demotion."""
    await db.users.update_one({"email": "admin@ketsip.local"}, {"$set": {"mustChangePassword": False}})
    token = (await client.post("/api/auth/login", json={"email": "admin@ketsip.local", "password": PASSWORD})).json()["token"]
    actor = await application.state.auth.authenticate(token)
    service = application.state.users
    payload = UserCreate(name="  Unit User  ", email="UNIT@ketsip.local", role="Engineer", password="UnitPassword123!")
    result = await service.create(actor, payload)
    assert result.name == "Unit User" and result.email == "unit@ketsip.local"
    assert (await db.users.find_one({"email": result.email}))["role"] == "Engineer"
    with pytest.raises(DomainError) as error:
        await service.mutate(actor, actor.user.id, UserWrite(name="Admin", email=actor.user.email, role="Engineer"))
    assert error.value.status == 409
    assert (await db.users.find_one({"email": actor.user.email}))["role"] == "Administrator"


async def test_service_scope_and_id_validation(application, client, db):
    """Reject out-of-scope assignment and invalid service identifiers."""
    portfolio = await db.portfolios.find_one({"name": "Payments"})
    other = await db.portfolios.find_one({"name": "Customer Platform"})
    await db.users.update_one({"email": "admin@ketsip.local"}, {"$set": {"mustChangePassword": False, "portfolioAccess": [portfolio["_id"]]}})
    token = (await client.post("/api/auth/login", json={"email": "admin@ketsip.local", "password": PASSWORD})).json()["token"]
    actor = await application.state.auth.authenticate(token)
    with pytest.raises(DomainError) as error:
        await application.state.users.create(actor, UserCreate(name="Out", email="out@ketsip.local", role="Engineer", portfolioAccess=[str(other["_id"])], password="UnitPassword123!"))
    assert error.value.status == 403
    with pytest.raises(DomainError) as error:
        await application.state.users.get(actor, "invalid")
    assert error.value.status == 422


@pytest.mark.parametrize("operation", ["missing_get", "missing_update", "missing_delete", "self_delete", "self_inactive", "last_admin_demote"])
async def test_service_rejects_missing_or_protected_users_without_writes(application, client, db, operation):
    """Missing users and administrator protections preserve all persisted state."""
    await db.users.update_one({"email": "admin@ketsip.local"}, {"$set": {"mustChangePassword": False}})
    token = (await client.post("/api/auth/login", json={"email": "admin@ketsip.local", "password": PASSWORD})).json()["token"]
    actor = await application.state.auth.authenticate(token)
    service = application.state.users
    users = await db.users.find({}).sort("_id", 1).to_list(None)
    audits = await db.audit_logs.find({}).sort("_id", 1).to_list(None)
    guards = await db.guards.find({}).sort("_id", 1).to_list(None)
    missing = str(ObjectId())
    with pytest.raises(DomainError) as error:
        if operation == "missing_get":
            await service.get(actor, missing)
        elif operation == "missing_update":
            await service.mutate(actor, missing, UserWrite(name="Missing", email="missing@ketsip.local", role="Engineer"))
        elif operation == "missing_delete":
            await service.mutate(actor, missing, None)
        elif operation == "self_delete":
            await service.mutate(actor, actor.user.id, None)
        elif operation == "self_inactive":
            await service.mutate(actor, actor.user.id, UserWrite(name="Admin", email=actor.user.email, role="Administrator", status="Inactive"))
        else:
            await service.mutate(actor, actor.user.id, UserWrite(name="Admin", email=actor.user.email, role="Engineer"))
    assert error.value.status == (404 if operation.startswith("missing") else 409)
    if operation.startswith("self_"):
        assert error.value.message == "You cannot deactivate your own account"
    if operation == "last_admin_demote":
        assert error.value.message == "At least one active Administrator is required"
    assert await db.users.find({}).sort("_id", 1).to_list(None) == users
    assert await db.audit_logs.find({}).sort("_id", 1).to_list(None) == audits
    assert await db.guards.find({}).sort("_id", 1).to_list(None) == guards


@pytest.mark.parametrize("operation", ["create_duplicate", "update_duplicate", "create_missing_role", "update_missing_role", "missing_portfolio"])
async def test_service_conflicts_roll_back_assignments_users_and_audits(application, client, db, operation):
    """Duplicate emails and missing assignment references cannot partially commit."""
    await db.users.update_one({"email": "admin@ketsip.local"}, {"$set": {"mustChangePassword": False}})
    token = (await client.post("/api/auth/login", json={"email": "admin@ketsip.local", "password": PASSWORD})).json()["token"]
    actor = await application.state.auth.authenticate(token)
    service = application.state.users
    target = await db.users.find_one({"email": "readonly@ketsip.local"})
    portfolio = await db.portfolios.find_one({"name": "Payments"})
    if "missing_role" in operation:
        await db.roles.delete_one({"name": "Engineer"})
    users = await db.users.find({}).sort("_id", 1).to_list(None)
    audits = await db.audit_logs.find({}).sort("_id", 1).to_list(None)
    portfolios = await db.portfolios.find({}).sort("_id", 1).to_list(None)
    guards = await db.guards.find({}).sort("_id", 1).to_list(None)
    email = actor.user.email.upper() if "duplicate" in operation else "new-unit@ketsip.local"
    assignment = str(ObjectId()) if operation == "missing_portfolio" else str(portfolio["_id"])
    fields = dict(name="Unit", email=email, role="Engineer", portfolioAccess=[assignment])
    with pytest.raises(DomainError) as error:
        if operation.startswith("update"):
            await service.mutate(actor, str(target["_id"]), UserWrite(**fields))
        else:
            await service.create(actor, UserCreate(**fields, password="UnitPassword123!"))
    assert error.value.status == 409
    expected = "Email already exists" if "duplicate" in operation else ("Role does not exist" if "missing_role" in operation else "Portfolio assignment does not exist")
    assert error.value.message == expected
    assert await db.users.find({}).sort("_id", 1).to_list(None) == users
    assert await db.audit_logs.find({}).sort("_id", 1).to_list(None) == audits
    assert await db.portfolios.find({}).sort("_id", 1).to_list(None) == portfolios
    assert await db.guards.find({}).sort("_id", 1).to_list(None) == guards


async def test_service_updates_assignment_password_and_role_with_audit(application, client, db):
    """Persist assigned portfolios, credential changes, revocation and role audits."""
    await db.users.update_one({"email": "admin@ketsip.local"}, {"$set": {"mustChangePassword": False}})
    token = (await client.post("/api/auth/login", json={"email": "admin@ketsip.local", "password": PASSWORD})).json()["token"]
    actor = await application.state.auth.authenticate(token)
    service = application.state.users
    portfolio = await db.portfolios.find_one({"name": "Payments"})
    created = await service.create(actor, UserCreate(name="Unit", email="unit-service@ketsip.local", role="Engineer", password="UnitPassword123!"))
    identifier = ObjectId(created.id)
    before = await db.users.find_one({"_id": identifier})
    result = await service.mutate(actor, created.id, UserWrite(name="Updated", email=created.email, role="Read Only", portfolioAccess=[str(portfolio["_id"])], password="ChangedPassword123!"))
    after = await db.users.find_one({"_id": identifier})
    assert result.name == "Updated" and result.role == "Read Only"
    assert result.portfolioAccess == [str(portfolio["_id"])]
    assert after["name"] == "Updated" and after["role"] == "Read Only"
    assert after["portfolioAccess"] == [portfolio["_id"]]
    assert after["tokenVersion"] == before["tokenVersion"] + 1
    assert after["passwordHash"] != before["passwordHash"]
    assert await verify_password("ChangedPassword123!", after["passwordHash"])
    assert not await verify_password("UnitPassword123!", after["passwordHash"])
    events = await db.audit_logs.find({"entityType": "user", "entityId": identifier}).to_list(None)
    assert sorted(event["action"] for event in events) == ["create", "edit", "roleChange"]
    assert all(event["userId"] == ObjectId(actor.user.id) for event in events)
    assert all("passwordHash" not in str(event) and "ChangedPassword123!" not in str(event) for event in events)
    await service.mutate(actor, created.id, UserWrite(name="Renamed", email=created.email, role="Read Only", portfolioAccess=[str(portfolio["_id"])]))
    unchanged_auth = await db.users.find_one({"_id": identifier})
    assert unchanged_auth["name"] == "Renamed"
    assert unchanged_auth["passwordHash"] == after["passwordHash"]
    assert unchanged_auth["tokenVersion"] == after["tokenVersion"]
    events = await db.audit_logs.find({"entityType": "user", "entityId": identifier}).to_list(None)
    assert sorted(event["action"] for event in events) == ["create", "edit", "edit", "roleChange"]
    deactivated = await service.mutate(actor, created.id, None)
    final = await db.users.find_one({"_id": identifier})
    assert deactivated.status == "Inactive" and final["status"] == "Inactive"
    assert final["tokenVersion"] == unchanged_auth["tokenVersion"] + 1
    assert final["passwordHash"] == unchanged_auth["passwordHash"]
    events = await db.audit_logs.find({"entityType": "user", "entityId": identifier}).to_list(None)
    assert sorted(event["action"] for event in events) == ["create", "delete", "edit", "edit", "roleChange"]
