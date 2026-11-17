"""Wire local auth to lifespan-owned native async Mongo persistence."""
import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from collections.abc import Callable, Awaitable
from fastapi.middleware.cors import CORSMiddleware
from pymongo import AsyncMongoClient
from pydantic import BaseModel, ConfigDict
from app.core.config import Settings
from app.core.database import create_indexes
from app.core.errors import register_errors
from app.core.security import hash_password
from app.core.seed import seed_database
from app.features.audit.repository import AuditRepository
from app.features.audit.service import AuditService
from app.features.auth.repository import AuthRepository
from app.features.auth.router import router
from app.features.auth.service import AuthService
from app.features.profile.router import router as profile_router
from app.features.profile.service import ProfileService
from app.features.portfolios.router import router as portfolios_router
from app.features.portfolios.repository import PortfolioRepository
from app.features.portfolios.service import PortfolioService
from app.features.applications.router import router as applications_router
from app.features.applications.repository import ApplicationRepository
from app.features.applications.service import ApplicationService

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    """Expose process liveness independently of database reads."""
    model_config = ConfigDict(extra="forbid", strict=True)
    status: str


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an app without opening Mongo until its lifespan begins."""
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """Open one client on this loop and always release it on shutdown."""
        config = settings or Settings()
        application.state.settings = config
        client = AsyncMongoClient(config.MONGODB_URI, tz_aware=True, serverSelectionTimeoutMS=5000)
        application.state.mongo = client
        try:
            db = client.get_database(config.MONGODB_DB)
            application.state.db = db
            await db.command("ping")
            await create_indexes(db)
            if config.SEED_ON_STARTUP:
                await seed_database(db, config)
            dummy_hash = await hash_password(secrets.token_urlsafe(24))
            application.state.auth = AuthService(AuthRepository(db), AuditService(AuditRepository(db)), config, dummy_hash)
            application.state.profile = ProfileService(application.state.auth, AuditRepository(db))
            application.state.portfolios = PortfolioService(PortfolioRepository(db), AuditRepository(db))
            application.state.applications = ApplicationService(ApplicationRepository(db))
            yield
        finally:
            await client.close()

    application = FastAPI(title="KP ETSIP", version="1.0.0", description="Local identity and scoped sessions",
                          lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    # Settings loading occurs at startup; CORS env is read independently without secrets.
    import os
    origins = settings.cors_origins if settings else [item.strip() for item in os.getenv("CORS_ORIGINS", "").split(",") if item.strip()]
    if settings is None:
        from dotenv import dotenv_values
        origins = [item.strip() for item in os.getenv("CORS_ORIGINS", dotenv_values(".env").get("CORS_ORIGINS") or "").split(",") if item.strip()]
    application.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Authorization", "Content-Type"])
    register_errors(application)
    application.include_router(router)
    application.include_router(profile_router)
    application.include_router(portfolios_router)
    application.include_router(applications_router)

    @application.middleware("http")
    async def security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Prevent auth response caching and MIME sniffing."""
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @application.get("/api/health", response_model=HealthResponse, tags=["Health"], summary="Check process liveness")
    async def health() -> HealthResponse:
        """Return liveness without querying external dependencies."""
        return HealthResponse(status="ok")

    return application


app = create_app()
