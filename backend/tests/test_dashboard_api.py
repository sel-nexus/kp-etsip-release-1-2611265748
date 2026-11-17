"""Exercise dashboard HTTP filters and authorization against real MongoDB."""
import pytest
from bson import ObjectId
from conftest import PASSWORD


async def bearer(client, email):
    """Obtain a bearer using the real login endpoint."""
    response = await client.post('/api/auth/login', json={'email': email, 'password': PASSWORD})
    assert response.status_code == 200
    return {'Authorization': 'Bearer ' + response.json()['token']}


async def test_dashboard_scoped_filters_and_exact_metrics(client, db):
    """Verify every scalar and per-portfolio value with a controlled data set."""
    await db.applications.delete_many({})
    await db.portfolios.delete_many({})
    p1, p2, p3 = ObjectId(), ObjectId(), ObjectId()
    await db.portfolios.insert_many([{'_id': p1, 'name': 'Alpha'}, {'_id': p2, 'name': 'Beta'}, {'_id': p3, 'name': 'Empty'}])
    await db.applications.insert_many([
        {'name': 'A', 'portfolioId': p1, 'productArea': 'Area A', 'riskLevel': 'High', 'qualityScore': 40, 'applicationHealthScore': 60, 'automationCoverage': 20, 'openCriticalDefects': 2},
        {'name': 'B', 'portfolioId': p1, 'productArea': 'Area B', 'riskLevel': 'Low', 'qualityScore': 41, 'applicationHealthScore': 61, 'automationCoverage': 21, 'openCriticalDefects': 3},
        {'name': 'C', 'portfolioId': p2, 'productArea': 'Area A', 'riskLevel': 'High', 'qualityScore': 70, 'applicationHealthScore': 80, 'automationCoverage': 90, 'openCriticalDefects': 7},
    ])
    auth = await bearer(client, 'executive@ketsip.local')
    response = await client.get('/api/dashboard/executive', headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert {key: body[key] for key in ('enterpriseQualityScore', 'applicationHealthScore', 'automationMaturityScore', 'openCriticalDefects', 'applicationsAtRisk', 'totalApplications', 'totalPortfolios')} == {
        'enterpriseQualityScore': 50, 'applicationHealthScore': 67, 'automationMaturityScore': 44, 'openCriticalDefects': 12, 'applicationsAtRisk': 2, 'totalApplications': 3, 'totalPortfolios': 3}
    assert body['portfolios'] == [
        {'id': str(p1), 'name': 'Alpha', 'applicationCount': 2, 'qualityScore': 41, 'highRiskCount': 1},
        {'id': str(p2), 'name': 'Beta', 'applicationCount': 1, 'qualityScore': 70, 'highRiskCount': 1},
        {'id': str(p3), 'name': 'Empty', 'applicationCount': 0, 'qualityScore': None, 'highRiskCount': 0},
    ]
    for params, expected in [({'portfolioId': str(p1)}, (2, 1, 41)), ({'productArea': 'Area A'}, (2, 2, 55)),
                             ({'riskLevel': 'Low'}, (1, 1, 41)), ({'portfolioId': str(p1), 'productArea': 'Area A', 'riskLevel': 'High'}, (1, 1, 40)),
                             ({'portfolioId': str(p3)}, (0, 0, None)), ({'productArea': 'missing'}, (0, 0, None))]:
        result = await client.get('/api/dashboard/executive', headers=auth, params=params)
        assert result.status_code == 200
        data = result.json()
        assert (data['totalApplications'], data['totalPortfolios'], data['enterpriseQualityScore']) == expected
    await db.users.update_one({'email': 'executive@ketsip.local'}, {'$set': {'portfolioAccess': [p1]}})
    limited = (await client.get('/api/dashboard/executive', headers=auth)).json()
    assert limited['totalPortfolios'] == 1 and limited['totalApplications'] == 2
    hidden = (await client.get('/api/dashboard/executive', headers=auth, params={'portfolioId': str(p2)})).json()
    assert hidden['totalPortfolios'] == 0 and hidden['totalApplications'] == 0


async def test_dashboard_auth_guards_and_invalid_filters(client, db):
    """Reject missing, revoked, forced-change, no-view and invalid requests."""
    path = '/api/dashboard/executive'
    assert (await client.get(path)).status_code == 401
    assert (await client.get(path, headers={'Authorization': 'Bearer invalid'})).status_code == 401
    admin = await bearer(client, 'admin@ketsip.local')
    assert (await client.get(path, headers=admin)).status_code == 403
    await db.users.update_one({'email': 'admin@ketsip.local'}, {'$set': {'mustChangePassword': False}})
    for params in ({'portfolioId': 'invalid'}, {'riskLevel': 'Critical'}, {'productArea': ''}, {'productArea': 'x' * 2001}):
        assert (await client.get(path, headers=admin, params=params)).status_code == 422
    await db.roles.update_one({'name': 'Administrator'}, {'$set': {'permissions': []}})
    assert (await client.get(path, headers=admin)).status_code == 403
    await client.post('/api/auth/logout', headers=admin)
    assert (await client.get(path, headers=admin)).status_code == 401


@pytest.mark.parametrize('email', ['leader@ketsip.local', 'engineer@ketsip.local', 'readonly@ketsip.local'])
async def test_dashboard_empty_restricted_assignments(client, db, email):
    """No assignment grants no visible portfolios for restricted roles."""
    await db.users.update_one({'email': email}, {'$set': {'portfolioAccess': []}})
    response = await client.get('/api/dashboard/executive', headers=await bearer(client, email))
    assert response.status_code == 200
    body = response.json()
    assert body['totalApplications'] == body['totalPortfolios'] == 0 and body['portfolios'] == []
    assert body['enterpriseQualityScore'] is body['applicationHealthScore'] is body['automationMaturityScore'] is None
