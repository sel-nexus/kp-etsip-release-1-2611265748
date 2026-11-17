"""Verify application service writes and reference integrity on real MongoDB."""
import asyncio
import socket
import subprocess
import time
import pytest
from bson import ObjectId
from pymongo import AsyncMongoClient, MongoClient
from pymongo.errors import ServerSelectionTimeoutError
from app.core.errors import DomainError
from app.core.config import Settings
from app.main import create_app
from app.features.applications.repository import ApplicationRepository
from app.features.applications.service import ApplicationService
from app.features.applications.schemas import ApplicationWrite
from test_applications_write_api import login, payload
from conftest import PASSWORD


async def test_service_duplicate_and_scope(client, application, db):
    """Persist a service mutation and reject duplicate and out-of-scope writes."""
    headers = await login(client, 'engineer@ketsip.local')
    actor = await application.state.auth.authenticate(headers['Authorization'].split(' ')[1])
    parent = await db.portfolios.find_one({'name': 'Payments'})
    hidden = await db.portfolios.find_one({'name': 'Customer Platform'})
    service = application.state.applications
    value = ApplicationWrite(**payload(parent['_id']))
    created = await service.mutate(actor, value, None, 'create')
    assert (await db.applications.find_one({'_id': ObjectId(created.id)}))['name'] == value.name
    with pytest.raises(DomainError) as duplicate:
        await service.mutate(actor, value, None, 'create')
    assert duplicate.value.status == 409
    with pytest.raises(DomainError) as denied:
        await service.mutate(actor, ApplicationWrite(**payload(hidden['_id'])), created.id, 'edit')
    assert denied.value.status == 404
    assert (await db.applications.find_one({'_id': ObjectId(created.id)}))['portfolioId'] == parent['_id']


@pytest.mark.parametrize('reassign', [False, True])
async def test_independent_mongo_clients_conflict_with_delete(client, application, db, reassign):
    """Run service mutations using separate pools and assert no dangling references."""
    await db.users.update_one({'email': 'admin@ketsip.local'}, {'$set': {'mustChangePassword': False}})
    headers = await login(client, 'admin@ketsip.local')
    actor = await application.state.auth.authenticate(headers['Authorization'].split(' ')[1])
    parent = await client.post('/api/portfolios', headers=headers, json={'name': 'Independent race', 'owner': '', 'description': '', 'productArea': '', 'status': 'Active'})
    identifier = parent.json()['id']
    other = AsyncMongoClient(application.state.settings.MONGODB_URI, tz_aware=True)
    try:
        service = ApplicationService(ApplicationRepository(other[db.name]))
        existing = await db.applications.find_one({'name': 'Payment Gateway'}) if reassign else None
        async def create():
            """Capture an expected conflict or a successful committed write."""
            try:
                await service.mutate(actor, ApplicationWrite(**payload(identifier, 'Independent app')), str(existing['_id']) if existing else None, 'edit' if reassign else 'create')
                return 200 if reassign else 201
            except DomainError as exc:
                return exc.status
        async def remove():
            """Capture an expected linked-reference conflict or successful deletion."""
            try:
                await application.state.portfolios.delete(actor, identifier)
                return 204
            except DomainError as exc:
                return exc.status
        result = await asyncio.gather(create(), remove())
        assert tuple(result) in ((200 if reassign else 201, 409), (404, 204))
        assert not (await db.applications.count_documents({'portfolioId': ObjectId(identifier)}) and not await db.portfolios.find_one({'_id': ObjectId(identifier)}))
    finally:
        await other.close()


async def test_standalone_database_fails_closed(client, application, tmp_path):
    """Return 503 without creating an application when transactions are unavailable."""
    headers = await login(client, 'engineer@ketsip.local')
    actor = await application.state.auth.authenticate(headers['Authorization'].split(' ')[1])
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen(['mongod', '--port', str(port), '--bind_ip', '127.0.0.1', '--dbpath', str(tmp_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    uri = f'mongodb://127.0.0.1:{port}'
    probe = MongoClient(uri, serverSelectionTimeoutMS=200)
    try:
        for _ in range(50):
            try:
                probe.admin.command('ping')
                break
            except ServerSelectionTimeoutError:
                time.sleep(0.1)
        else:
            pytest.fail('Standalone mongod did not start')
        settings = Settings(_env_file=None, APP_ENV='test', MONGODB_URI=uri, MONGODB_DB='etsip_standalone_startup',
                            JWT_SECRET='test-secret-not-for-deployment', CORS_ORIGINS='http://test',
                            SEED_ADMIN_PASSWORD=PASSWORD, SEED_DEMO_PASSWORD=PASSWORD)
        standalone_app = create_app(settings)
        with pytest.raises(DomainError, match='transactions are unavailable'):
            async with standalone_app.router.lifespan_context(standalone_app):
                pytest.fail('Standalone seeding must not start with incomplete inventory')
        other = AsyncMongoClient(uri, tz_aware=True)
        try:
            db = other['etsip_standalone_test']
            parent = ObjectId(actor.user.portfolioAccess[0])
            await db.portfolios.insert_one({'_id': parent, 'name': 'Standalone'})
            with pytest.raises(DomainError) as error:
                await ApplicationService(ApplicationRepository(db)).mutate(actor, ApplicationWrite(**payload(parent)), None, 'create')
            assert error.value.status == 503
            assert await db.applications.count_documents({}) == 0
        finally:
            await other.close()
    finally:
        probe.close()
        process.terminate()
        process.wait(timeout=10)
