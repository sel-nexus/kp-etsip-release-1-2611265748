"""Exercise portfolio HTTP contracts against isolated native Mongo databases."""
import pytest
from bson import ObjectId
from conftest import PASSWORD

PAYLOAD = {'name': 'Inventory One', 'owner': 'Owner', 'description': 'Description', 'productArea': 'Area', 'status': 'Active'}


async def headers(client, email):
    """Authenticate a seeded user through the real HTTP boundary."""
    result = await client.post('/api/auth/login', json={'email': email, 'password': PASSWORD})
    assert result.status_code == 200
    return {'Authorization': 'Bearer ' + result.json()['token']}


async def test_crud_filters_uniqueness_and_persisted_requery(client, db):
    """Create, filter, edit, requery and delete using the exact public paths."""
    await db.users.update_one({'email': 'admin@ketsip.local'}, {'$set': {'mustChangePassword': False}})
    auth = await headers(client, 'admin@ketsip.local')
    response = await client.post('/api/portfolios', headers=auth, json=PAYLOAD)
    assert response.status_code == 201
    item = response.json()
    identifier = item['id']
    assert item['applicationCount'] == 0 and item['qualityScore'] is None
    assert (await db.portfolios.find_one({'_id': ObjectId(identifier)}))['description'] == 'Description'
    assert (await client.post('/api/portfolios', headers=auth, json=PAYLOAD)).status_code == 409
    found = await client.get('/api/portfolios', headers=auth, params={'search': 'inventory', 'status': 'Active', 'productArea': 'Area', 'page': 1, 'pageSize': 1})
    assert found.status_code == 200 and found.json()['total'] == 1 and found.json()['items'][0]['id'] == identifier
    assert (await client.get('/api/portfolios', headers=auth, params={'search': '.*'})).json()['total'] == 0
    changed = {**PAYLOAD, 'name': 'Renamed', 'status': 'Archived', 'owner': 'Another'}
    assert (await client.put(f'/api/portfolios/{identifier}', headers=auth, json=changed)).status_code == 200
    assert (await client.get(f'/api/portfolios/{identifier}', headers=auth)).json()['owner'] == 'Another'
    assert (await db.portfolios.find_one({'_id': ObjectId(identifier)}))['status'] == 'Archived'
    assert (await client.delete(f'/api/portfolios/{identifier}', headers=auth)).status_code == 204
    assert (await client.get(f'/api/portfolios/{identifier}', headers=auth)).status_code == 404
    assert await db.portfolios.find_one({'_id': ObjectId(identifier)}) is None


async def test_linked_apps_are_real_paginated_and_prevent_deletion(client, db):
    """Derive mean half-up, display stored linked records and reject deletion."""
    await db.users.update_one({'email': 'admin@ketsip.local'}, {'$set': {'mustChangePassword': False}})
    auth = await headers(client, 'admin@ketsip.local')
    portfolio = await db.portfolios.find_one({'name': 'Payments'})
    identifier = str(portfolio['_id'])
    await db.applications.delete_many({'portfolioId': portfolio['_id']})
    for name, score in [('Alpha', 50), ('Beta', 51)]:
        await db.applications.insert_one({'name': name, 'portfolioId': portfolio['_id'], 'qualityScore': score,
            'productArea': 'Payments', 'lifecycleStatus': 'Active', 'riskLevel': 'Medium'})
    detail = (await client.get(f'/api/portfolios/{identifier}', headers=auth)).json()
    assert detail['applicationCount'] == 2 and detail['qualityScore'] == 51
    linked = await client.get(f'/api/portfolios/{identifier}/applications', headers=auth, params={'pageSize': 1, 'page': 2})
    assert linked.status_code == 200 and linked.json()['total'] == 2 and linked.json()['items'][0]['name'] == 'Beta'
    assert (await client.delete(f'/api/portfolios/{identifier}', headers=auth)).status_code == 409
    assert await db.portfolios.find_one({'_id': portfolio['_id']})


async def test_visibility_permissions_and_live_role_changes(client, db):
    """Enforce role boundaries, assignment visibility and changing permissions."""
    leader = await headers(client, 'leader@ketsip.local')
    reader = await headers(client, 'readonly@ketsip.local')
    engineer = await headers(client, 'engineer@ketsip.local')
    payments = await db.portfolios.find_one({'name': 'Payments'})
    hidden = await db.portfolios.find_one({'name': 'Customer Platform'})
    pid, other = str(payments['_id']), str(hidden['_id'])
    assert (await client.get('/api/portfolios', headers=leader)).json()['total'] == 1
    for method, path in [('get', f'/api/portfolios/{other}'), ('get', f'/api/portfolios/{other}/applications'), ('delete', f'/api/portfolios/{other}')]:
        assert (await getattr(client, method)(path, headers=leader)).status_code == 404
    assert (await client.put(f'/api/portfolios/{pid}', headers=leader, json=PAYLOAD)).status_code == 200
    assert (await client.post('/api/portfolios', headers=leader, json=PAYLOAD)).status_code == 403
    assert (await client.delete(f'/api/portfolios/{pid}', headers=leader)).status_code == 403
    for auth in [reader, engineer]:
        assert (await client.put(f'/api/portfolios/{pid}', headers=auth, json=PAYLOAD)).status_code == 403
    await db.users.update_one({'email': 'leader@ketsip.local'}, {'$set': {'portfolioAccess': []}})
    assert (await client.get('/api/portfolios', headers=leader)).json()['total'] == 0
    assert (await client.get(f'/api/portfolios/{pid}', headers=leader)).status_code == 404
    await db.roles.update_one({'name': 'Read Only'}, {'$set': {'permissions': ['view', 'create', 'edit', 'delete']}})
    assert (await client.post('/api/portfolios', headers=reader, json=PAYLOAD)).status_code == 403
    assert (await client.delete(f'/api/portfolios/{pid}', headers=reader)).status_code == 403


@pytest.mark.parametrize('payload', [{}, {'name': ''}, {'name': '   '}, {'name': {'$ne': None}},
    {'name': 'x' * 201}, {'name': 'ok', 'status': 'Invalid'}, {'name': 'ok', 'owner': None},
    {'name': 'ok', 'qualityScore': 99}, {'name': 'ok', 'description': 'x' * 2001}])
async def test_invalid_write_rejected_without_persistence(client, db, payload):
    """Reject malformed or derived fields without modifying Mongo."""
    await db.users.update_one({'email': 'admin@ketsip.local'}, {'$set': {'mustChangePassword': False}})
    auth = await headers(client, 'admin@ketsip.local')
    count = await db.portfolios.count_documents({})
    assert (await client.post('/api/portfolios', headers=auth, json=payload)).status_code == 422
    assert await db.portfolios.count_documents({}) == count


async def test_auth_validation_and_duplicate_update(client, db):
    """Reject unauthenticated, forced-password, invalid IDs and query bounds."""
    assert (await client.get('/api/portfolios')).status_code == 401
    auth = await headers(client, 'admin@ketsip.local')
    assert (await client.get('/api/portfolios', headers=auth)).status_code == 403
    await db.users.update_one({'email': 'admin@ketsip.local'}, {'$set': {'mustChangePassword': False}})
    for query in ['page=0', 'pageSize=101', 'pageSize=0', 'status=Invalid', 'search=' + 'x' * 201]:
        assert (await client.get('/api/portfolios?' + query, headers=auth)).status_code == 422
    assert (await client.get('/api/portfolios/not-an-id', headers=auth)).status_code == 422
    assert (await client.get('/api/portfolios/' + str(ObjectId()), headers=auth)).status_code == 404
    one = await db.portfolios.find_one({'name': 'Payments'})
    assert (await client.put('/api/portfolios/' + str(one['_id']), headers=auth, json={**PAYLOAD, 'name': 'Customer Platform'})).status_code == 409
    assert (await db.portfolios.find_one({'_id': one['_id']}))['name'] == 'Payments'
