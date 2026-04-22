"""Application settings (env / .env)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from api.paths import repo_root

_REPO_ROOT = repo_root()


def _default_sqlite_url() -> str:
    """File next to repo root so the API starts without Docker/Postgres."""
    db_path = (_REPO_ROOT / "rezume_dev.db").resolve()
    return f"sqlite+pysqlite:///{db_path.as_posix()}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Repo-root .env regardless of cwd (e.g. `python training/scripts/foo.py`).
        env_file=str(_REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Override in .env: PostgreSQL e.g. postgresql+psycopg2://rezume:rezume@localhost:5432/rezumeai
    database_url: str = Field(default_factory=_default_sqlite_url)

    # API
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"

    # ML / data paths (repo root)
    project_root: Optional[str] = None

    # Lifecycle (set SKIP_MODEL_WARMUP=true in pytest)
    skip_model_warmup: bool = False

    # Model versioning labels (env: MODEL_VERSION_TFIDF, etc.)
    model_version_tfidf: str = "model_v1_tfidf"
    model_version_sbert: str = "model_v2_sbert"
    model_version_crossencoder: str = "model_v3_crossencoder"
    model_version_role: str = "model_v3_role_roberta"

    # Auth (optional; REQUIRE_AUTH=false keeps existing clients working)
    jwt_secret: str = "change-me-in-production"
    jwt_expire_minutes: int = 60
    require_auth: bool = False

    # Email verification (for registration)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@rezume.local"
    smtp_use_tls: bool = True
    # If true, connect with SMTP_SSL (typical port 465). Otherwise use plain SMTP + STARTTLS when smtp_use_tls.
    smtp_ssl: bool = False
    # Log SMTP protocol to api logger (troubleshoot auth / TLS).
    smtp_debug: bool = False
    verification_code_ttl_minutes: int = 15

    # When SMTP is configured: also log codes (useful while debugging mail delivery).
    # When SMTP is unset, codes are always logged — no need to toggle this for local dev.
    dev_email_print_code: bool = False

    # OpenAI-compatible API for ranking narrative (optional; falls back to template if unset).
    openai_api_key: str = ""
    openai_api_base: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openai_insight_timeout_seconds: int = 45

    # xAI Grok (OpenAI-compatible Chat Completions) — optional LinkedIn scrape refinement
    xai_api_key: str = ""
    xai_api_base: str = "https://api.x.ai/v1"
    xai_model: str = "grok-2-latest"
    xai_refine_timeout_seconds: int = 90

    @model_validator(mode="after")
    def _anchor_relative_sqlite_paths(self) -> "Settings":
        """
        .env often uses DATABASE_URL=sqlite+pysqlite:///./rezume_dev.db — that path is cwd-relative
        in SQLite, so CLI runs from training/scripts hit a different/empty DB than the API.
        Anchor relative sqlite file paths to the repository root.
        """
        url_str = (self.database_url or "").strip()
        if "sqlite" not in url_str.lower():
            return self
        try:
            from sqlalchemy.engine.url import make_url

            u = make_url(url_str)
        except Exception:
            return self
        try:
            if u.get_dialect().name != "sqlite":
                return self
        except Exception:
            return self
        db = u.database
        if not db or db == ":memory:":
            return self
        p = Path(db)
        if p.is_absolute():
            return self
        abs_path = (_REPO_ROOT / db).resolve()
        new_u = u.set(database=str(abs_path))
        rendered = new_u.render_as_string(hide_password=False)
        if rendered != url_str:
            self.database_url = rendered
        return self

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
