"""SQLAlchemy engine and session factory for PostgreSQL."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from api.config import get_settings

settings = get_settings()

_db_url = (settings.database_url or "").lower()
_engine_kwargs: dict = {"pool_pre_ping": True, "echo": False}

# --- Pool strategy (important for Supabase) ---------------------------------
# Supabase *session* pooler (:5432) exposes a very small global client limit for the whole
# project. SQLAlchemy's default QueuePool keeps connections open after each HTTP request
# returns, so 2–3 laptops × default pool = "MaxClientsInSessionMode" / 500 errors.
#
# Fix: NullPool on session pooler = open a connection for each DB session, close when the
# request ends. Only concurrent requests use concurrent connections (expected to be low in dev).
#
# For production / many workers: use Transaction pooler (:6543) in DATABASE_URL — then a
# normal QueuePool is fine (PgBouncer multiplexes many clients to fewer Postgres backends).
#
# Optional overrides for any host: DATABASE_POOL_SIZE, DATABASE_MAX_OVERFLOW
if settings.database_pool_size is not None:
    _engine_kwargs["pool_size"] = max(1, int(settings.database_pool_size))
    _mo = settings.database_max_overflow
    _engine_kwargs["max_overflow"] = max(0, int(_mo)) if _mo is not None else 5
    _engine_kwargs["pool_recycle"] = 1800
elif "pooler.supabase.com" in _db_url:
    if ":6543" in _db_url:
        _engine_kwargs.update(pool_size=5, max_overflow=10, pool_recycle=1800)
    else:
        # Session pooler :5432 — must not hold idle connections between API requests.
        _engine_kwargs["poolclass"] = NullPool
elif ".supabase.co" in _db_url and "pooler" not in _db_url:
    # Direct host db.*.supabase.co
    _engine_kwargs.update(pool_size=3, max_overflow=5, pool_recycle=600)

engine = create_engine(settings.database_url, **_engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
