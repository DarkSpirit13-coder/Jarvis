"""FastAPI application factory for the JARVIS AI Operating System."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.conversations import router as conversations_router
from app.api.health import router as health_router
from app.config.settings import get_settings
from app.core.logging import configure_logging, get_logger
from app.database.session import dispose_engine
from app.websocket.router import router as websocket_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown lifecycle events."""
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("jarvis_starting", extra={"environment": settings.environment})
    yield
    await dispose_engine()
    logger.info("jarvis_stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if settings.enable_openapi else None,
        redoc_url="/redoc" if settings.enable_openapi else None,
        openapi_url="/openapi.json" if settings.enable_openapi else None,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(health_router, prefix="/api")
    app.include_router(auth_router, prefix="/api/auth")
    app.include_router(chat_router, prefix="/api")
    app.include_router(conversations_router, prefix="/api/conversations")
    app.include_router(websocket_router, prefix="/ws")
    return app


app = create_app()
