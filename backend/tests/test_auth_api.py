"""Verify exact HTTP auth contracts and persisted audit/security behavior."""
import pytest
from bson import ObjectId
from jose import jwt
from app.core.security import create_token
from conftest import PASSWORD


async def test_login_me_logout_contract_persistence_and_revocation(client, db):
    """Exercise all three real endpoints and re-query writes."""
    response = await client.post("/api/auth/login", json={"email": "executive@ketsip.local", "password": PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"token", "user"}
    assert body["user"]["role"] == "Executive"
    assert "passwordHash" not in response.text and "tokenVersion" not in response.text and PASSWORD not in response.text
    assert body["user"]["lastLogin"] is not None
    stored = await db.users.find_one({"_id": ObjectId(body["user"]["id"])})
    assert stored["lastLogin"] is not None
    token = body["token"]
    headers = {"Authorization": f"Bearer {token}"}
    current = await client.get("/api/auth/me", headers=headers)
    assert current.status_code == 200 and current.json() == body["user"]
    assert current.headers["cache-control"] == "no-store"
    logout = await client.post("/api/auth/logout", headers=headers)
    assert logout.status_code == 204 and logout.content == b""
    assert (await db.users.find_one({"_id": stored["_id"]}))["tokenVersion"] == 1
    assert (await client.get("/api/auth/me", headers=headers)).status_code == 401
    assert (await client.post("/api/auth/logout", headers=headers)).status_code == 401
    event = await db.audit_logs.find_one({"details": "Login succeeded"})
    assert event["userId"] == stored["_id"] and event["userName"] == stored["name"]


@pytest.mark.parametrize("email,inactive", [("missing@ketsip.local", False), ("executive@ketsip.local", False), ("executive@ketsip.local", True)])
async def test_bad_credentials_generic_response_and_audit_identity(client, db, email, inactive):
    """Keep unknown, incorrect and inactive credentials indistinguishable."""
    if inactive: await db.users.update_one({"email": email}, {"$set": {"status": "Inactive"}})
    response = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD if inactive else "WrongPassword123!"})
    assert response.status_code == 401 and response.json() == {"detail": "Invalid email or password"}
    assert response.headers["www-authenticate"] == "Bearer"
    event = await db.audit_logs.find_one({"details": "Login failed"})
    assert event["userName"] == ("Unknown user" if email.startswith("missing") else "Demo Executive")
    assert (event["userId"] is None) == email.startswith("missing")
    assert email not in str(event) and PASSWORD not in str(event)


@pytest.mark.parametrize("payload", [
    {}, {"email": "executive@ketsip.local"}, {"password": "secret-value"},
    {"email": "bad", "password": "secret-value"},
    {"email": {"$ne": None}, "password": "secret-value"},
    {"email": "executive@ketsip.local", "password": 123},
    {"email": "executive@ketsip.local", "password": ""},
    {"email": "executive@ketsip.local", "password": "secret-value" * 100},
    {"email": "x" * 255 + "@ketsip.local", "password": "secret-value"},
    {"email": "executive@ketsip.local", "password": "secret-value", "role": "Administrator"},
    {"email": "<script>alert(1)</script>@ketsip.local", "password": "secret-value"},
])
async def test_strict_invalid_payloads_reject_without_echoing_secrets_or_writes(client, db, payload):
    """Cover missing fields, types, unknown fields, operators and size bounds."""
    response = await client.post("/api/auth/login", json=payload)
    assert response.status_code == 422
    assert "secret-value" not in response.text and "<script>" not in response.text
    assert await db.audit_logs.count_documents({}) == 0
    assert (await db.users.find_one({"email": "executive@ketsip.local"}))["lastLogin"] is None


@pytest.mark.parametrize("path,method", [("/api/auth/me", "get"), ("/api/auth/logout", "post")])
@pytest.mark.parametrize("authorization", [None, "Basic not-a-bearer", "Bearer malformed.jwt", "Bearer"])
async def test_protected_endpoints_reject_missing_and_malformed_bearers(client, path, method, authorization):
    """Require a valid bearer for both current-user and logout endpoints."""
    response = await getattr(client, method)(path, headers={} if authorization is None else {"Authorization": authorization})
    assert response.status_code == 401


@pytest.mark.parametrize("case", ["expired", "forged", "wrong-algorithm", "inactive", "revoked", "deleted", "missing-role"])
async def test_http_security_branches_reject_invalid_sessions(client, application, db, case):
    """Exercise signature, expiry and live persistence checks through HTTP."""
    result = await client.post("/api/auth/login", json={"email": "executive@ketsip.local", "password": PASSWORD})
    token = result.json()["token"]
    user_id = ObjectId(result.json()["user"]["id"])
    config = application.state.settings
    if case in ("expired", "forged", "wrong-algorithm"):
        claims = jwt.get_unverified_claims(token)
        if case == "expired": claims["exp"] = 1
        token = jwt.encode(claims, "forged" if case == "forged" else config.JWT_SECRET.get_secret_value(),
                           algorithm="HS384" if case == "wrong-algorithm" else "HS256")
    elif case == "inactive": await db.users.update_one({"_id": user_id}, {"$set": {"status": "Inactive"}})
    elif case == "revoked": await db.users.update_one({"_id": user_id}, {"$inc": {"tokenVersion": 1}})
    elif case == "deleted": await db.users.delete_one({"_id": user_id})
    elif case == "missing-role": await db.roles.delete_one({"name": "Executive"})
    headers = {"Authorization": f"Bearer {token}"}
    assert (await client.get("/api/auth/me", headers=headers)).status_code == 401
    assert (await client.post("/api/auth/logout", headers=headers)).status_code == 401


async def test_me_reads_changed_role_permissions_and_bson_scope(client, db):
    """Ignore stale JWT role grants and serialize only current scoped identity."""
    result = await client.post("/api/auth/login", json={"email": "executive@ketsip.local", "password": PASSWORD})
    portfolio_id = ObjectId()
    await db.users.update_one({"email": "executive@ketsip.local"}, {"$set": {"role": "Read Only", "portfolioAccess": [portfolio_id]}})
    await db.roles.update_one({"name": "Read Only"}, {"$set": {"permissions": []}})
    response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {result.json()['token']}"})
    assert response.status_code == 200
    assert response.json()["role"] == "Read Only" and response.json()["permissions"] == []
    assert response.json()["portfolioAccess"] == [str(portfolio_id)]


async def test_admin_me_available_but_portfolios_require_password_change(client):
    """Expose required first-login state and enforce the business guard."""
    result = await client.post("/api/auth/login", json={"email": "admin@ketsip.local", "password": PASSWORD})
    assert result.status_code == 200 and result.json()["user"]["mustChangePassword"] is True
    headers = {"Authorization": f"Bearer {result.json()['token']}"}
    assert (await client.get("/api/auth/me", headers=headers)).status_code == 200
    assert (await client.get("/api/portfolios", headers=headers)).status_code == 403
    assert (await client.get("/api/applications", headers=headers)).status_code == 403
    for path in ("/api/users", "/api/audit-logs", "/api/dashboard/executive"):
        assert (await client.get(path, headers=headers)).status_code == 404
    assert (await client.post("/api/auth/change-password", headers=headers, json={})).status_code == 422
    assert (await client.post("/api/auth/logout", headers=headers)).status_code == 204


async def test_health_public_and_cors_preflight_are_safe(client):
    """Keep process liveness public and allow explicit configured browser origins."""
    response = await client.get("/api/health")
    assert response.status_code == 200 and response.json() == {"status": "ok"}
    allowed = await client.options("/api/auth/me", headers={"Origin": "http://test", "Access-Control-Request-Method": "GET"})
    assert allowed.status_code == 200 and allowed.headers["access-control-allow-origin"] == "http://test"
    denied = await client.options("/api/auth/me", headers={"Origin": "http://evil", "Access-Control-Request-Method": "GET"})
    assert denied.status_code == 400
