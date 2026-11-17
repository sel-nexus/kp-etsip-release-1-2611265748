"""Exercise user administration against an isolated Mongo replica set."""
import asyncio
import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient
from conftest import PASSWORD
from app.main import create_app

PAYLOAD = {"name": "Example User", "email": "Example@ketsip.local", "role": "Engineer", "portfolioAccess": [],
           "status": "Active", "managerName": None, "vendorIndicator": False, "password": "NewPassword123!"}


async def login(client, email="admin@ketsip.local", password=PASSWORD):
    """Obtain a real bearer token for a seeded or created account."""
    result = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert result.status_code == 200
    return {"Authorization": "Bearer " + result.json()["token"]}


async def test_crud_audit_duplicate_and_session_revocation(client, db):
    """Persist normalized records, preserve audit references and revoke changed sessions."""
    await db.users.update_one({"email": "admin@ketsip.local"}, {"$set": {"mustChangePassword": False}})
    auth = await login(client)
    portfolio = await db.portfolios.find_one({"name": "Payments"})
    data = {**PAYLOAD, "portfolioAccess": [str(portfolio["_id"])]}
    created = await client.post("/api/users", headers=auth, json=data)
    assert created.status_code == 201
    result = created.json()
    identifier = result["id"]
    assert result["email"] == "example@ketsip.local"
    assert "passwordHash" not in result and "tokenVersion" not in result and "password" not in result
    assert (await client.post("/api/users", headers=auth, json=data)).status_code == 409
    doc = await db.users.find_one({"_id": ObjectId(identifier)})
    assert doc["portfolioAccess"] == [portfolio["_id"]] and doc["passwordHash"] != data["password"]
    assert (await client.get(f"/api/users/{identifier}", headers=auth)).json()["id"] == identifier
    listed = await client.get("/api/users", headers=auth, params={"search": "EXAMPLE", "pageSize": 1})
    assert listed.status_code == 200 and listed.json()["total"] == 1
    assert (await client.get("/api/users", headers=auth, params={"search": ".*"})).json()["total"] == 0
    old = await login(client, "example@ketsip.local", "NewPassword123!")
    changed = {**data, "name": "Changed", "role": "Read Only", "password": "ChangedPassword123!"}
    response = await client.put(f"/api/users/{identifier}", headers=auth, json=changed)
    assert response.status_code == 200 and response.json()["name"] == "Changed"
    assert (await client.get("/api/auth/me", headers=old)).status_code == 401
    replacement = await login(client, "example@ketsip.local", "ChangedPassword123!")
    assert (await client.delete(f"/api/users/{identifier}", headers=auth)).status_code == 204
    assert (await client.get("/api/auth/me", headers=replacement)).status_code == 401
    doc = await db.users.find_one({"_id": ObjectId(identifier)})
    assert doc["status"] == "Inactive" and doc["tokenVersion"] == 2
    events = await db.audit_logs.find({"entityId": ObjectId(identifier), "entityType": "user"}).to_list(None)
    assert {"create", "edit", "roleChange", "delete"} <= {event["action"] for event in events}
    assert all("Password123" not in str(event) and "passwordHash" not in str(event) for event in events)


@pytest.mark.parametrize("change", [
    {"name": " "}, {"name": {"$ne": "x"}}, {"email": "bad"}, {"email": {"$ne": None}},
    {"role": "Root"}, {"status": "Deleted"}, {"password": "short"}, {"password": "x" * 73},
    {"vendorIndicator": "true"}, {"portfolioAccess": ["bad"]}, {"extra": 1},
])
async def test_invalid_payloads_do_not_write(client, db, change):
    """Reject malformed scalars, enums, credentials and unknown fields."""
    await db.users.update_one({"email": "admin@ketsip.local"}, {"$set": {"mustChangePassword": False}})
    auth = await login(client)
    count = await db.users.count_documents({})
    assert (await client.post("/api/users", headers=auth, json={**PAYLOAD, **change})).status_code == 422
    assert await db.users.count_documents({}) == count


async def test_guards_hidden_resources_and_missing_references(client, db):
    """Enforce live permissions, scope, self-protection and nonexistent IDs."""
    assert (await client.get("/api/users")).status_code == 401
    await db.users.update_one({"email": "admin@ketsip.local"}, {"$set": {"mustChangePassword": False}})
    auth = await login(client)
    admin = await db.users.find_one({"email": "admin@ketsip.local"})
    assert (await client.delete(f"/api/users/{admin['_id']}", headers=auth)).status_code == 409
    assert (await client.put(f"/api/users/{admin['_id']}", headers=auth, json={**PAYLOAD, "email": admin["email"]})).status_code == 409
    for method in ("get", "delete"):
        assert (await getattr(client, method)(f"/api/users/{ObjectId()}", headers=auth)).status_code == 404
    assert (await client.get("/api/users/bad", headers=auth)).status_code == 422
    assert (await client.post("/api/users", headers=auth, json={**PAYLOAD, "portfolioAccess": [str(ObjectId())]})).status_code == 409
    reader = await login(client, "readonly@ketsip.local")
    assert (await client.get("/api/users", headers=reader)).status_code == 403
    await db.roles.update_one({"name": "Administrator"}, {"$pull": {"permissions": "administer"}})
    assert (await client.get("/api/users", headers=auth)).status_code == 403


async def test_restricted_admin_cannot_view_or_assign_unrestricted_and_outside_accounts(client, db):
    """Enforce visibility on list, detail and mutation, not just portfolio options."""
    payments = await db.portfolios.find_one({"name": "Payments"})
    customer = await db.portfolios.find_one({"name": "Customer Platform"})
    await db.users.update_one({"email": "admin@ketsip.local"}, {"$set": {"mustChangePassword": False, "portfolioAccess": [payments["_id"]]}})
    auth = await login(client)
    executive = await db.users.find_one({"email": "executive@ketsip.local"})
    assert (await client.get(f"/api/users/{executive['_id']}", headers=auth)).status_code == 404
    assert (await client.delete(f"/api/users/{executive['_id']}", headers=auth)).status_code == 404
    items = (await client.get("/api/users", headers=auth)).json()["items"]
    assert str(executive["_id"]) not in [item["id"] for item in items]
    assert (await client.post("/api/users", headers=auth, json={**PAYLOAD, "role": "Executive"})).status_code == 403
    assert (await client.post("/api/users", headers=auth, json={**PAYLOAD, "portfolioAccess": [str(customer["_id"])]})).status_code == 403
    assert (await client.post("/api/users", headers=auth, json={**PAYLOAD, "portfolioAccess": [str(payments["_id"])]})).status_code == 201


async def test_user_reference_blocks_portfolio_deletion_and_audit_rolls_back(client, db, application, monkeypatch):
    """Preserve assignments on deletion and roll back user writes if auditing fails."""
    await db.users.update_one({"email": "admin@ketsip.local"}, {"$set": {"mustChangePassword": False}})
    auth = await login(client)
    portfolio = await db.portfolios.find_one({"name": "Payments"})
    await db.applications.delete_many({"portfolioId": portfolio["_id"]})
    assert (await client.delete(f"/api/portfolios/{portfolio['_id']}", headers=auth)).status_code == 409
    assert await db.portfolios.find_one({"_id": portfolio["_id"]})
    async def fail_audit(event, session=None):
        """Simulate a failed audit write within the actual Mongo transaction."""
        from pymongo.errors import OperationFailure
        raise OperationFailure("audit failed")
    monkeypatch.setattr(application.state.users.audit, "append", fail_audit)
    assert (await client.post("/api/users", headers=auth, json=PAYLOAD)).status_code == 503
    assert await db.users.find_one({"email": "example@ketsip.local"}) is None


@pytest.mark.parametrize("operation", ["demote", "deactivate"])
async def test_concurrent_last_admin_removal_is_serialized(application, client, db, operation):
    """Race two independently authenticated administrators against a shared guard."""
    await db.users.update_one({"email": "admin@ketsip.local"}, {"$set": {"mustChangePassword": False}})
    first = await login(client)
    created = await client.post("/api/users", headers=first, json={**PAYLOAD, "email": "second@ketsip.local", "role": "Administrator"})
    assert created.status_code == 201
    second_id = created.json()["id"]
    second = await login(client, "second@ketsip.local", "NewPassword123!")
    first_id = str((await db.users.find_one({"email": "admin@ketsip.local"}))["_id"])
    other_app = create_app(application.state.settings)
    async with other_app.router.lifespan_context(other_app):
        assert other_app.state.mongo is not application.state.mongo
        async with AsyncClient(transport=ASGITransport(app=other_app), base_url="http://test") as other:
            async def remove(http, headers, identifier, email):
                """Attempt a competing demotion or deactivation."""
                if operation == "deactivate":
                    return await http.delete(f"/api/users/{identifier}", headers=headers)
                return await http.put(f"/api/users/{identifier}", headers=headers, json={**PAYLOAD, "email": email, "role": "Read Only", "password": None})
            one, two = await asyncio.gather(remove(client, first, second_id, "second@ketsip.local"),
                                            remove(other, second, first_id, "admin@ketsip.local"))
    assert sorted([one.status_code, two.status_code]) in ([200, 403], [204, 403], [200, 409], [204, 409])
    assert await db.users.count_documents({"role": "Administrator", "status": "Active"}) == 1
