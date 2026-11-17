"""Exercise portfolio service decisions with isolated real Mongo persistence."""
import pytest
from bson import ObjectId
from app.core.errors import DomainError
from app.core.seed import seed_database
from app.features.portfolios.schemas import PortfolioWrite
from conftest import PASSWORD


async def session(client, application, email):
    """Return an authenticated session obtained from the real login service."""
    response = await client.post('/api/auth/login', json={'email': email, 'password': PASSWORD})
    assert response.status_code == 200
    return await application.state.auth.authenticate(response.json()['token'])


async def test_service_mutation_duplicate_and_link_protection(client, application, db):
    """Persist service edits, reject duplicates and protect linked inventory."""
    await db.users.update_one({'email': 'admin@ketsip.local'}, {'$set': {'mustChangePassword': False}})
    admin = await session(client, application, 'admin@ketsip.local')
    service = application.state.portfolios
    payload = PortfolioWrite(name='New Portfolio', owner='Owner', productArea='Area', description='About', status='Active')
    created = await service.create(admin, payload)
    assert (await db.portfolios.find_one({'_id': ObjectId(created.id)}))['owner'] == 'Owner'
    with pytest.raises(DomainError) as duplicate:
        await service.create(admin, payload)
    assert duplicate.value.status == 409
    changed = await service.update(admin, created.id, payload.model_copy(update={'owner': 'New Owner'}))
    assert changed.owner == 'New Owner'
    assert (await db.portfolios.find_one({'_id': ObjectId(created.id)}))['owner'] == 'New Owner'
    await db.applications.insert_one({'name': 'Linked', 'portfolioId': ObjectId(created.id), 'qualityScore': 40,
        'productArea': 'Area', 'lifecycleStatus': 'Retired', 'riskLevel': 'Low'})
    with pytest.raises(DomainError) as conflict:
        await service.delete(admin, created.id)
    assert conflict.value.status == 409
    assert await db.portfolios.find_one({'_id': ObjectId(created.id)})
    await db.applications.delete_many({'portfolioId': ObjectId(created.id)})
    await service.delete(admin, created.id)
    assert await db.portfolios.find_one({'_id': ObjectId(created.id)}) is None
    with pytest.raises(DomainError) as missing:
        await service.get(admin, created.id)
    assert missing.value.status == 404


async def test_service_scope_rounding_pagination_and_validation(client, application, db):
    """Compute exact half-up mean and prevent access beyond assigned IDs."""
    leader = await session(client, application, 'leader@ketsip.local')
    service = application.state.portfolios
    visible = await service.listing(leader)
    assert visible.total == 1
    identifier = visible.items[0].id
    await db.applications.delete_many({'portfolioId': ObjectId(identifier)})
    for index, score in enumerate([40, 41]):
        await db.applications.insert_one({'name': f'Application {index}', 'portfolioId': ObjectId(identifier),
            'qualityScore': score, 'productArea': 'Area', 'lifecycleStatus': 'Active', 'riskLevel': 'High'})
    result = await service.get(leader, identifier)
    assert result.applicationCount == 2 and result.qualityScore == 41
    first = await service.linked(leader, identifier, 1, 1)
    assert first.total == 2 and len(first.items) == 1 and first.items[0].name == 'Application 0'
    other = await db.portfolios.find_one({'_id': {'$ne': ObjectId(identifier)}})
    with pytest.raises(DomainError) as hidden:
        await service.get(leader, str(other['_id']))
    assert hidden.value.status == 404
    with pytest.raises(DomainError) as invalid:
        await service.get(leader, 'invalid')
    assert invalid.value.status == 422
    for page, size in [(0, 25), (1, 0), (1, 101)]:
        with pytest.raises(DomainError) as bounds:
            await service.listing(leader, page=page, page_size=size)
        assert bounds.value.status == 422
    with pytest.raises(DomainError) as forbidden:
        await service.create(leader, PortfolioWrite(name='Denied'))
    assert forbidden.value.status == 403


async def test_seed_is_idempotent_and_does_not_reset_changed_assignments(client, application, db):
    """Rerun seeding without overwriting existing inventory or scoped-user changes."""
    assert await db.portfolios.count_documents({}) == 3
    portfolio = await db.portfolios.find_one({'name': 'Payments'})
    await db.portfolios.update_one({'_id': portfolio['_id']}, {'$set': {'name': 'Renamed Payments', 'owner': 'Edited owner'}})
    await db.users.update_one({'email': 'leader@ketsip.local'}, {'$set': {'portfolioAccess': []}})
    await seed_database(db, application.state.settings)
    await seed_database(db, application.state.settings)
    assert await db.portfolios.count_documents({}) == 3
    assert (await db.portfolios.find_one({'_id': portfolio['_id']}))['owner'] == 'Edited owner'
    assert (await db.users.find_one({'email': 'leader@ketsip.local'}))['portfolioAccess'] == []
    assert (await db.users.find_one({'email': 'engineer@ketsip.local'}))['portfolioAccess'] == [portfolio['_id']]
