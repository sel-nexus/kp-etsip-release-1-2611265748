"""Exercise application services against the isolated real Mongo fixture."""
import pytest
from bson import ObjectId
from conftest import PASSWORD
from app.core.errors import DomainError
from app.core.seed import seed_database


async def session(client, application, email):
    """Authenticate through the real service before calling inventory logic."""
    response = await client.post('/api/auth/login', json={'email': email, 'password': PASSWORD})
    assert response.status_code == 200
    return await application.state.auth.authenticate(response.json()['token'])


async def test_service_scope_filters_details_and_boundaries(client, application, db):
    """Apply assignments and combined filters to actual persisted records."""
    leader = await session(client, application, 'leader@ketsip.local')
    service = application.state.applications
    payment = await db.portfolios.find_one({'name': 'Payments'})
    other = await db.applications.find_one({'portfolioId': {'$ne': payment['_id']}})
    page = await service.listing(leader, search='gateway', criticality='Critical', risk='High', lifecycle='Active', page_size=1)
    assert page.total == 1 and page.items[0].name == 'Payment Gateway'
    assert page.items[0].portfolioName == 'Payments'
    assert (await service.get(leader, page.items[0].id)).portfolioId == str(payment['_id'])
    assert (await service.listing(leader, search='.*')).total == 0
    assert (await service.listing(leader, portfolio_id=str(other['portfolioId']))).total == 0
    for identifier, status in [(str(other['_id']), 404), (str(ObjectId()), 404), ('bad', 422)]:
        with pytest.raises(DomainError) as error:
            await service.get(leader, identifier)
        assert error.value.status == status
    for page_number, size in [(0, 1), (1, 0), (1, 101)]:
        with pytest.raises(DomainError) as error:
            await service.listing(leader, page=page_number, page_size=size)
        assert error.value.status == 422


async def test_seed_repeatedly_retains_edits_and_portfolio_identity(application, db):
    """Seed exactly ten records and preserve renamed or edited records on restart."""
    assert await db.applications.count_documents({}) == 10
    record = await db.applications.find_one({'name': 'Payment Gateway'})
    await db.applications.update_one({'_id': record['_id']}, {'$set': {'name': 'Renamed gateway', 'qualityScore': 23}})
    await db.portfolios.update_one({'_id': record['portfolioId']}, {'$set': {'name': 'Renamed portfolio'}})
    await seed_database(db, application.state.settings)
    await seed_database(db, application.state.settings)
    assert await db.applications.count_documents({}) == 10
    saved = await db.applications.find_one({'_id': record['_id']})
    assert saved['name'] == 'Renamed gateway' and saved['qualityScore'] == 23
    assert saved['portfolioId'] == record['portfolioId']


async def test_service_permission_and_empty_scope(client, application, db):
    """Deny missing permissions and treat an empty restricted scope as no access."""
    leader = await session(client, application, 'leader@ketsip.local')
    service = application.state.applications
    empty = leader.user.model_copy(update={'portfolioAccess': []})
    assert (await service.listing(type(leader)(empty, leader.token_version))).total == 0
    denied = leader.user.model_copy(update={'permissions': []})
    with pytest.raises(DomainError) as error:
        await service.listing(type(leader)(denied, leader.token_version))
    assert error.value.status == 403
