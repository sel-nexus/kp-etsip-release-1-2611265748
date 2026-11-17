"""Provide function-isolated real Mongo databases and lifespan HTTP clients."""
import os
from collections.abc import AsyncIterator
from uuid import uuid4
import pytest
from httpx import ASGITransport, AsyncClient
from pymongo.asynchronous.database import AsyncDatabase
from fastapi import FastAPI
from app.core.config import Settings
from app.main import create_app

PASSWORD = "TestDemoPassword123!"


@pytest.fixture
async def application() -> AsyncIterator[FastAPI]:
    """Seed a unique test database and drop only that database after each test."""
    database_name = f"etsip_test_{uuid4().hex}"
    settings = Settings(_env_file=None, APP_ENV="test", MONGODB_URI=os.getenv("TEST_MONGODB_URI", "mongodb://127.0.0.1:27017"),
                        MONGODB_DB=database_name, JWT_SECRET="test-secret-not-for-deployment", CORS_ORIGINS="http://test",
                        SEED_ADMIN_PASSWORD=PASSWORD, SEED_DEMO_PASSWORD=PASSWORD)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        try:
            yield app
        finally:
            assert app.state.settings.MONGODB_DB.startswith("etsip_test_")
            await app.state.mongo.drop_database(database_name)


@pytest.fixture
async def db(application: FastAPI) -> AsyncDatabase:
    """Expose the lifespan database for persisted-state assertions."""
    return application.state.db


@pytest.fixture
async def client(application: FastAPI) -> AsyncIterator[AsyncClient]:
    """Exercise real HTTP handlers without replacing database repositories."""
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as http:
        yield http
