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
    existing_jobs = _cols(engine, "jobs")
    existing_clients = _cols(engine, "clients")
    existing_job_attachments = _cols(engine, "job_attachments")
    existing_ing = _cols(engine, "resume_ingestions")
    existing_users = _cols(engine, "users")
    existing_events = _cols(engine, "activity_events")

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
            ("contact_email", "VARCHAR(320) NOT NULL DEFAULT ''"),
            ("best_job_match_score", "FLOAT"),
            ("best_job_external_id", "VARCHAR(64) NOT NULL DEFAULT ''"),
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

    if existing_jobs:
        for col, ddl in [
            ("status", "VARCHAR(24) NOT NULL DEFAULT 'active'"),
            ("client_id", "UUID" if dialect == "postgresql" else "VARCHAR(36)"),
            ("salary_range", "VARCHAR(128) NOT NULL DEFAULT ''"),
            ("work_location", "VARCHAR(32) NOT NULL DEFAULT ''"),
            ("job_type", "VARCHAR(32) NOT NULL DEFAULT ''"),
            ("recruitment_urgency", "VARCHAR(16) NOT NULL DEFAULT ''"),
            ("preferred_onboarding_date", "TIMESTAMP"),
            ("rankings_top_insight", "TEXT"),
            ("rankings_top_insight_cache_key", "VARCHAR(512)"),
        ]:
            if col not in existing_jobs:
                if dialect == "postgresql":
                    alters.append(f"ALTER TABLE jobs ADD COLUMN IF NOT EXISTS {col} {ddl}")
                else:
                    alters.append(f"ALTER TABLE jobs ADD COLUMN {col} {ddl}")

    if existing_clients:
        for col, ddl in [
            ("status", "VARCHAR(24) NOT NULL DEFAULT 'active'"),
            ("contact_person", "VARCHAR(256) NOT NULL DEFAULT ''"),
            ("email", "VARCHAR(320) NOT NULL DEFAULT ''"),
            ("company_name", "VARCHAR(256) NOT NULL DEFAULT ''"),
        ]:
            if col not in existing_clients:
                if dialect == "postgresql":
                    alters.append(f"ALTER TABLE clients ADD COLUMN IF NOT EXISTS {col} {ddl}")
                else:
                    alters.append(f"ALTER TABLE clients ADD COLUMN {col} {ddl}")

    if existing_job_attachments:
        # Back-compat columns if table existed in older DBs.
        for col, ddl in [
            ("content_type", "VARCHAR(128) NOT NULL DEFAULT 'application/octet-stream'"),
            ("size_bytes", "INTEGER NOT NULL DEFAULT 0"),
            ("storage_path", "VARCHAR(2048) NOT NULL DEFAULT ''"),
        ]:
            if col not in existing_job_attachments:
                if dialect == "postgresql":
                    alters.append(f"ALTER TABLE job_attachments ADD COLUMN IF NOT EXISTS {col} {ddl}")
                else:
                    alters.append(f"ALTER TABLE job_attachments ADD COLUMN {col} {ddl}")

    if existing_users:
        for col, ddl in [
            ("is_verified", "BOOLEAN NOT NULL DEFAULT 0" if dialect != "postgresql" else "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("verification_code_hash", "VARCHAR(256) NOT NULL DEFAULT ''"),
            ("verification_code_expires_at", "TIMESTAMP"),
            ("full_name", "VARCHAR(256) NOT NULL DEFAULT ''"),
            ("phone", "VARCHAR(64) NOT NULL DEFAULT ''"),
            ("address", "VARCHAR(512) NOT NULL DEFAULT ''"),
            ("company", "VARCHAR(256) NOT NULL DEFAULT ''"),
            ("available_hours", "VARCHAR(128) NOT NULL DEFAULT ''"),
            ("role_label", "VARCHAR(64) NOT NULL DEFAULT 'Recruiter'"),
            ("avatar_data", "TEXT"),
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


def ensure_indexes(engine: Engine) -> None:
    """
    Best-effort index creation for frequently filtered/sorted fields.
    Safe to run repeatedly; uses IF NOT EXISTS where supported.
    """
    dialect = engine.dialect.name
    stmts: list[str] = []

    # Candidates
    stmts.extend(
        [
            "CREATE INDEX IF NOT EXISTS idx_candidates_created_at ON candidates (created_at)",
            "CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates (status)",
            "CREATE INDEX IF NOT EXISTS idx_candidates_role_label ON candidates (role_label)",
        ]
    )

    # Jobs
    stmts.append("CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs (created_at)")
    stmts.append("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status)")
    stmts.append("CREATE INDEX IF NOT EXISTS idx_jobs_client_id ON jobs (client_id)")

    # Clients
    stmts.append("CREATE INDEX IF NOT EXISTS idx_clients_status ON clients (status)")
    stmts.append("CREATE INDEX IF NOT EXISTS idx_clients_created_at ON clients (created_at)")

    # Ingestions
    stmts.extend(
        [
            "CREATE INDEX IF NOT EXISTS idx_ingestions_status ON resume_ingestions (status)",
            "CREATE INDEX IF NOT EXISTS idx_ingestions_updated_at ON resume_ingestions (updated_at)",
            "CREATE INDEX IF NOT EXISTS idx_ingestions_batch_id ON resume_ingestions (batch_id)",
        ]
    )

    # Rankings already have job_id/candidate_id indexes via ORM; keep as-is.
    stmts.append("CREATE INDEX IF NOT EXISTS idx_job_attachments_job_id ON job_attachments (job_id)")
    stmts.append("CREATE INDEX IF NOT EXISTS idx_job_attachments_created_at ON job_attachments (created_at)")

    # SBERT shortlist cache
    stmts.append("CREATE INDEX IF NOT EXISTS idx_sbert_scores_job_id ON job_candidate_sbert_scores (job_id)")
    stmts.append("CREATE INDEX IF NOT EXISTS idx_sbert_scores_candidate_id ON job_candidate_sbert_scores (candidate_id)")
    stmts.append("CREATE INDEX IF NOT EXISTS idx_sbert_scores_updated_at ON job_candidate_sbert_scores (updated_at)")

    # User shortlist
    stmts.append("CREATE INDEX IF NOT EXISTS idx_shortlist_job_id ON job_shortlisted_candidates (job_id)")
    stmts.append("CREATE INDEX IF NOT EXISTS idx_shortlist_candidate_id ON job_shortlisted_candidates (candidate_id)")
    stmts.append("CREATE INDEX IF NOT EXISTS idx_shortlist_created_at ON job_shortlisted_candidates (created_at)")

    # Applicant tracking (single source of truth)
    stmts.append("CREATE INDEX IF NOT EXISTS idx_job_applicants_job_id ON job_applicants (job_id)")
    stmts.append("CREATE INDEX IF NOT EXISTS idx_job_applicants_candidate_id ON job_applicants (candidate_id)")
    stmts.append("CREATE INDEX IF NOT EXISTS idx_job_applicants_status ON job_applicants (status)")
    stmts.append("CREATE INDEX IF NOT EXISTS idx_job_applicants_updated_at ON job_applicants (updated_at)")

    with engine.begin() as conn:
        for stmt in stmts:
            try:
                conn.execute(text(stmt))
            except Exception:
                # SQLite/Postgres both support IF NOT EXISTS for CREATE INDEX; ignore any edge failures.
                continue
