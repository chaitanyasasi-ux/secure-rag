from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.rate_limit import limiter
from app.db.session import init_db

configure_logging()
log = structlog.get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info("app.startup", env=settings.app_env)
    await init_db()

    # Setup Qdrant collection
    try:
        from app.services.qdrant_service import get_qdrant_client, setup_collection
        qdrant_client = get_qdrant_client()
        setup_collection(qdrant_client)
        qdrant_client.close()
        log.info("qdrant.ready")
    except Exception as e:
        log.warning("qdrant.setup_failed", error=str(e))

    yield
    log.info("app.shutdown")


def create_app() -> FastAPI:
    application = FastAPI(
        title="Secure Enterprise RAG API",
        version="1.0.0",
        description=(
            "Production-grade RAG system with RBAC, vector-level access control, "
            "prompt injection guardrails, and full audit logging."
        ),
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # Attach rate limiter to app state
    application.state.limiter = limiter

    # ── Middleware ────────────────────────────────────────────────────────────
    application.add_middleware(SlowAPIMiddleware)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # ── Routes ────────────────────────────────────────────────────────────────
    application.include_router(api_router)

    # ── Static files and UI ───────────────────────────────────────────────────
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    if os.path.exists(static_dir):
        application.mount("/static", StaticFiles(directory=static_dir), name="static")

    @application.get("/", include_in_schema=False)
    async def serve_ui():
        return FileResponse(os.path.join(static_dir, "index.html"))

    # ── Exception handlers ────────────────────────────────────────────────────

    # Rate limit exceeded — return clean 429 response
    application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Any unhandled exception — never expose tracebacks to clients
    @application.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        log.exception(
            "app.unhandled_exception",
            path=request.url.path,
            method=request.method,
            exc_type=type(exc).__name__,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An internal server error occurred."},
        )

    # ── Health check ──────────────────────────────────────────────────────────
    @application.get("/health", tags=["Ops"], include_in_schema=False)
    async def health(request: Request) -> dict:
        checks = {"status": "ok", "env": settings.app_env}

        # Check Postgres
        try:
            from app.db.session import engine
            from sqlalchemy import text
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["postgres"] = "healthy"
        except Exception as e:
            checks["postgres"] = f"unhealthy: {str(e)}"
            checks["status"] = "degraded"

        # Check Qdrant
        try:
            from app.services.qdrant_service import get_qdrant_client
            client = get_qdrant_client()
            client.get_collections()
            client.close()
            checks["qdrant"] = "healthy"
        except Exception as e:
            checks["qdrant"] = f"unhealthy: {str(e)}"
            checks["status"] = "degraded"

        return checks

    return application


app = create_app()