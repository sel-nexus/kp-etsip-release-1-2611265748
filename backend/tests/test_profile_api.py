"""Verify profile HTTP contracts, validation, revocation and persistence."""
import asyncio
import pytest
from bson import ObjectId
from app.core.access import get_business_session
from app.core.errors import DomainError
from app.core.security import create_token, verify_password
from conftest import PASSWORD

NEW = "ReplacementPassword123!"


async def login_headers(client, email="admin@ketsip.local", password=PASSWORD):
    """Authenticate through HTTP and retain the actual server bearer."""
    result = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert result.status_code == 200
    return {"Authorization": f"Bearer {result.json()['token']}"}, result.json()


async def test_forced_change_preferences_revocation_and_fresh_login(client, application, db):
    """Exercise allowed identity operations and deny business access until rotation."""
    headers, first = await login_headers(client)
    other_headers, _ = await login_headers(client)
    session = await application.state.auth.authenticate(first["token"])
    with pytest.raises(DomainError, match="Password change required"):
        await get_business_session(session)
    assert (await client.get("/api/auth/me", headers=headers)).status_code == 200
    preference = await client.put("/api/auth/profile", headers=headers, json={"defaultLandingPage": "applications"})
    assert preference.status_code == 200 and preference.json()["mustChangePassword"]
    assert preference.json()["defaultLandingPage"] == "applications"
    assert "passwordHash" not in preference.text and "tokenVersion" not in preference.text
    changed = await client.post("/api/auth/change-password", headers=headers,
                                json={"currentPassword": PASSWORD, "newPassword": NEW})
    assert changed.status_code == 204 and changed.content == b""
    stored = await db.users.find_one({"_id": ObjectId(first["user"]["id"])})
    assert not stored["mustChangePassword"] and stored["tokenVersion"] == 1
    assert await verify_password(NEW, stored["passwordHash"])
    for old in (headers, other_headers):
        assert (await client.get("/api/auth/me", headers=old)).status_code == 401
        assert (await client.put("/api/auth/profile", headers=old, json={"defaultLandingPage": "dashboard"})).status_code == 401
        assert (await client.post("/api/auth/logout", headers=old)).status_code == 401
        assert (await client.post("/api/auth/change-password", headers=old,
                                  json={"currentPassword": PASSWORD, "newPassword": NEW})).status_code == 401
    denied = await client.post("/api/auth/login", json={"email": first["user"]["email"], "password": PASSWORD})
    assert denied.status_code == 401
    fresh_headers, fresh = await login_headers(client, password=NEW)
    assert not fresh["user"]["mustChangePassword"] and fresh["user"]["defaultLandingPage"] == "applications"
    assert await get_business_session(await application.state.auth.authenticate(fresh["token"]))
    assert (await client.post("/api/auth/logout", headers=fresh_headers)).status_code == 204
    edits = await db.audit_logs.find({"action": "edit"}).to_list(None)
    assert len(edits) == 2
    for secret in (PASSWORD, NEW, stored["passwordHash"], first["token"]):
        assert secret not in str(edits)


@pytest.mark.parametrize("landing", ["dashboard", "applications"])
async def test_preference_persists_after_relogin_for_read_only_without_generic_edit(client, db, landing):
    """Keep self-service available independently of business permissions."""
    await db.roles.update_one({"name": "Read Only"}, {"$set": {"permissions": []}})
    headers, result = await login_headers(client, "readonly@ketsip.local")
    response = await client.put("/api/auth/profile", headers=headers, json={"defaultLandingPage": landing})
    assert response.status_code == 200 and response.json()["permissions"] == []
    assert (await db.users.find_one({"_id": ObjectId(result["user"]["id"])}))["defaultLandingPage"] == landing
    assert (await client.post("/api/auth/logout", headers=headers)).status_code == 204
    _, fresh = await login_headers(client, "readonly@ketsip.local")
    assert fresh["user"]["defaultLandingPage"] == landing


@pytest.mark.parametrize("payload", [
    {}, {"currentPassword": PASSWORD}, {"newPassword": NEW},
    {"currentPassword": "", "newPassword": NEW},
    {"currentPassword": 123, "newPassword": NEW},
    {"currentPassword": {"$ne": None}, "newPassword": NEW},
    {"currentPassword": "x" * 73, "newPassword": NEW},
    {"currentPassword": PASSWORD, "newPassword": ""},
    {"currentPassword": PASSWORD, "newPassword": "x" * 11},
    {"currentPassword": PASSWORD, "newPassword": "x" * 73},
    {"currentPassword": PASSWORD, "newPassword": "é" * 37},
    {"currentPassword": PASSWORD, "newPassword": 123},
    {"currentPassword": PASSWORD, "newPassword": None},
    {"currentPassword": PASSWORD, "newPassword": NEW, "mustChangePassword": False},
])
async def test_password_invalid_payloads_have_no_write_and_no_secret_echo(client, db, payload):
    """Cover each missing field, strict types, unknown fields and byte limits."""
    headers, result = await login_headers(client)
    before = await db.users.find_one({"_id": ObjectId(result["user"]["id"])})
    response = await client.post("/api/auth/change-password", headers=headers, json=payload)
    assert response.status_code == 422
    assert PASSWORD not in response.text and NEW not in response.text
    assert await db.users.find_one({"_id": before["_id"]}) == before
    assert await db.audit_logs.count_documents({"action": "edit"}) == 0


@pytest.mark.parametrize("payload", [{}, {"defaultLandingPage": ""}, {"defaultLandingPage": "profile"},
    {"defaultLandingPage": None}, {"defaultLandingPage": 1}, {"defaultLandingPage": {"$ne": None}},
    {"defaultLandingPage": "x" * 10000}, {"defaultLandingPage": "<script>alert(1)</script>"},
    {"defaultLandingPage": "dashboard", "role": "Administrator"}])
async def test_profile_invalid_payloads_cannot_change_identity(client, db, payload):
    """Reject operator injection and arbitrary account edits at the schema boundary."""
    headers, result = await login_headers(client)
    before = await db.users.find_one({"_id": ObjectId(result["user"]["id"])})
    response = await client.put("/api/auth/profile", headers=headers, json=payload)
    assert response.status_code == 422 and "<script>" not in response.text
    assert await db.users.find_one({"_id": before["_id"]}) == before
    assert await db.audit_logs.count_documents({"action": "edit"}) == 0


@pytest.mark.parametrize("new", ["x" * 12, "x" * 72, "é" * 6, "é" * 36])
async def test_new_password_exact_utf8_boundaries_are_accepted(client, new):
    """Accept inclusive byte bounds rather than JavaScript/Python character counts."""
    headers, _ = await login_headers(client)
    response = await client.post("/api/auth/change-password", headers=headers, json={"currentPassword": PASSWORD, "newPassword": new})
    assert response.status_code == 204
    await login_headers(client, password=new)


@pytest.mark.parametrize("current,new,status,message", [
    ("IncorrectPassword123!", NEW, 400, "Current password is incorrect"),
    (PASSWORD, PASSWORD, 422, "New password must differ from current password"),
])
async def test_password_semantic_failures_preserve_session(client, db, current, new, status, message):
    """Reject incorrect credentials and reuse without silently signing the user out."""
    headers, result = await login_headers(client)
    before = await db.users.find_one({"_id": ObjectId(result["user"]["id"])})
    response = await client.post("/api/auth/change-password", headers=headers, json={"currentPassword": current, "newPassword": new})
    assert response.status_code == status and response.json() == {"detail": message}
    assert await db.users.find_one({"_id": before["_id"]}) == before
    assert (await client.get("/api/auth/me", headers=headers)).status_code == 200
    assert await db.audit_logs.count_documents({"action": "edit"}) == 0


@pytest.mark.parametrize("case", ["missing", "malformed", "expired", "inactive", "deleted", "revoked"])
async def test_both_profile_endpoints_reject_invalid_sessions(client, application, db, case):
    """Require active live bearer state for every profile mutation."""
    headers, result = await login_headers(client)
    selector = {"_id": ObjectId(result["user"]["id"])}
    if case == "missing": headers = {}
    elif case == "malformed": headers = {"Authorization": "Bearer not.a.jwt"}
    elif case == "expired":
        from jose import jwt
        claims = jwt.get_unverified_claims(result["token"])
        claims["exp"] = 1
        token = jwt.encode(claims, application.state.settings.JWT_SECRET.get_secret_value(), algorithm="HS256")
        headers = {"Authorization": f"Bearer {token}"}
    elif case == "inactive": await db.users.update_one(selector, {"$set": {"status": "Inactive"}})
    elif case == "deleted": await db.users.delete_one(selector)
    else: await db.users.update_one(selector, {"$inc": {"tokenVersion": 1}})
    response = await client.put("/api/auth/profile", headers=headers, json={"defaultLandingPage": "dashboard"})
    assert response.status_code == 401
    response = await client.post("/api/auth/change-password", headers=headers, json={"currentPassword": PASSWORD, "newPassword": NEW})
    assert response.status_code == 401
    assert await db.audit_logs.count_documents({"action": "edit"}) == 0


async def test_http_concurrent_password_changes_only_one_succeeds(client, db):
    """Race actual HTTP requests and verify one durable version increment."""
    headers, result = await login_headers(client)
    responses = await asyncio.gather(*[
        client.post("/api/auth/change-password", headers=headers, json={"currentPassword": PASSWORD, "newPassword": new})
        for new in (NEW, "OtherReplacement123!")
    ])
    assert sorted(response.status_code for response in responses) == [204, 401]
    stored = await db.users.find_one({"_id": ObjectId(result["user"]["id"])})
    assert stored["tokenVersion"] == 1 and not stored["mustChangePassword"]
    assert await db.audit_logs.count_documents({"action": "edit"}) == 1


async def test_profile_put_cors_preflight_is_allowed(client):
    """Permit the newly wired method only for configured browser origins."""
    response = await client.options("/api/auth/profile", headers={"Origin": "http://test", "Access-Control-Request-Method": "PUT"})
    assert response.status_code == 200 and response.headers["access-control-allow-origin"] == "http://test"
