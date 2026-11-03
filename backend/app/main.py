"""Application factory.

Run locally:  uvicorn app.main:create_app --factory --reload
"""

import asyncio
import logging
import re
import uuid
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.config import Settings, get_settings
from app.db import make_engine, make_session_factory
from app.email_inbox import process_due_inboxes
from app.engine import process_due_timers
from app.ratelimit import SlidingWindowLimiter
from app.routers import ai_status, auth, connections, email_inbox, executions, orgs, webhooks, workflows

_SAFE_TRACE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
logger = logging.getLogger("hermes.scheduler")


def _tick(session_factory, settings: Settings) -> None:
    with session_factory() as db:
        db.info["settings"] = settings
        process_due_timers(db)
    # Mailboxes are checked on their own, longer interval inside process_due_inboxes.
    with session_factory() as db:
        db.info["settings"] = settings
        try:
            process_due_inboxes(db, settings, settings.email_poll_seconds)
        except Exception:
            logger.exception("Mailbox check failed")


async def _scheduler_loop(session_factory, settings: Settings, interval: float) -> None:
    """Resume runs whose delay has elapsed. Run state is in the database, so a restart loses nothing."""
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(_tick, session_factory, settings)
        except Exception:
            logger.exception("Scheduler tick failed")


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = engine or make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        task = None
        if settings.scheduler_enabled:
            task = asyncio.create_task(
                _scheduler_loop(app.state.session_factory, settings, settings.scheduler_interval_seconds)
            )
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(
        lifespan=lifespan,
        title="Hermes AI API",
        version="0.1.0",
        docs_url=None if settings.is_production else "/api/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/api/openapi.json",
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.login_limiter = SlidingWindowLimiter(settings.login_rate_limit, settings.login_rate_window_seconds)
    # Per-endpoint cap on inbound webhook deliveries.
    app.state.webhook_limiter = SlidingWindowLimiter(settings.webhook_rate_limit, 60)
    if settings.is_production:
        # Fail at startup, not on the first webhook, if secrets cannot be encrypted.
        from app.crypto import resolve_key

        resolve_key(settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"],
        max_age=600,
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        incoming = request.headers.get("x-request-id", "")
        trace_id = incoming if _SAFE_TRACE.match(incoming) else str(uuid.uuid4())
        request.state.trace_id = trace_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = trace_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception):  # pragma: no cover - safety net
        # Never leak internals. The trace ID links the response to server logs.
        return JSONResponse(
            status_code=500,
            content={"detail": "An unexpected error occurred.", "trace_id": getattr(request.state, "trace_id", None)},
        )

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["ops"])
    def readyz():
        try:
            with app.state.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse(status_code=503, content={"status": "unavailable"})
        return {"status": "ready"}

    app.include_router(auth.router)
    app.include_router(orgs.router)
    app.include_router(workflows.router)
    app.include_router(executions.router)
    app.include_router(webhooks.public_router)
    app.include_router(webhooks.manage_router)
    app.include_router(connections.router)
    app.include_router(email_inbox.router)
    app.include_router(ai_status.router)
    return app
