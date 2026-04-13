"""
Add columns to existing SQLite/Postgres DBs (create_all does not alter tables).
Called once from app lifespan after create_all.
"""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def _cols(engine: Engine, table: str) -> set[str]:
    insp = inspect(engine)
    if not insp.has_table(table):
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def ensure_extra_columns(engine: Engine) -> None:
    dialect = engine.dialect.name
    existing_rank = _cols(engine, "job_candidate_rankings")
    existing_cand = _cols(engine, "candidates")
    existing_ing = _cols(engine, "resume_ingestions")
    existing_users = _cols(engine, "users")

    alters: list[str] = []

    if existing_cand:
        for col, ddl in [
            ("full_name", "VARCHAR(512) NOT NULL DEFAULT ''"),
            ("role_label", "VARCHAR(128) NOT NULL DEFAULT ''"),
            ("role_fine", "VARCHAR(64) NOT NULL DEFAULT 'unknown'"),
            ("years_experience", "FLOAT"),
            ("highest_degree", "VARCHAR(256) NOT NULL DEFAULT ''"),
            ("certifications", "TEXT NOT NULL DEFAULT ''"),
            ("education_lines", "TEXT NOT NULL DEFAULT ''"),
            ("embedding_sbert", "BYTEA" if dialect == "postgresql" else "BLOB"),
            ("status", "VARCHAR(64) NOT NULL DEFAULT 'new'"),
            ("storage_path", "VARCHAR(2048) NOT NULL DEFAULT ''"),
        ]:
            if col not in existing_cand:
                if dialect == "postgresql":
                    alters.append(
                        f"ALTER TABLE candidates ADD COLUMN IF NOT EXISTS {col} {ddl}"
                    )
                else:
                    alters.append(f"ALTER TABLE candidates ADD COLUMN {col} {ddl}")

    if existing_rank:
        for col, ddl in [
            ("candidate_name", "VARCHAR(512) NOT NULL DEFAULT ''"),
            ("candidate_title", "VARCHAR(512) NOT NULL DEFAULT ''"),
            ("candidate_role", "VARCHAR(128) NOT NULL DEFAULT ''"),
            ("years_experience", "FLOAT"),
            ("highest_degree", "VARCHAR(256) NOT NULL DEFAULT ''"),
            ("skills_summary", "TEXT NOT NULL DEFAULT ''"),
        ]:
            if col not in existing_rank:
                if dialect == "postgresql":
                    alters.append(
                        f"ALTER TABLE job_candidate_rankings ADD COLUMN IF NOT EXISTS {col} {ddl}"
                    )
                else:
                    alters.append(f"ALTER TABLE job_candidate_rankings ADD COLUMN {col} {ddl}")

        if "explanation_json" not in existing_rank:
            if dialect == "postgresql":
                alters.append(
                    "ALTER TABLE job_candidate_rankings ADD COLUMN IF NOT EXISTS explanation_json TEXT"
                )
            else:
                alters.append("ALTER TABLE job_candidate_rankings ADD COLUMN explanation_json TEXT")

    if existing_users:
        for col, ddl in [
            ("is_verified", "BOOLEAN NOT NULL DEFAULT 0" if dialect != "postgresql" else "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("verification_code_hash", "VARCHAR(256) NOT NULL DEFAULT ''"),
            ("verification_code_expires_at", "TIMESTAMP"),
        ]:
            if col not in existing_users:
                if dialect == "postgresql":
                    alters.append(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {ddl}")
                else:
                    alters.append(f"ALTER TABLE users ADD COLUMN {col} {ddl}")

    if not alters:
        return

    with engine.begin() as conn:
        for stmt in alters:
            conn.execute(text(stmt))

    # Best-effort: resume_ingestions.updated_at default for older DBs (Postgres only).
    # SQLite lacks ALTER COLUMN default in a simple way; we keep app-level updates.
    if existing_ing and dialect == "postgresql":
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE resume_ingestions ALTER COLUMN updated_at SET DEFAULT (NOW() AT TIME ZONE 'UTC')"
                    )
                )
        except Exception:
            pass
