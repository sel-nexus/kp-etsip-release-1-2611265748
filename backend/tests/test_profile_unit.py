"""Exercise profile services and atomic mutations against isolated real Mongo."""
import asyncio
import pytest
from bson import ObjectId
from app.core.access import get_business_session
from app.core.errors import DomainError
from app.core.security import verify_password
from app.features.auth.schemas import LoginRequest
from app.features.profile.schemas import ChangePasswordRequest, ProfileRequest
from conftest import PASSWORD

NEW = "ReplacementPassword123!"


async def session_for(application, email="admin@ketsip.local"):
    """Establish a live service session through the existing auth flow."""
    login = await application.state.auth.login(LoginRequest(email=email, password=PASSWORD))
    return await application.state.auth.authenticate(login.token), login.token


@pytest.mark.parametrize("landing", ["dashboard", "applications"])
async def test_preference_persists_without_changing_credentials_or_scope(application, db, landing):
    """Verify safe public output, audit and a real persisted preference."""
    session, token = await session_for(application)
    before = await db.users.find_one({"_id": ObjectId(session.user.id)})
    result = await application.state.profile.update_profile(session, ProfileRequest(defaultLandingPage=landing))
    stored = await db.users.find_one({"_id": before["_id"]})
    assert result.defaultLandingPage == stored["defaultLandingPage"] == landing
    assert stored["passwordHash"] == before["passwordHash"] and stored["tokenVersion"] == 0
    assert result.mustChangePassword and result.portfolioAccess == session.user.portfolioAccess
    assert "passwordHash" not in result.model_dump() and "tokenVersion" not in result.model_dump()
    assert (await application.state.auth.authenticate(token)).user.defaultLandingPage == landing
    assert await db.audit_logs.count_documents({"action": "edit", "details": "Landing preference updated"}) == 1


async def test_password_rotation_persists_hash_revokes_tokens_and_releases_guard(application, db):
    """Require new login and verify the mandatory-change state is actually cleared."""
    session, token = await session_for(application)
    with pytest.raises(DomainError, match="Password change required"):
        await get_business_session(session)
    await application.state.profile.change_password(session, ChangePasswordRequest(currentPassword=PASSWORD, newPassword=NEW))
    stored = await db.users.find_one({"_id": ObjectId(session.user.id)})
    assert stored["tokenVersion"] == 1 and not stored["mustChangePassword"]
    assert stored["passwordHash"] != NEW and await verify_password(NEW, stored["passwordHash"])
    assert not await verify_password(PASSWORD, stored["passwordHash"])
    with pytest.raises(DomainError):
        await application.state.auth.authenticate(token)
    login = await application.state.auth.login(LoginRequest(email=session.user.email, password=NEW))
    assert await get_business_session(await application.state.auth.authenticate(login.token))
    event = await db.audit_logs.find_one({"action": "edit"})
    assert event["entityId"] == stored["_id"] and event["userName"] == session.user.name
    for secret in (PASSWORD, NEW, stored["passwordHash"], token):
        assert secret not in str(event)


@pytest.mark.parametrize("current,new,status", [("WrongPassword123!", NEW, 400), (PASSWORD, PASSWORD, 422)])
async def test_password_rejection_does_not_mutate_or_audit(application, db, current, new, status):
    """Reject incorrect current credentials and reuse before writing."""
    session, _ = await session_for(application)
    before = await db.users.find_one({"_id": ObjectId(session.user.id)})
    with pytest.raises(DomainError) as failure:
        await application.state.profile.change_password(session, ChangePasswordRequest(currentPassword=current, newPassword=new))
    assert failure.value.status == status
    assert await db.users.find_one({"_id": before["_id"]}) == before
    assert await db.audit_logs.count_documents({"action": "edit"}) == 0


@pytest.mark.parametrize("change", ["deleted", "inactive", "revoked"])
async def test_stale_service_session_cannot_update_preferences_or_password(application, db, change):
    """Reject identity changes after authentication at the write boundary."""
    session, _ = await session_for(application)
    selector = {"_id": ObjectId(session.user.id)}
    if change == "deleted":
        await db.users.delete_one(selector)
    elif change == "inactive":
        await db.users.update_one(selector, {"$set": {"status": "Inactive"}})
    else:
        await db.users.update_one(selector, {"$inc": {"tokenVersion": 1}})
    with pytest.raises(DomainError) as failure:
        await application.state.profile.update_profile(session, ProfileRequest(defaultLandingPage="applications"))
    assert failure.value.status == 401
    with pytest.raises(DomainError) as failure:
        await application.state.profile.change_password(session, ChangePasswordRequest(currentPassword=PASSWORD, newPassword=NEW))
    assert failure.value.status == 401
    assert await db.audit_logs.count_documents({"action": "edit"}) == 0


async def test_concurrent_password_changes_have_one_winner_and_one_safe_audit(application, db):
    """Exercise competing bcrypt work and real compare-and-version writes."""
    session, _ = await session_for(application)
    choices = [NEW, "AnotherReplacement123!"]
    results = await asyncio.gather(*[
        application.state.profile.change_password(session, ChangePasswordRequest(currentPassword=PASSWORD, newPassword=value))
        for value in choices
    ], return_exceptions=True)
    assert sum(result is None for result in results) == 1
    loser = next(result for result in results if result is not None)
    assert isinstance(loser, DomainError) and loser.status == 401
    stored = await db.users.find_one({"_id": ObjectId(session.user.id)})
    assert stored["tokenVersion"] == 1
    winner = choices[results.index(None)]
    assert await verify_password(winner, stored["passwordHash"])
    assert await db.audit_logs.count_documents({"action": "edit"}) == 1


async def test_atomic_password_write_rejects_changed_hash_and_logout_version(application, db):
    """Verify both independent compare predicates prevent stale credential writes."""
    session, _ = await session_for(application)
    repository = application.state.auth.repository
    stored = await repository.by_id(session.user.id)
    assert not await repository.change_password(session.user.id, 0, "stale-hash", stored["passwordHash"])
    await application.state.auth.logout(session)
    assert not await repository.change_password(session.user.id, 0, stored["passwordHash"], "never-written")
    assert (await repository.by_id(session.user.id))["passwordHash"] == stored["passwordHash"]
