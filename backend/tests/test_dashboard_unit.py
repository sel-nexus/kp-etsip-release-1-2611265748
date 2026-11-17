"""Verify executive service calculations against isolated Mongo inventory."""
import pytest
from bson import ObjectId
from conftest import PASSWORD
from app.core.errors import DomainError
from app.features.dashboard.service import mean_half_up


async def login_session(client, application, email):
    """Authenticate a seeded user through the real session service."""
    response = await client.post('/api/auth/login', json={'email': email, 'password': PASSWORD})
    assert response.status_code == 200
    return await application.state.auth.authenticate(response.json()['token'])


@pytest.mark.parametrize('total,count,expected', [(0, 0, None), (0, 2, 0), (81, 2, 41), (80, 2, 40), (100, 3, 33), (101, 3, 34)])
def test_half_up_integer_means(total, count, expected):
    """Round ties upward and retain null for no observations."""
    assert mean_half_up(total, count) == expected


async def test_service_aggregates_real_inventory_and_empty_visible_portfolio(client, application, db):
    """Sum counts and defects and round each mean from exact integer totals."""
    await db.applications.delete_many({})
    await db.portfolios.delete_many({})
    first, empty = ObjectId(), ObjectId()
    await db.portfolios.insert_many([{'_id': first, 'name': 'One'}, {'_id': empty, 'name': 'Empty'}])
    await db.applications.insert_many([
        {'name': 'A', 'portfolioId': first, 'productArea': 'One', 'riskLevel': 'High', 'qualityScore': 40,
         'applicationHealthScore': 60, 'automationCoverage': 20, 'openCriticalDefects': 2},
        {'name': 'B', 'portfolioId': first, 'productArea': 'Two', 'riskLevel': 'Low', 'qualityScore': 41,
         'applicationHealthScore': 61, 'automationCoverage': 21, 'openCriticalDefects': 3},
    ])
    executive = await login_session(client, application, 'executive@ketsip.local')
    service = application.state.dashboard
    data = await service.executive(executive)
    assert (data.enterpriseQualityScore, data.applicationHealthScore, data.automationMaturityScore) == (41, 61, 21)
    assert (data.openCriticalDefects, data.applicationsAtRisk, data.totalApplications, data.totalPortfolios) == (5, 1, 2, 2)
    metrics = {item.name: item for item in data.portfolios}
    assert (metrics['One'].qualityScore, metrics['One'].highRiskCount, metrics['One'].applicationCount) == (41, 1, 2)
    assert metrics['Empty'].qualityScore is None and metrics['Empty'].applicationCount == 0
    filtered = await service.executive(executive, product_area='Two')
    assert (filtered.totalPortfolios, filtered.totalApplications, filtered.enterpriseQualityScore, filtered.applicationsAtRisk) == (1, 1, 41, 0)
    no_match = await service.executive(executive, risk='Medium')
    assert no_match.totalPortfolios == 0 and no_match.enterpriseQualityScore is None
    with pytest.raises(DomainError) as invalid:
        await service.executive(executive, portfolio_id='invalid')
    assert invalid.value.status == 422
    with pytest.raises(DomainError):
        await service.executive(executive, risk='invalid')


async def test_service_enforces_empty_assignments_and_permission(client, application, db):
    """Deny revoked view permission and treat restricted empty access as no scope."""
    await db.users.update_one({'email': 'leader@ketsip.local'}, {'$set': {'portfolioAccess': []}})
    leader = await login_session(client, application, 'leader@ketsip.local')
    data = await application.state.dashboard.executive(leader)
    assert data.totalPortfolios == data.totalApplications == 0
    assert data.enterpriseQualityScore is data.applicationHealthScore is data.automationMaturityScore is None
    await db.roles.update_one({'name': 'Portfolio Leader'}, {'$set': {'permissions': []}})
    denied = await login_session(client, application, 'leader@ketsip.local')
    with pytest.raises(DomainError) as error:
        await application.state.dashboard.executive(denied)
    assert error.value.status == 403
