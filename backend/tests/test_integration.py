"""Cross-feature HTTP journeys against the isolated real Mongo replica set."""
import csv
import io

from bson import ObjectId
from conftest import PASSWORD


async def login(client, email, password=PASSWORD):
    """Authenticate through the API and return the bearer and public identity."""
    response = await client.post('/api/auth/login', json={'email': email, 'password': password})
    assert response.status_code == 200, response.text
    return {'Authorization': 'Bearer ' + response.json()['token']}, response.json()['user']


async def admin_login(client):
    """Complete the seeded administrator's mandatory password rotation via HTTP."""
    original, _ = await login(client, 'admin@ketsip.local')
    changed = await client.post('/api/auth/change-password', headers=original,
                                json={'currentPassword': PASSWORD, 'newPassword': 'IntegrationAdminPassword123!'})
    assert changed.status_code == 204, changed.text
    assert (await client.get('/api/auth/me', headers=original)).status_code == 401
    return await login(client, 'admin@ketsip.local', 'IntegrationAdminPassword123!')


def application_payload(portfolio_id, name, quality=40, health=60, automation=20, defects=2, risk='High'):
    """Build a complete maintained application with deliberately measurable values."""
    return {'name': name, 'description': 'Integration inventory', 'portfolioId': str(portfolio_id),
            'productArea': 'Integration Area', 'businessOwner': 'Business', 'technologyOwner': 'Technology',
            'etsOwner': 'ETS', 'criticality': 'High', 'tier': 2, 'lifecycleStatus': 'Active',
            'technologyStack': 'Python', 'repositoryLink': 'https://example.com/repo', 'pipelineLink': None,
            'applicationHealthScore': health, 'qualityScore': quality, 'automationCoverage': automation,
            'unitTestCoverage': 50, 'openDefects': 4, 'openCriticalDefects': defects, 'riskLevel': risk}


def user_payload(portfolio_id, email='journey@ketsip.local'):
    """Build a scoped engineer account for the journey."""
    return {'name': 'Journey Engineer', 'email': email, 'role': 'Engineer',
            'portfolioAccess': [str(portfolio_id)], 'status': 'Active', 'managerName': None,
            'vendorIndicator': False, 'password': 'JourneyPassword123!'}


async def test_scoped_inventory_to_dashboard_reports_and_audit(client, db):
    """Carry real identities and records through inventory, insight, reports and audit."""
    admin, admin_user = await admin_login(client)
    portfolio_body = {'name': 'Integration Portfolio', 'owner': 'Owner', 'description': 'Journey',
                      'productArea': 'Integration Area', 'status': 'Active'}
    response = await client.post('/api/portfolios', headers=admin, json=portfolio_body)
    assert response.status_code == 201, response.text
    portfolio_id = response.json()['id']
    response = await client.post('/api/users', headers=admin, json=user_payload(portfolio_id))
    assert response.status_code == 201, response.text
    user_id = response.json()['id']
    engineer, identity = await login(client, 'journey@ketsip.local', 'JourneyPassword123!')
    assert identity['id'] == user_id and identity['portfolioAccess'] == [portfolio_id]

    first = application_payload(portfolio_id, 'Journey Alpha')
    second = application_payload(portfolio_id, 'Journey Beta', quality=41, health=61,
                                 automation=21, defects=3, risk='Low')
    created = []
    for body in (first, second):
        result = await client.post('/api/applications', headers=engineer, json=body)
        assert result.status_code == 201, result.text
        assert result.json()['portfolioId'] == portfolio_id
        assert result.json()['portfolioName'] == portfolio_body['name']
        created.append(result.json()['id'])

    dashboard = await client.get('/api/dashboard/executive', headers=engineer)
    assert dashboard.status_code == 200
    assert dashboard.json() == {
        'enterpriseQualityScore': 41, 'applicationHealthScore': 61,
        'automationMaturityScore': 21, 'openCriticalDefects': 5,
        'applicationsAtRisk': 1, 'totalApplications': 2, 'totalPortfolios': 1,
        'portfolios': [{'id': portfolio_id, 'name': 'Integration Portfolio',
                        'applicationCount': 2, 'qualityScore': 41, 'highRiskCount': 1}],
    }
    filtered = await client.get('/api/dashboard/executive', headers=engineer, params={'riskLevel': 'High'})
    assert filtered.status_code == 200
    assert filtered.json() == {
        'enterpriseQualityScore': 40, 'applicationHealthScore': 60,
        'automationMaturityScore': 20, 'openCriticalDefects': 2,
        'applicationsAtRisk': 1, 'totalApplications': 1, 'totalPortfolios': 1,
        'portfolios': [{'id': portfolio_id, 'name': 'Integration Portfolio',
                        'applicationCount': 1, 'qualityScore': 40, 'highRiskCount': 1}],
    }
    report = await client.get('/api/reports/applications', headers=engineer, params={'portfolioId': portfolio_id})
    assert report.status_code == 200 and report.json()['total'] == 2
    assert {item['id'] for item in report.json()['items']} == set(created)
    assert {item['name']: item['qualityScore'] for item in report.json()['items']} == {'Journey Alpha': 40, 'Journey Beta': 41}
    export = await client.get('/api/reports/applications', headers=engineer,
                              params={'portfolioId': portfolio_id, 'riskLevel': 'High', 'format': 'csv'})
    assert export.status_code == 200 and export.headers['content-type'].startswith('text/csv')
    assert list(csv.DictReader(io.StringIO(export.text))) == [{
        'name': 'Journey Alpha', 'portfolioName': 'Integration Portfolio', 'criticality': 'High',
        'tier': '2', 'lifecycleStatus': 'Active', 'applicationHealthScore': '60',
        'automationCoverage': '20', 'openCriticalDefects': '2', 'riskLevel': 'High',
    }]
    portfolio_report = await client.get('/api/reports/portfolios', headers=engineer)
    assert portfolio_report.status_code == 200 and portfolio_report.json()['total'] == 1
    portfolio_item = portfolio_report.json()['items'][0]
    assert (portfolio_item['id'], portfolio_item['applicationCount'], portfolio_item['qualityScore']) == (portfolio_id, 2, 41)

    audit = await client.get('/api/audit-logs', headers=admin, params={'pageSize': 100})
    assert audit.status_code == 200
    events = audit.json()['items']
    for entity_type, entity_id, actor_id in [('portfolio', portfolio_id, admin_user['id']),
                                              ('user', user_id, admin_user['id']),
                                              *[('application', item, user_id) for item in created]]:
        assert any(event['action'] == 'create' and event['entityType'] == entity_type
                   and event['entityId'] == entity_id and event['userId'] == actor_id for event in events)
    assert any(event['action'] == 'export' and event['entityType'] == 'application'
               and event['userId'] == user_id and event['details'] == 'Application report export succeeded' for event in events)
    assert 'JourneyPassword123!' not in audit.text and 'passwordHash' not in audit.text

    stored_portfolio = await db.portfolios.find_one({'_id': ObjectId(portfolio_id)})
    stored_user = await db.users.find_one({'_id': ObjectId(user_id)})
    stored_apps = await db.applications.find({'_id': {'$in': [ObjectId(x) for x in created]}}).to_list(None)
    assert stored_portfolio['name'] == portfolio_body['name']
    assert stored_user['portfolioAccess'] == [stored_portfolio['_id']]
    assert len(stored_apps) == 2 and all(item['portfolioId'] == stored_portfolio['_id'] for item in stored_apps)
    linked = await client.get(f'/api/portfolios/{portfolio_id}/applications', headers=engineer)
    assert linked.status_code == 200 and {item['id'] for item in linked.json()['items']} == set(created)
    assert (await client.delete(f'/api/portfolios/{portfolio_id}', headers=admin)).status_code == 409
    assert await db.portfolios.find_one({'_id': ObjectId(portfolio_id)}) is not None


async def test_live_role_permission_change_restricts_existing_session(client, db):
    """A role edit immediately changes the same token's cross-feature authority."""
    admin, admin_user = await admin_login(client)
    engineer, engineer_user = await login(client, 'engineer@ketsip.local')
    payments = await db.portfolios.find_one({'name': 'Payments'})
    roles = await client.get('/api/roles', headers=admin)
    assert roles.status_code == 200
    role = next(item for item in roles.json()['items'] if item['name'] == 'Engineer')
    body = application_payload(payments['_id'], 'Permission before')
    before = await client.post('/api/applications', headers=engineer, json=body)
    assert before.status_code == 201, before.text
    item_id = before.json()['id']
    update = await client.put(f"/api/roles/{role['id']}", headers=admin,
                              json={'description': 'View only', 'permissions': ['view']})
    assert update.status_code == 200
    assert (await client.get('/api/auth/me', headers=engineer)).json()['permissions'] == ['view']
    denied = await client.post('/api/applications', headers=engineer,
                               json=application_payload(payments['_id'], 'Permission denied'))
    assert denied.status_code == 403
    assert (await client.get(f'/api/applications/{item_id}', headers=engineer)).status_code == 200
    assert (await client.get('/api/dashboard/executive', headers=engineer)).status_code == 200
    assert (await client.get('/api/reports/applications', headers=engineer, params={'format': 'csv'})).status_code == 403
    update = await client.put(f"/api/roles/{role['id']}", headers=admin,
                              json={'description': 'No access', 'permissions': []})
    assert update.status_code == 200
    for path in (f'/api/applications/{item_id}', '/api/dashboard/executive', '/api/reports/applications'):
        assert (await client.get(path, headers=engineer)).status_code == 403
    assert await db.applications.find_one({'name': 'Permission denied'}) is None
    assert (await db.applications.find_one({'_id': ObjectId(item_id)}))['portfolioId'] == payments['_id']
    assert (await db.roles.find_one({'_id': ObjectId(role['id'])}))['permissions'] == []
    events = await client.get('/api/audit-logs', headers=admin, params={'action': 'permissionChange'})
    assert events.status_code == 200
    matching = [event for event in events.json()['items'] if event['entityId'] == role['id']]
    assert len(matching) == 2 and all(event['userId'] == admin_user['id'] for event in matching)
    assert await db.audit_logs.count_documents({'entityType': 'application', 'entityId': ObjectId(item_id),
                                                 'action': 'create', 'userId': ObjectId(engineer_user['id'])}) == 1


async def test_deactivation_revokes_existing_token_and_preserves_history(client, db):
    """Account deactivation invalidates existing access without deleting inventory or audit."""
    admin, admin_user = await admin_login(client)
    payments = await db.portfolios.find_one({'name': 'Payments'})
    response = await client.post('/api/users', headers=admin, json=user_payload(payments['_id'], 'deactivate@ketsip.local'))
    assert response.status_code == 201
    user_id = response.json()['id']
    engineer, _ = await login(client, 'deactivate@ketsip.local', 'JourneyPassword123!')
    created = await client.post('/api/applications', headers=engineer,
                                json=application_payload(payments['_id'], 'Deactivation inventory'))
    assert created.status_code == 201
    item_id = created.json()['id']
    assert (await client.get('/api/dashboard/executive', headers=engineer)).status_code == 200
    old_user = await db.users.find_one({'_id': ObjectId(user_id)})
    assert (await client.delete(f'/api/users/{user_id}', headers=admin)).status_code == 204
    for path in ('/api/auth/me', f'/api/applications/{item_id}', '/api/dashboard/executive', '/api/reports/applications'):
        assert (await client.get(path, headers=engineer)).status_code == 401
    assert (await client.post('/api/auth/login', json={'email': 'deactivate@ketsip.local',
                                                      'password': 'JourneyPassword123!'})).status_code == 401
    stored = await db.users.find_one({'_id': ObjectId(user_id)})
    assert stored['status'] == 'Inactive' and stored['tokenVersion'] == old_user['tokenVersion'] + 1
    assert stored['portfolioAccess'] == [payments['_id']]
    assert (await db.applications.find_one({'_id': ObjectId(item_id)}))['portfolioId'] == payments['_id']
    audit = await client.get('/api/audit-logs', headers=admin, params={'pageSize': 100})
    assert audit.status_code == 200
    assert any(e['action'] == 'delete' and e['entityType'] == 'user' and e['entityId'] == user_id
               and e['userId'] == admin_user['id'] for e in audit.json()['items'])
    assert any(e['action'] == 'create' and e['entityType'] == 'application' and e['entityId'] == item_id
               and e['userId'] == user_id for e in audit.json()['items'])


async def test_invisible_references_and_real_audit_write_failure_leave_no_partial_state(client, db):
    """Conceal hidden parents and roll back application plus parent on Mongo rejection."""
    admin, _ = await admin_login(client)
    engineer, _ = await login(client, 'engineer@ketsip.local')
    payments = await db.portfolios.find_one({'name': 'Payments'})
    hidden = await db.portfolios.find_one({'name': 'Customer Platform'})
    baseline = await client.post('/api/applications', headers=engineer,
                                 json=application_payload(payments['_id'], 'Rollback original'))
    assert baseline.status_code == 201
    item_id = baseline.json()['id']
    original = await db.applications.find_one({'_id': ObjectId(item_id)})
    parent_before = await db.portfolios.find_one({'_id': payments['_id']})
    hidden_before = await db.portfolios.find_one({'_id': hidden['_id']})
    audit_before = await db.audit_logs.count_documents({})

    assert (await client.get(f"/api/portfolios/{hidden['_id']}", headers=engineer)).status_code == 404
    hidden_report = await client.get('/api/reports/applications', headers=engineer,
                                     params={'portfolioId': str(hidden['_id'])})
    assert hidden_report.status_code == 200 and hidden_report.json()['total'] == 0
    hidden_dashboard = await client.get('/api/dashboard/executive', headers=engineer,
                                        params={'portfolioId': str(hidden['_id'])})
    assert hidden_dashboard.status_code == 200
    assert hidden_dashboard.json()['totalApplications'] == hidden_dashboard.json()['totalPortfolios'] == 0
    assert (await client.post('/api/portfolios', headers=engineer,
                              json={'name': 'Forbidden portfolio', 'owner': '', 'description': '',
                                    'productArea': '', 'status': 'Active'})).status_code == 403
    assert (await client.post('/api/applications', headers=engineer,
                              json=application_payload(hidden['_id'], 'Hidden create'))).status_code == 404
    assert (await client.put(f'/api/applications/{item_id}', headers=engineer,
                             json=application_payload(hidden['_id'], 'Hidden move'))).status_code == 404
    assert (await client.post('/api/applications', headers=engineer,
                              json=application_payload(ObjectId(), 'Missing create'))).status_code == 404
    assert (await client.post('/api/applications', headers=admin,
                              json=application_payload(ObjectId(), 'Missing admin create'))).status_code == 404
    assert (await client.post('/api/users', headers=admin,
                              json=user_payload(ObjectId(), 'missing@ketsip.local'))).status_code == 409
    assert (await client.delete(f"/api/portfolios/{payments['_id']}", headers=admin)).status_code == 409
    assert await db.applications.find_one({'_id': ObjectId(item_id)}) == original
    assert await db.portfolios.find_one({'_id': payments['_id']}) == parent_before
    assert await db.portfolios.find_one({'_id': hidden['_id']}) == hidden_before
    assert await db.audit_logs.count_documents({}) == audit_before
    assert await db.users.find_one({'email': 'missing@ketsip.local'}) is None
    assert await db.portfolios.find_one({'name': 'Forbidden portfolio'}) is None

    # The real server rejects the audit insert after the application and parent
    # writes within the transaction. No repository or database is mocked.
    await db.command({'collMod': 'audit_logs', 'validator': {'$jsonSchema': {
        'bsonType': 'object', 'required': ['integrationNeverPresent']}}, 'validationLevel': 'strict'})
    try:
        failed_create = await client.post('/api/applications', headers=engineer,
                                          json=application_payload(payments['_id'], 'Rejected transaction'))
        assert failed_create.status_code == 503
        failed_edit = await client.put(f'/api/applications/{item_id}', headers=engineer,
                                       json=application_payload(payments['_id'], 'Rejected edit', quality=99))
        assert failed_edit.status_code == 503
    finally:
        await db.command({'collMod': 'audit_logs', 'validator': {}})
    assert await db.applications.find_one({'name': 'Rejected transaction'}) is None
    assert await db.applications.find_one({'_id': ObjectId(item_id)}) == original
    assert await db.portfolios.find_one({'_id': payments['_id']}) == parent_before
    assert await db.audit_logs.count_documents({}) == audit_before
    for name in ('Hidden create', 'Hidden move', 'Missing create', 'Missing admin create', 'Rejected edit'):
        assert await db.applications.find_one({'name': name}) is None
    requery = await client.get(f'/api/applications/{item_id}', headers=engineer)
    assert requery.status_code == 200 and requery.json()['name'] == 'Rollback original'
    assert requery.json()['portfolioId'] == str(payments['_id'])
    report = await client.get('/api/reports/applications', headers=engineer, params={'search': 'Rejected'})
    assert report.status_code == 200 and report.json()['total'] == 0
    assert await db.portfolios.find_one({'_id': original['portfolioId']}) is not None
