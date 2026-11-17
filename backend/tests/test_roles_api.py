"""Exercise role HTTP contracts and concurrency against real MongoDB."""
import asyncio
from bson import ObjectId
from httpx import ASGITransport, AsyncClient
from app.main import create_app
from conftest import PASSWORD


async def login(client, email="admin@ketsip.local", password=PASSWORD):
    """Return a real bearer for a seeded account."""
    result = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert result.status_code == 200
    return {"Authorization": "Bearer " + result.json()["token"]}


async def test_role_listing_validation_duplicate_and_live_authority(client, db):
    """Enforce fixed names, live permissions and immutable role boundaries."""
    assert (await client.get('/api/roles')).status_code == 401
    await db.users.update_one({"email": "admin@ketsip.local"}, {"$set": {"mustChangePassword": False}})
    admin = await login(client)
    reader = await login(client, 'readonly@ketsip.local')
    response = await client.get('/api/roles', headers=admin, params={'pageSize': 2})
    assert response.status_code == 200 and response.json()['total'] == 6 and len(response.json()['items']) == 2
    assert (await client.get('/api/roles', headers=admin, params={'pageSize': 101})).status_code == 422
    role_list = await client.get('/api/roles', headers=admin)
    assert role_list.status_code == 200
    roles = role_list.json()['items']
    engineer = next(role for role in roles if role['name'] == 'Engineer')
    readonly = next(role for role in roles if role['name'] == 'Read Only')
    assert (await client.post('/api/roles', headers=admin, json={'name': 'Engineer', 'description': '', 'permissions': []})).status_code == 409
    assert (await client.post('/api/roles', headers=admin, json={'name': 'Root', 'description': '', 'permissions': []})).status_code == 422
    for invalid in (["view", "view"], ["root"]):
        assert (await client.put(f"/api/roles/{engineer['id']}", headers=admin, json={'description': '', 'permissions': invalid})).status_code == 422
    assert (await client.put(f'/api/roles/{ObjectId()}', headers=admin, json={'description': '', 'permissions': []})).status_code == 404
    assert (await client.put('/api/roles/bad', headers=admin, json={'description': '', 'permissions': []})).status_code == 422
    assert (await client.put(f"/api/roles/{readonly['id']}", headers=admin, json={'description': 'Restricted', 'permissions': ['view', 'administer', 'delete', 'edit', 'create', 'export']})).status_code == 200
    assert (await client.get('/api/roles', headers=reader)).status_code == 403
    portfolio = await db.portfolios.find_one({'name': 'Payments'})
    assert (await client.delete(f"/api/portfolios/{portfolio['_id']}", headers=reader)).status_code == 403
    identity = await client.get('/api/auth/me', headers=reader)
    assert identity.status_code == 200
    assert identity.json()['permissions'] == ['view', 'administer', 'delete', 'edit', 'create', 'export']
    changed = await client.put(f"/api/roles/{readonly['id']}", headers=admin, json={'description': 'No view', 'permissions': []})
    assert changed.status_code == 200
    assert (await client.get('/api/portfolios', headers=reader)).status_code == 403
    stored = await db.roles.find_one({'_id': ObjectId(readonly['id'])})
    assert stored['description'] == 'No view' and stored['permissions'] == []
    assert await db.audit_logs.count_documents({'entityType': 'role', 'entityId': stored['_id'], 'action': 'permissionChange'}) == 2


async def test_create_missing_fixed_role(client, db):
    """Recreate a missing fixed role and audit its persisted insertion."""
    await db.users.update_one({'email': 'admin@ketsip.local'}, {'$set': {'mustChangePassword': False}})
    admin = await login(client)
    await db.roles.delete_one({'name': 'Engineer'})
    response = await client.post('/api/roles', headers=admin, json={'name': 'Engineer', 'description': 'Restored', 'permissions': ['view']})
    assert response.status_code == 201
    identifier = ObjectId(response.json()['id'])
    assert (await db.roles.find_one({'_id': identifier}))['description'] == 'Restored'
    assert await db.audit_logs.count_documents({'entityType': 'role', 'entityId': identifier, 'action': 'create'}) == 1


async def test_role_audit_failure_rolls_back(client, db):
    """Abort the role write if the transactional audit append fails."""
    await db.users.update_one({'email': 'admin@ketsip.local'}, {'$set': {'mustChangePassword': False}})
    admin = await login(client)
    role = await db.roles.find_one({'name': 'Engineer'})
    before_audits = await db.audit_logs.count_documents({})
    await db.command({'collMod': 'audit_logs', 'validator': {'$jsonSchema': {'bsonType': 'object', 'required': ['neverPresent']}}, 'validationLevel': 'strict'})
    try:
        response = await client.put(f"/api/roles/{role['_id']}", headers=admin, json={'description': 'Lost', 'permissions': []})
    finally:
        await db.command({'collMod': 'audit_logs', 'validator': {}})
    assert response.status_code == 503
    assert (await db.roles.find_one({'_id': role['_id']}))['description'] == role['description']
    assert await db.roles.find_one({'_id': role['_id']}) == role
    assert await db.audit_logs.count_documents({}) == before_audits


async def test_concurrent_administrator_revocations_and_user_change(application, client, db):
    """Race two clients using the same guard; preserve a manageable system."""
    await db.users.update_one({'email': 'admin@ketsip.local'}, {'$set': {'mustChangePassword': False}})
    first = await login(client)
    payload = {'name': 'Second Admin', 'email': 'second@ketsip.local', 'role': 'Administrator', 'portfolioAccess': [],
               'status': 'Active', 'managerName': None, 'vendorIndicator': False, 'password': 'NewPassword123!'}
    created = await client.post('/api/users', headers=first, json=payload)
    assert created.status_code == 201
    second = await login(client, 'second@ketsip.local', 'NewPassword123!')
    role = await db.roles.find_one({'name': 'Administrator'})
    other_app = create_app(application.state.settings)
    async with other_app.router.lifespan_context(other_app):
        async with AsyncClient(transport=ASGITransport(app=other_app), base_url='http://test') as other:
            url = f"/api/roles/{role['_id']}"
            body = {'description': 'Attempt', 'permissions': ['view']}
            a, b = await asyncio.gather(client.put(url, headers=first, json=body), other.put(url, headers=second, json=body))
            assert [a.status_code, b.status_code] == [409, 409]
            a, b = await asyncio.gather(client.put(url, headers=first, json=body), other.delete(f"/api/users/{created.json()['id']}", headers=first))
            assert a.status_code == 409 and b.status_code == 204
    assert 'administer' in (await db.roles.find_one({'name': 'Administrator'}))['permissions']
    assert await db.users.count_documents({'role': 'Administrator', 'status': 'Active'}) == 1
    assert await db.audit_logs.count_documents({'entityType': 'role', 'action': 'permissionChange'}) == 0


async def test_role_edit_racing_actor_deactivation_rechecks_transaction(application, client, db):
    """Serialize a valid role edit with deactivation of its acting administrator."""
    await db.users.update_one({'email': 'admin@ketsip.local'}, {'$set': {'mustChangePassword': False}})
    first = await login(client)
    payload = {'name': 'Second Admin', 'email': 'second@ketsip.local', 'role': 'Administrator', 'portfolioAccess': [],
               'status': 'Active', 'managerName': None, 'vendorIndicator': False, 'password': 'NewPassword123!'}
    created = await client.post('/api/users', headers=first, json=payload)
    assert created.status_code == 201
    second = await login(client, 'second@ketsip.local', 'NewPassword123!')
    role = await db.roles.find_one({'name': 'Engineer'})
    other_app = create_app(application.state.settings)
    async with other_app.router.lifespan_context(other_app):
        async with AsyncClient(transport=ASGITransport(app=other_app), base_url='http://test') as other:
            edit, removal = await asyncio.gather(
                client.put(f"/api/roles/{role['_id']}", headers=second, json={'description': 'Raced', 'permissions': ['view']}),
                other.delete(f"/api/users/{created.json()['id']}", headers=first),
            )
    assert removal.status_code == 204
    assert edit.status_code in (200, 401, 403)
    persisted = await db.roles.find_one({'_id': role['_id']})
    audits = await db.audit_logs.count_documents({'entityType': 'role', 'entityId': role['_id'], 'action': 'permissionChange'})
    if edit.status_code == 200:
        assert persisted['description'] == 'Raced' and audits == 1
    else:
        assert persisted['description'] == role['description'] and audits == 0
