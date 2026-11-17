"""Exercise auth services and immutable guards against real isolated Mongo."""
from datetime import UTC, datetime, timedelta
from dataclasses import replace
import pytest
from bson import ObjectId
from jose import jwt
from pydantic import SecretStr
from app.core.access import get_business_session, portfolio_scope, require_permission
from app.core.errors import DomainError
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.core.seed import seed_database, ACCOUNTS, ROLE_PERMISSIONS
from app.features.auth.schemas import LoginRequest
from conftest import PASSWORD


async def test_login_persists_timestamp_signed_claims_and_safe_identity(application, db):
    """Verify a successful service call writes identity and audit state."""
    result = await application.state.auth.login(LoginRequest(email=" EXECUTIVE@KETSIP.LOCAL ", password=PASSWORD))
    stored = await db.users.find_one({"email": "executive@ketsip.local"})
    claims = decode_token(result.token, application.state.settings)
    assert claims.sub == result.user.id == claims.userId
    assert claims.role == "Executive" and claims.tokenVersion == 0
    assert 28795 <= claims.exp - claims.iat <= 28800
    assert stored["lastLogin"] is not None and result.user.lastLogin == stored["lastLogin"]
    assert "passwordHash" not in result.user.model_dump() and "tokenVersion" not in result.user.model_dump()
    event = await db.audit_logs.find_one({"action": "login"})
    assert event["userId"] == stored["_id"] and event["entityId"] == stored["_id"]
    assert event["details"] == "Login succeeded" and event["userName"] == stored["name"]


@pytest.mark.parametrize("email,password,inactive", [
    ("unknown@ketsip.local", PASSWORD, False),
    ("executive@ketsip.local", "IncorrectPassword!", False),
    ("executive@ketsip.local", PASSWORD, True),
])
async def test_failed_credentials_are_generic_audited_and_do_not_update_last_login(application, db, email, password, inactive):
    """Verify unknown, wrong-password and inactive attempts share a safe failure."""
    if inactive:
        await db.users.update_one({"email": email}, {"$set": {"status": "Inactive"}})
    with pytest.raises(DomainError, match="Invalid email or password") as failure:
        await application.state.auth.login(LoginRequest(email=email, password=password))
    assert failure.value.status == 401
    event = await db.audit_logs.find_one({"action": "login"})
    known = email != "unknown@ketsip.local"
    assert (event["userId"] is not None) == known
    assert event["userName"] == ("Demo Executive" if known else "Unknown user")
    assert event["details"] == "Login failed"
    assert email not in str(event) and password not in str(event) and "passwordHash" not in event
    stored = await db.users.find_one({"email": "executive@ketsip.local"})
    assert stored["lastLogin"] is None


async def test_logout_revokes_all_concurrent_sessions_and_persists_version(application, db):
    """Reject both previous tokens after one version increment."""
    service = application.state.auth
    first = await service.login(LoginRequest(email="executive@ketsip.local", password=PASSWORD))
    second = await service.login(LoginRequest(email="executive@ketsip.local", password=PASSWORD))
    assert first.token != second.token
    session = await service.authenticate(first.token)
    await service.logout(session)
    assert (await db.users.find_one({"_id": ObjectId(session.user.id)}))["tokenVersion"] == 1
    for token in (first.token, second.token):
        with pytest.raises(DomainError, match="Invalid or expired session"):
            await service.authenticate(token)
    with pytest.raises(DomainError):
        await service.logout(session)
    fresh = await service.login(LoginRequest(email="executive@ketsip.local", password=PASSWORD))
    assert (await service.authenticate(fresh.token)).token_version == 1


async def test_live_role_permissions_scope_and_status_override_old_claims(application, db):
    """Re-read role/permissions and user state on every authenticated request."""
    service = application.state.auth
    result = await service.login(LoginRequest(email="executive@ketsip.local", password=PASSWORD))
    portfolio = ObjectId()
    await db.users.update_one({"_id": ObjectId(result.user.id)}, {"$set": {"role": "Read Only", "portfolioAccess": [portfolio]}})
    await db.roles.update_one({"name": "Read Only"}, {"$set": {"permissions": []}})
    session = await service.authenticate(result.token)
    assert session.user.role == "Read Only" and session.user.permissions == []
    assert portfolio_scope(session) == [portfolio]
    await db.users.update_one({"_id": ObjectId(result.user.id)}, {"$set": {"status": "Inactive"}})
    with pytest.raises(DomainError):
        await service.authenticate(result.token)


@pytest.mark.parametrize("case", ["expired", "forged", "malformed", "missing-exp", "mismatch", "bad-id", "bool-version", "future-iat", "unknown-user", "extra"])
async def test_token_security_branches_reject_invalid_claims(application, db, case):
    """Reject malformed cryptographic and identity claims before granting access."""
    config = application.state.settings
    user = await db.users.find_one({"email": "executive@ketsip.local"})
    token = create_token(str(user["_id"]), user["role"], 0, config)
    payload = jwt.get_unverified_claims(token)
    key = config.JWT_SECRET.get_secret_value()
    if case == "expired": payload["exp"] = int((datetime.now(UTC) - timedelta(seconds=1)).timestamp())
    elif case == "forged": key = "forged-secret"
    elif case == "missing-exp": del payload["exp"]
    elif case == "mismatch": payload["userId"] = str(ObjectId())
    elif case == "bad-id": payload["sub"] = "not-an-id"
    elif case == "bool-version": payload["tokenVersion"] = True
    elif case == "future-iat": payload["iat"] += 3600
    elif case == "unknown-user": payload["sub"] = payload["userId"] = str(ObjectId())
    elif case == "extra": payload["password"] = "never-allowed"
    token = "not.a.jwt" if case == "malformed" else jwt.encode(payload, key, algorithm="HS256")
    with pytest.raises(DomainError) as failure:
        await application.state.auth.authenticate(token)
    assert failure.value.status == 401


async def test_missing_role_blocks_login_and_existing_session(application, db):
    """Fail closed when a current role no longer exists."""
    result = await application.state.auth.login(LoginRequest(email="executive@ketsip.local", password=PASSWORD))
    await db.roles.delete_one({"name": "Executive"})
    with pytest.raises(DomainError):
        await application.state.auth.authenticate(result.token)
    with pytest.raises(DomainError):
        await application.state.auth.login(LoginRequest(email="executive@ketsip.local", password=PASSWORD))
    assert await db.audit_logs.count_documents({"details": "Login failed"}) == 1


async def test_deleted_user_invalidates_existing_session(application, db):
    """Reject a signed bearer whose account no longer exists."""
    result = await application.state.auth.login(LoginRequest(email="executive@ketsip.local", password=PASSWORD))
    await db.users.delete_one({"_id": ObjectId(result.user.id)})
    with pytest.raises(DomainError):
        await application.state.auth.authenticate(result.token)


async def test_admin_forced_change_guard_and_identity_access(application):
    """Keep me/logout available while future business dependency denies access."""
    result = await application.state.auth.login(LoginRequest(email="admin@ketsip.local", password=PASSWORD))
    session = await application.state.auth.authenticate(result.token)
    assert session.user.mustChangePassword
    with pytest.raises(DomainError, match="Password change required"):
        await get_business_session(session)
    with pytest.raises(DomainError, match="Password change required"):
        require_permission(session, "view", "application")
    await application.state.auth.logout(session)


@pytest.mark.parametrize("role", list(ACCOUNTS))
async def test_scope_empty_semantics_and_immutable_role_boundaries(application, role):
    """Test each role independently of editable generic grants."""
    email = ACCOUNTS[role][0]
    result = await application.state.auth.login(LoginRequest(email=email, password=PASSWORD))
    session = await application.state.auth.authenticate(result.token)
    session = replace(session, user=session.user.model_copy(update={"mustChangePassword": False, "permissions": list(ROLE_PERMISSIONS["Administrator"])}))
    assert portfolio_scope(session) == (None if role in ("Administrator", "Executive", "Auditor") else [])
    assert await get_business_session(session) == session
    for permission, resource, allowed in [
        ("delete", "application", role == "Administrator"),
        ("administer", "administration", role == "Administrator"),
        ("create", "portfolio", role == "Administrator"),
        ("edit", "portfolio", role in ("Administrator", "Portfolio Leader")),
        ("edit", "application", role in ("Administrator", "Portfolio Leader", "Engineer")),
        ("export", "application", role != "Read Only"),
        ("view", "audit", role in ("Administrator", "Auditor")),
    ]:
        if allowed: require_permission(session, permission, resource)
        else:
            with pytest.raises(DomainError) as failure: require_permission(session, permission, resource)
            assert failure.value.status == 403
    restricted = replace(session, user=session.user.model_copy(update={"permissions": []}))
    with pytest.raises(DomainError): require_permission(restricted, "view", "application")


async def test_seed_is_insert_only_with_six_roles_and_users(application, db):
    """Retain edited account/role state and do not reset credential/version fields."""
    before = await db.users.find_one({"email": "admin@ketsip.local"})
    await db.users.update_one({"_id": before["_id"]}, {"$set": {"name": "Edited", "tokenVersion": 4, "mustChangePassword": False}})
    await db.roles.update_one({"name": "Executive"}, {"$set": {"permissions": []}})
    await seed_database(db, application.state.settings)
    assert await db.users.count_documents({}) == 6 and await db.roles.count_documents({}) == 6
    after = await db.users.find_one({"_id": before["_id"]})
    assert after["name"] == "Edited" and after["passwordHash"] == before["passwordHash"]
    assert after["tokenVersion"] == 4 and not after["mustChangePassword"]
    assert (await db.roles.find_one({"name": "Executive"}))["permissions"] == []
    assert await db.portfolios.count_documents({}) == 0


async def test_password_helpers_reject_truncation_wrong_and_corrupt_hashes():
    """Verify offloaded bcrypt behavior and UTF-8 byte bounds."""
    stored = await hash_password(PASSWORD)
    assert stored != PASSWORD and await verify_password(PASSWORD, stored)
    assert not await verify_password("WrongPassword123!", stored)
    assert not await verify_password(PASSWORD, "corrupt")
    assert not await verify_password("", stored)
    assert not await verify_password("é" * 37, stored)
    for password in ("short", "x" * 73, "é" * 37):
        with pytest.raises(ValueError): await hash_password(password)


async def test_login_compare_and_set_rejects_stale_version_without_last_login(application, db):
    """Exercise the real atomic login write with a stale revocation version."""
    user = await db.users.find_one({"email": "executive@ketsip.local"})
    assert await application.state.auth.repository.mark_login(str(user["_id"]), 99, user["passwordHash"]) is None
    assert (await db.users.find_one({"_id": user["_id"]}))["lastLogin"] is None
