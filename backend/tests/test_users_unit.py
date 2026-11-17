"""Exercise direct user service invariants with real Mongo persistence."""
import pytest
from app.core.errors import DomainError
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
