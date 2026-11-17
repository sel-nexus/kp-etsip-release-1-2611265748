"""Exercise application HTTP reads using a real isolated Mongo database."""
import pytest
from bson import ObjectId
from conftest import PASSWORD


async def headers(client, email):
    """Log in through the public endpoint and return the real bearer."""
    response = await client.post('/api/auth/login', json={'email': email, 'password': PASSWORD})
    assert response.status_code == 200
    return {'Authorization': 'Bearer ' + response.json()['token']}


async def test_list_detail_filters_pagination_and_portfolio_linkage(client, db):
    """Verify all filters, current portfolio names and complete public details."""
    auth = await headers(client, 'executive@ketsip.local')
    portfolio = await db.portfolios.find_one({'name': 'Payments'})
    response = await client.get('/api/applications', headers=auth, params={
        'search': 'gateway', 'portfolioId': str(portfolio['_id']), 'criticality': 'Critical',
        'riskLevel': 'High', 'lifecycleStatus': 'Active', 'page': 1, 'pageSize': 1})
    assert response.status_code == 200
    body = response.json()
    assert body['total'] == 1 and body['page'] == 1 and body['pageSize'] == 1
    item = body['items'][0]
    assert item['name'] == 'Payment Gateway' and item['portfolioName'] == 'Payments'
    assert {'description', 'businessOwner', 'technologyOwner', 'etsOwner', 'technologyStack', 'repositoryLink',
            'pipelineLink', 'qualityScore', 'applicationHealthScore', 'automationCoverage', 'unitTestCoverage',
            'openDefects', 'openCriticalDefects', 'riskLevel', 'createdAt', 'updatedAt'} <= item.keys()
    detail = await client.get('/api/applications/' + item['id'], headers=auth)
    assert detail.status_code == 200 and detail.json() == item
    linked = await client.get('/api/portfolios/' + str(portfolio['_id']) + '/applications', headers=auth)
    assert linked.status_code == 200 and item['id'] in [row['id'] for row in linked.json()['items']]
    result = await client.get('/api/portfolios/' + str(portfolio['_id']), headers=auth)
    assert result.json()['applicationCount'] == linked.json()['total'] == 4
    second = await client.get('/api/applications', headers=auth, params={'page': 2, 'pageSize': 1})
    first = await client.get('/api/applications', headers=auth, params={'page': 1, 'pageSize': 1})
    assert second.json()['total'] == 10 and second.json()['items'][0]['id'] != first.json()['items'][0]['id']
    await db.portfolios.update_one({'_id': portfolio['_id']}, {'$set': {'name': 'Renamed'}})
    assert (await client.get('/api/applications/' + item['id'], headers=auth)).json()['portfolioName'] == 'Renamed'


@pytest.mark.parametrize('email,expected', [('executive@ketsip.local', 10), ('auditor@ketsip.local', 10),
    ('leader@ketsip.local', 4), ('engineer@ketsip.local', 4), ('readonly@ketsip.local', 4)])
async def test_role_scopes_and_invisible_detail(client, db, email, expected):
    """Honor unrestricted roles and assigned roles for both list and detail."""
    auth = await headers(client, email)
    result = await client.get('/api/applications', headers=auth)
    assert result.status_code == 200 and result.json()['total'] == expected
    hidden = await db.applications.find_one({'name': 'Customer Portal'})
    response = await client.get('/api/applications/' + str(hidden['_id']), headers=auth)
    assert response.status_code == (200 if expected == 10 else 404)
    if expected == 4:
        await db.users.update_one({'email': email}, {'$set': {'portfolioAccess': []}})
        assert (await client.get('/api/applications', headers=auth)).json()['total'] == 0
        assert (await client.get('/api/applications/' + str(hidden['_id']), headers=auth)).status_code == 404


async def test_auth_permission_forced_password_and_invalid_queries(client, db):
    """Reject unauthorized, malformed, oversized, and injection-shaped input."""
    assert (await client.get('/api/applications')).status_code == 401
    admin = await headers(client, 'admin@ketsip.local')
    assert (await client.get('/api/applications', headers=admin)).status_code == 403
    await db.users.update_one({'email': 'admin@ketsip.local'}, {'$set': {'mustChangePassword': False}})
    assert (await client.get('/api/applications', headers=admin)).json()['total'] == 10
    for query in ['page=0', 'pageSize=101', 'pageSize=0', 'criticality=bogus', 'riskLevel=Critical',
                  'lifecycleStatus=bad', 'portfolioId=bad', 'search=' + 'x' * 201]:
        assert (await client.get('/api/applications?' + query, headers=admin)).status_code == 422
    assert (await client.get('/api/applications/bad', headers=admin)).status_code == 422
    assert (await client.get('/api/applications/' + str(ObjectId()), headers=admin)).status_code == 404
    assert (await client.get('/api/applications', headers=admin, params={'search': '.*'})).json()['total'] == 0
    await db.roles.update_one({'name': 'Administrator'}, {'$set': {'permissions': []}})
    assert (await client.get('/api/applications', headers=admin)).status_code == 403


async def test_each_filter_and_restricted_privileged_role(client, db):
    """Intersect each filter with live assignments, even for privileged roles."""
    auth = await headers(client, 'executive@ketsip.local')
    payments = await db.portfolios.find_one({'name': 'Payments'})
    other = await db.portfolios.find_one({'name': 'Customer Platform'})
    for params, expected in [({'criticality': 'Critical'}, 2), ({'riskLevel': 'High'}, 3),
                             ({'lifecycleStatus': 'Retired'}, 1), ({'portfolioId': str(payments['_id'])}, 4),
                             ({'search': 'GATEWAY'}, 1)]:
        result = await client.get('/api/applications', headers=auth, params=params)
        assert result.status_code == 200 and result.json()['total'] == expected
    await db.users.update_one({'email': 'executive@ketsip.local'}, {'$set': {'portfolioAccess': [payments['_id']]}})
    assert (await client.get('/api/applications', headers=auth)).json()['total'] == 4
    assert (await client.get('/api/applications', headers=auth, params={'portfolioId': str(other['_id'])})).json()['total'] == 0
    hidden = await db.applications.find_one({'portfolioId': other['_id']})
    assert (await client.get('/api/applications/' + str(hidden['_id']), headers=auth)).status_code == 404
    assert (await client.get('/api/portfolios/' + str(other['_id']) + '/applications', headers=auth)).status_code == 404


async def test_malformed_and_revoked_tokens_do_not_reveal_inventory(client, db):
    """Reject malformed and revoked bearers on both list and detail endpoints."""
    row = await db.applications.find_one({})
    for path in ['/api/applications', '/api/applications/' + str(row['_id'])]:
        assert (await client.get(path, headers={'Authorization': 'Bearer invalid'})).status_code == 401
    auth = await headers(client, 'readonly@ketsip.local')
    assert (await client.post('/api/auth/logout', headers=auth)).status_code == 204
    assert (await client.get('/api/applications', headers=auth)).status_code == 401
