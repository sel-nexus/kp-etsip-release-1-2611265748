"""Exercise application writes and portfolio integrity against real MongoDB."""
import asyncio
from bson import ObjectId
import pytest
from httpx import ASGITransport, AsyncClient
from conftest import PASSWORD


async def login(client, email):
    """Authenticate a seeded user."""
    result = await client.post('/api/auth/login', json={'email': email, 'password': PASSWORD})
    assert result.status_code == 200
    return {'Authorization': 'Bearer ' + result.json()['token']}


def payload(portfolio, name='New app'):
    """Build a complete valid inventory mutation."""
    return {'name': name, 'description': 'Description', 'portfolioId': str(portfolio), 'productArea': 'Area',
            'businessOwner': 'Business', 'technologyOwner': 'Tech', 'etsOwner': 'ETS', 'criticality': 'High',
            'tier': 2, 'lifecycleStatus': 'Active', 'technologyStack': 'Python', 'repositoryLink': 'https://example.com/repo',
            'pipelineLink': None, 'applicationHealthScore': 80, 'qualityScore': 75, 'automationCoverage': 60,
            'unitTestCoverage': 50, 'openDefects': 4, 'openCriticalDefects': 1, 'riskLevel': 'Medium'}


async def test_crud_permissions_scope_and_audit(client, db):
    """Persist complete records, enforce scope and audit successful changes."""
    await db.users.update_one({'email': 'admin@ketsip.local'}, {'$set': {'mustChangePassword': False}})
    admin = await login(client, 'admin@ketsip.local')
    engineer = await login(client, 'engineer@ketsip.local')
    reader = await login(client, 'readonly@ketsip.local')
    parent = await db.portfolios.find_one({'name': 'Payments'})
    hidden = await db.portfolios.find_one({'name': 'Customer Platform'})
    body = payload(parent['_id'])
    assert (await client.post('/api/applications', json=body)).status_code == 401
    assert (await client.post('/api/applications', headers=reader, json=body)).status_code == 403
    assert (await client.post('/api/applications', headers=engineer, json=payload(hidden['_id']))).status_code == 404
    created = await client.post('/api/applications', headers=engineer, json=body)
    assert created.status_code == 201, created.text
    item = created.json()
    assert all(item[key] == value for key, value in body.items())
    path = '/api/applications/' + item['id']
    assert (await client.post('/api/applications', headers=engineer, json=body)).status_code == 409
    assert (await client.put(path, headers=engineer, json=payload(hidden['_id']))).status_code == 404
    changed = {**body, 'name': 'Edited app', 'qualityScore': 99}
    assert (await client.put(path, headers=engineer, json=changed)).status_code == 200
    assert (await client.get(path, headers=engineer)).json()['qualityScore'] == 99
    assert (await client.delete(path, headers=engineer)).status_code == 403
    assert (await client.delete(path, headers=admin)).status_code == 204
    assert await db.applications.find_one({'_id': ObjectId(item['id'])}) is None
    events = await db.audit_logs.find({'entityId': ObjectId(item['id'])}).to_list(None)
    assert [event['action'] for event in events] == ['create', 'edit', 'delete']


@pytest.mark.parametrize('field,value', [('name', '  '), ('tier', 5), ('qualityScore', 101), ('openDefects', -1),
    ('unitTestCoverage', True), ('criticality', 'bad'), ('riskLevel', 'Critical'), ('lifecycleStatus', 'bad'),
    ('portfolioId', 'bad'), ('repositoryLink', 'javascript:alert(1)'), ('pipelineLink', 'https://x:y@example.com')])
async def test_invalid_fields_never_persist(client, db, field, value):
    """Reject each invalid field before writing."""
    auth = await login(client, 'engineer@ketsip.local')
    parent = await db.portfolios.find_one({'name': 'Payments'})
    body = payload(parent['_id'])
    body[field] = value
    assert (await client.post('/api/applications', headers=auth, json=body)).status_code == 422
    assert await db.applications.find_one({'name': 'New app'}) is None


@pytest.mark.parametrize('reassign', [False, True])
async def test_concurrent_reference_and_delete_leave_no_orphan(application, client, db, reassign):
    """Race independent HTTP clients and check persisted references after both finish."""
    await db.users.update_one({'email': 'admin@ketsip.local'}, {'$set': {'mustChangePassword': False}})
    auth = await login(client, 'admin@ketsip.local')
    created = await client.post('/api/portfolios', headers=auth, json={'name': 'Race parent', 'owner': '', 'description': '', 'productArea': '', 'status': 'Active'})
    assert created.status_code == 201
    target = created.json()['id']
    if reassign:
        existing = await db.applications.find_one({'name': 'Payment Gateway'})
        path = '/api/applications/' + str(existing['_id'])
    async with AsyncClient(transport=ASGITransport(app=application), base_url='http://test') as a, AsyncClient(transport=ASGITransport(app=application), base_url='http://test') as b:
        write = a.put(path, headers=auth, json=payload(target, 'Race application')) if reassign else a.post('/api/applications', headers=auth, json=payload(target, 'Race application'))
        result, deletion = await asyncio.gather(write, b.delete('/api/portfolios/' + target, headers=auth))
    assert (result.status_code, deletion.status_code) in [(200 if reassign else 201, 409), (404, 204)]
    assert not (await db.applications.count_documents({'portfolioId': ObjectId(target)}) and not await db.portfolios.find_one({'_id': ObjectId(target)}))
