"""
Rezume AI FastAPI application: ML inference + REST API + PostgreSQL.
Run from repo root:
  PYTHONPATH=backend uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
Or: ./run_api.sh
"""
from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from api.paths import repo_root

ROOT = repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.config import get_settings
from api.database import Base, engine
from api.db_migrate import backfill_workspaces, ensure_extra_columns, ensure_indexes
from api.error_handlers import (
    http_exception_handler,
    rezume_api_error_handler,
    response_validation_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from api.errors import RezumeAPIError
from api.logging_config import setup_logging
from api.routers import auth, analytics, candidate_portal, candidates, clients, feedback, health, inbox, ingestions, jobs, legacy_ml, meta, ml, preview, ocr, rankings, uploads
from api.slow_limiter import limiter
from starlette.exceptions import HTTPException as StarletteHTTPException

_log = logging.getLogger("rezume.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    # Fresh settings read on boot (lru_cache is empty after process start; clear avoids stale tests).
    get_settings.cache_clear()
    if not os.environ.get("REZUME_TESTING"):
        try:
            Base.metadata.create_all(bind=engine)
            ensure_extra_columns(engine)
            backfill_workspaces(engine)
            ensure_indexes(engine)
        except Exception as e:
            _log.error(
                "Database startup failed (%s). If using Postgres, run: docker compose up -d postgres "
                "and check DATABASE_URL in .env. For local dev without Docker, remove DATABASE_URL "
                "or set DATABASE_URL=sqlite+pysqlite:///./rezume_dev.db",
                e,
            )
            raise
    settings = get_settings()
    if (settings.smtp_host or "").strip():
        _log.info(
            "SMTP configured: host=%r port=%s ssl=%s starttls=%s user=%r from=%r",
            settings.smtp_host.strip(),
            settings.smtp_port,
            getattr(settings, "smtp_ssl", False),
            settings.smtp_use_tls,
            settings.smtp_user,
            (settings.smtp_from or settings.smtp_user or ""),
        )
    else:
        _log.warning("SMTP_HOST is empty — verification/reset codes are only written to API logs, not emailed.")
    if not settings.skip_model_warmup:
        try:
            from src.inference.service import warmup_match_ranker, warmup_role_classifier

            if warmup_role_classifier():
                _log.info("Role classifier weights preloaded (upload parse will skip cold start).")
            if warmup_match_ranker():
                _log.info("Cross-encoder match ranker preloaded (batched rank endpoints skip cold start).")
        except Exception as e:
            _log.warning("Model preload skipped: %s", e)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Rezume AI API",
        version="1.0.0",
        description="Resume parsing, job matching, SBERT + cross-encoder ranking, PostgreSQL persistence.",
        lifespan=lifespan,
    )
    app.state.limiter = limiter

    # Explicit origins from .env plus RFC1918 LAN dev (Vite --host on http://192.168.x.x:5173, etc.)
    # so browsers can call the API directly when not using the dev proxy.
    _lan_dev_origin_regex = (
        r"^https?://("
        r"localhost|127\.0\.0\.1"
        r"|192\.168\.\d{1,3}\.\d{1,3}"
        r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
        r"|172\.(1[6-9]|2[0-9]|3[0-1])\.\d{1,3}\.\d{1,3}"
        r")(?::\d+)?$"
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_origin_regex=_lan_dev_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(SlowAPIMiddleware)

    app.add_exception_handler(RezumeAPIError, rezume_api_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ResponseValidationError, response_validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    async def _rate_limit_json(request, exc: RateLimitExceeded):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=429,
            content={
                "success": False,
                "error": "Rate limit exceeded. Try again later.",
                "code": "RATE_LIMIT",
            },
        )

    app.add_exception_handler(RateLimitExceeded, _rate_limit_json)

    app.include_router(health.router)
    app.include_router(legacy_ml.router)
    prefix = settings.api_prefix
    app.include_router(ml.router, prefix=prefix)
    app.include_router(auth.router, prefix=prefix)
    app.include_router(candidate_portal.router, prefix=prefix)
    app.include_router(meta.router, prefix=prefix)
    app.include_router(inbox.router, prefix=prefix)
    app.include_router(analytics.router, prefix=prefix)
    app.include_router(clients.router, prefix=prefix)
    app.include_router(jobs.router, prefix=prefix)
    app.include_router(candidates.router, prefix=prefix)
    app.include_router(rankings.router, prefix=prefix)
    app.include_router(feedback.router, prefix=prefix)
    app.include_router(ingestions.router, prefix=prefix)
    app.include_router(uploads.router, prefix=prefix)
    app.include_router(preview.router, prefix=prefix)
    app.include_router(ocr.router, prefix=prefix)

    @app.get("/", include_in_schema=False)
    async def _root() -> RedirectResponse:
        """Browser often opens / alone; there is no JSON here — use /health or /docs."""
        return RedirectResponse(url="/docs")

    return app


app = create_app()
