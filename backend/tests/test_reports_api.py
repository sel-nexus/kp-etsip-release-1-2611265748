"""Exercise report endpoints against isolated real MongoDB inventory."""
import csv
import io
import pytest
from bson import ObjectId
from conftest import PASSWORD
from app.features.reports.schemas import APPLICATION_COLUMNS, PORTFOLIO_COLUMNS


async def auth(client, email):
    """Sign in with a seeded role."""
    response = await client.post('/api/auth/login', json={'email': email, 'password': PASSWORD})
    assert response.status_code == 200
    return {'Authorization': 'Bearer ' + response.json()['token']}


def rows(response):
    """Parse the actual response as CSV."""
    return list(csv.DictReader(io.StringIO(response.text)))


async def test_application_filters_pagination_full_export_and_audit(client, db):
    """CSV contains every filtered row and exactly one safe export event."""
    headers = await auth(client, 'executive@ketsip.local')
    payments = await db.portfolios.find_one({'name': 'Payments'})
    for filters, expected in [({'search': 'gateway'}, 1), ({'portfolioId': str(payments['_id'])}, 4),
                              ({'criticality': 'Critical'}, 2), ({'riskLevel': 'High'}, 3), ({'lifecycleStatus': 'Retired'}, 1)]:
        response = await client.get('/api/reports/applications', headers=headers, params=filters)
        assert response.status_code == 200 and response.json()['total'] == expected
    response = await client.get('/api/reports/applications', headers=headers, params={'page': 2, 'pageSize': 1})
    assert response.status_code == 200 and response.json()['total'] == 10 and len(response.json()['items']) == 1
    before = await db.audit_logs.count_documents({'action': 'export'})
    response = await client.get('/api/reports/applications', headers=headers, params={'format': 'csv', 'page': 2, 'pageSize': 1})
    assert response.status_code == 200 and response.headers['content-type'].startswith('text/csv')
    assert response.headers['content-disposition'] == 'attachment; filename="applications.csv"'
    assert len(rows(response)) == 10 and tuple(rows(response)[0]) == APPLICATION_COLUMNS
    event = await db.audit_logs.find_one({'action': 'export'})
    assert await db.audit_logs.count_documents({'action': 'export'}) == before + 1
    assert event['details'] == 'Application report export succeeded'
    assert PASSWORD not in str(event)


async def test_portfolio_filters_and_csv_columns(client, db):
    """Match inventory JSON for every portfolio filter and derived CSV value."""
    headers = await auth(client, 'executive@ketsip.local')
    portfolio = await db.portfolios.find_one({'name': 'Payments'})
    for filters in [{'search': 'PAYMENTS'}, {'status': portfolio['status']}, {'productArea': portfolio['productArea']}]:
        report = await client.get('/api/reports/portfolios', headers=headers, params=filters)
        inventory = await client.get('/api/portfolios', headers=headers, params=filters)
        assert report.status_code == 200 and report.json() == inventory.json()
    response = await client.get('/api/reports/portfolios', headers=headers, params={'format': 'csv', 'pageSize': 1})
    assert response.status_code == 200 and len(rows(response)) == 3
    assert tuple(rows(response)[0]) == PORTFOLIO_COLUMNS
    payment = next(row for row in rows(response) if row['name'] == 'Payments')
    assert payment['applicationCount'] == '4' and payment['qualityScore']
    empty = await client.get('/api/reports/portfolios', headers=headers, params={'format': 'csv', 'search': 'nonexistent'})
    assert empty.status_code == 200 and list(csv.reader(io.StringIO(empty.text))) == [list(PORTFOLIO_COLUMNS)]


async def test_scope_and_read_only_export_prohibition(client, db):
    """Intersect filters with assigned scope even when role permissions are edited."""
    leader = await auth(client, 'leader@ketsip.local')
    hidden = await db.portfolios.find_one({'name': 'Customer Platform'})
    for kind in ('applications', 'portfolios'):
        response = await client.get('/api/reports/' + kind, headers=leader, params={'format': 'csv'})
        assert response.status_code == 200 and 'Customer Platform' not in response.text
    restricted = await client.get('/api/reports/applications', headers=leader, params={'format': 'csv', 'portfolioId': str(hidden['_id'])})
    assert rows(restricted) == []
    readonly = await auth(client, 'readonly@ketsip.local')
    await db.roles.update_one({'name': 'Read Only'}, {'$addToSet': {'permissions': 'export'}})
    for kind in ('applications', 'portfolios'):
        assert (await client.get('/api/reports/' + kind, headers=readonly)).status_code == 200
        assert (await client.get('/api/reports/' + kind, headers=readonly, params={'format': 'csv'})).status_code == 403
    await db.users.update_one({'email': 'leader@ketsip.local'}, {'$set': {'portfolioAccess': []}})
    assert (await client.get('/api/reports/applications', headers=leader)).json()['total'] == 0


async def test_export_exceeds_page_limit_and_preserves_all_fields(client, db):
    """Export across multiple batches and compare every CSV column to inventory."""
    headers = await auth(client, 'executive@ketsip.local')
    original = await db.applications.find_one({'name': 'Payment Gateway'})
    for index in range(105):
        row = {**original, '_id': ObjectId(), 'name': f'Bulk report {index:03}', 'seedKey': f'bulk-report-{index}'}
        await db.applications.insert_one(row)
    params = {'search': 'Bulk report', 'page': 2, 'pageSize': 1}
    response = await client.get('/api/reports/applications', headers=headers, params={**params, 'format': 'csv'})
    assert response.status_code == 200
    data = rows(response)
    assert len(data) == 105 and len({row['name'] for row in data}) == 105
    page = await client.get('/api/reports/applications', headers=headers, params={'search': 'Bulk report', 'pageSize': 100})
    by_name = {item['name']: item for item in page.json()['items']}
    for row in data[:100]:
        assert row == {field: str(by_name[row['name']][field]) for field in APPLICATION_COLUMNS}
    filtered = await client.get('/api/reports/applications', headers=headers, params={'format': 'csv', 'search': 'Bulk report 104', 'riskLevel': original['riskLevel']})
    assert [row['name'] for row in rows(filtered)] == ['Bulk report 104']


async def test_formula_injection_and_filter_validation(client, db):
    """Quote dangerous user-entered names and reject invalid requests."""
    headers = await auth(client, 'executive@ketsip.local')
    application = await db.applications.find_one({'name': 'Payment Gateway'})
    await db.applications.update_one({'_id': application['_id']}, {'$set': {'name': '=SUM(1,2)'}})
    response = await client.get('/api/reports/applications', headers=headers, params={'format': 'csv', 'search': '=SUM'})
    assert response.status_code == 200 and rows(response)[0]['name'] == "'=SUM(1,2)"
    for kind in ('applications', 'portfolios'):
        assert (await client.get('/api/reports/' + kind)).status_code == 401
        assert (await client.get('/api/reports/' + kind, headers=headers, params={'format': 'pdf'})).status_code == 400
        assert (await client.get('/api/reports/' + kind, headers=headers, params={'pageSize': 101})).status_code == 422
        assert (await client.get('/api/reports/' + kind, headers=headers, params={'search': 'x' * 201})).status_code == 422
        assert (await client.get('/api/reports/' + kind, headers=headers, params={'search': '.*'})).json()['total'] == 0
    for params in [{'portfolioId': 'bad'}, {'criticality': 'bad'}, {'riskLevel': 'bad'}, {'lifecycleStatus': 'bad'}]:
        assert (await client.get('/api/reports/applications', headers=headers, params=params)).status_code == 422
    assert (await client.get('/api/reports/portfolios', headers=headers, params={'status': 'bad'})).status_code == 422
    await db.roles.update_one({'name': 'Executive'}, {'$set': {'permissions': ['export']}})
    assert (await client.get('/api/reports/applications', headers=headers, params={'format': 'csv'})).status_code == 403
