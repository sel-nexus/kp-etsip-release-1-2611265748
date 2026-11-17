"""Verify audit HTTP security, filtering, export and atomic rollback on Mongo."""
import csv
import io
from datetime import UTC, datetime, timedelta
import pytest
from bson import ObjectId
from pymongo.errors import OperationFailure
from conftest import PASSWORD

PAYLOAD = {'name': 'Audit test portfolio', 'owner': 'Owner', 'description': 'Description', 'productArea': 'Area', 'status': 'Active'}


async def login(client, email):
    """Authenticate an existing seeded identity."""
    response = await client.post('/api/auth/login', json={'email': email, 'password': PASSWORD})
    assert response.status_code == 200
    return {'Authorization': 'Bearer ' + response.json()['token']}, response.json()['user']


async def test_filters_validation_access_and_live_permissions(client, db):
    """Enforce role boundaries and exact inclusive UTC filters."""
    await db.users.update_one({'email': 'admin@ketsip.local'}, {'$set': {'mustChangePassword': False}})
    admin, identity = await login(client, 'admin@ketsip.local')
    auditor, _ = await login(client, 'auditor@ketsip.local')
    assert (await client.get('/api/audit-logs')).status_code == 401
    for email in ['engineer@ketsip.local', 'executive@ketsip.local', 'leader@ketsip.local', 'readonly@ketsip.local']:
        denied, _ = await login(client, email)
        assert (await client.get('/api/audit-logs', headers=denied)).status_code == 403
        assert (await client.get('/api/audit-logs?format=csv', headers=denied)).status_code == 403
    for headers in (admin, auditor):
        response = await client.get('/api/audit-logs', headers=headers, params={'userId': identity['id'], 'action': 'login', 'pageSize': 1})
        assert response.status_code == 200
        assert response.json()['total'] == 1 and response.json()['items'][0]['userId'] == identity['id']
        assert PASSWORD not in response.text and 'passwordHash' not in response.text
    for params in [{'userId': 'invalid'}, {'action': '$ne'}, {'from': '2025-01-01'},
                   {'to': '2025-01-01T00:00:00+01:00'}, {'from': 'bad'}, {'pageSize': 101},
                   {'from': '2026-01-01T00:00:00Z', 'to': '2025-01-01T00:00:00Z'}, {'format': 'xml'}]:
        assert (await client.get('/api/audit-logs', headers=admin, params=params)).status_code == 422
    now = datetime.now(UTC)
    bounded = await client.get('/api/audit-logs', headers=admin, params={'from': (now - timedelta(minutes=1)).isoformat(), 'to': (now + timedelta(minutes=1)).isoformat()})
    assert bounded.status_code == 200 and bounded.json()['total'] >= 6
    await db.roles.update_one({'name': 'Auditor'}, {'$set': {'permissions': ['view']}})
    assert (await client.get('/api/audit-logs?format=csv', headers=auditor)).status_code == 403
    await db.roles.update_one({'name': 'Auditor'}, {'$set': {'permissions': ['export']}})
    assert (await client.get('/api/audit-logs', headers=auditor)).status_code == 403
    assert (await client.get('/api/audit-logs?format=csv', headers=auditor)).status_code == 403
    assert (await client.get('/api/users', headers=auditor)).status_code == 403
    assert (await client.get('/api/roles', headers=auditor)).status_code == 403


async def test_csv_full_filtered_results_formula_safety_and_export_event(client, db):
    """Export beyond one page, redact stored extras and audit the export exactly once."""
    auditor, user = await login(client, 'auditor@ketsip.local')
    now = datetime.now(UTC)
    rows = [{ 'timestamp': now, 'createdAt': now, 'updatedAt': now, 'userId': ObjectId(user['id']),
              'userName': '=HYPERLINK("bad")', 'action': 'edit', 'entityType': 'portfolio',
              'entityId': ObjectId(), 'details': '\t=cmd', 'passwordHash': 'secret-hash'} for _ in range(27)]
    await db.audit_logs.insert_many(rows)
    response = await client.get('/api/audit-logs', headers=auditor, params={'format': 'csv', 'action': 'edit', 'pageSize': 1})
    assert response.status_code == 200 and response.headers['content-type'].startswith('text/csv')
    parsed = list(csv.DictReader(io.StringIO(response.text)))
    assert len(parsed) == 27 and parsed[0]['userName'].startswith("'=") and parsed[0]['details'].startswith("'\t")
    assert 'secret-hash' not in response.text and PASSWORD not in response.text
    assert await db.audit_logs.count_documents({'action': 'export', 'entityType': 'audit'}) == 1
    page = await client.get('/api/audit-logs', headers=auditor, params={'action': 'edit', 'pageSize': 1, 'page': 2})
    assert page.json()['total'] == 27 and len(page.json()['items']) == 1 and 'passwordHash' not in page.text


async def test_csv_export_preserves_and_neutralizes_leading_controls_and_formulas(client, db):
    """Read actual CSV cells for persisted unsafe and ordinary audit values."""
    auditor, user = await login(client, 'auditor@ketsip.local')
    now = datetime.now(UTC)
    unsafe = [prefix + chr(code) + suffix
              for code in (*range(32), 127)
              for prefix in ('', ' ', '\u00a0')
              for suffix in ('text', '=1+1')]
    unsafe += [prefix + formula for prefix in ('', '  ', '\t', '\n', '\r', '\u2003')
               for formula in ('=1+1', '+SUM(A1)', '-2', '@formula')]
    safe = ['   ', 'ordinary\ttext', 'ordinary\n=1+1', 'quoted, "text"']
    expected = {}
    rows = []
    for value, neutralize in [(value, True) for value in unsafe] + [(value, False) for value in safe]:
        entity_id = ObjectId()
        expected[str(entity_id)] = ("'" if neutralize else '') + value
        rows.append({'timestamp': now, 'createdAt': now, 'updatedAt': now,
                     'userId': ObjectId(user['id']), 'userName': value, 'action': 'edit',
                     'entityType': 'portfolio', 'entityId': entity_id, 'details': value})
    await db.audit_logs.insert_many(rows)
    response = await client.get('/api/audit-logs', headers=auditor,
                                params={'format': 'csv', 'action': 'edit'})
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/csv')
    parsed = list(csv.DictReader(io.StringIO(response.text, newline='')))
    assert len(parsed) == len(rows)
    assert {row['entityId'] for row in parsed} == set(expected)
    for row in parsed:
        assert row['userName'] == expected[row['entityId']]
        assert row['details'] == expected[row['entityId']]
        assert row['userId'] == user['id']
        assert row['action'] == 'edit' and row['entityType'] == 'portfolio'


async def test_restricted_auditor_scope_never_exposes_unattributed_or_other_events(client, db):
    """Fail closed on records without trustworthy portfolio attribution."""
    auditor, user = await login(client, 'auditor@ketsip.local')
    one, two = await db.portfolios.find({}).limit(2).to_list(None)
    await db.users.update_one({'_id': ObjectId(user['id'])}, {'$set': {'portfolioAccess': [one['_id']]}})
    now = datetime.now(UTC)
    for portfolio in (one, two):
        await db.audit_logs.insert_one({'timestamp': now, 'createdAt': now, 'updatedAt': now,
            'userId': ObjectId(user['id']), 'userName': 'Auditor', 'action': 'edit', 'entityType': 'portfolio',
            'entityId': portfolio['_id'], 'details': 'Portfolio edit succeeded'})
    result = await client.get('/api/audit-logs', headers=auditor)
    assert result.status_code == 200 and result.json()['total'] == 1
    assert result.json()['items'][0]['entityId'] == str(one['_id'])
    csv_result = await client.get('/api/audit-logs?format=csv', headers=auditor)
    assert str(one['_id']) in csv_result.text and str(two['_id']) not in csv_result.text


async def test_failed_audit_insert_rolls_back_profile_portfolio_and_login(application, db):
    """Use Mongo collection validation to force actual transactional insert failures."""
    auth = application.state.auth
    from app.features.auth.schemas import LoginRequest
    from app.features.profile.schemas import ProfileRequest, ChangePasswordRequest
    from app.features.portfolios.schemas import PortfolioWrite
    await db.users.update_one({'email': 'admin@ketsip.local'}, {'$set': {'mustChangePassword': False}})
    login_result = await auth.login(LoginRequest(email='admin@ketsip.local', password=PASSWORD))
    session = await auth.authenticate(login_result.token)
    portfolio = await db.portfolios.find_one({'name': 'Payments'})
    before_user = await db.users.find_one({'_id': ObjectId(session.user.id)})
    before_count = await db.audit_logs.count_documents({})
    await db.command({'collMod': 'audit_logs', 'validator': {'$jsonSchema': {'bsonType': 'object', 'required': ['neverPresent']}}, 'validationLevel': 'strict'})
    with pytest.raises(OperationFailure):
        await application.state.profile.update_profile(session, ProfileRequest(defaultLandingPage='applications'))
    with pytest.raises(OperationFailure):
        await application.state.profile.change_password(session, ChangePasswordRequest(currentPassword=PASSWORD, newPassword='ReplacementPassword123!'))
    with pytest.raises(OperationFailure):
        await application.state.portfolios.create(session, PortfolioWrite(**PAYLOAD))
    with pytest.raises(OperationFailure):
        await application.state.portfolios.update(session, str(portfolio['_id']), PortfolioWrite(**PAYLOAD))
    with pytest.raises(OperationFailure):
        await auth.login(LoginRequest(email='admin@ketsip.local', password=PASSWORD))
    assert await db.users.find_one({'_id': before_user['_id']}) == before_user
    assert await db.portfolios.find_one({'_id': portfolio['_id']}) == portfolio
    assert await db.portfolios.find_one({'name': PAYLOAD['name']}) is None
    assert await db.audit_logs.count_documents({}) == before_count
