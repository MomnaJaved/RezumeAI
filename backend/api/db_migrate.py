"""
Add columns to existing SQLite/Postgres DBs (create_all does not alter tables).
Called once from app lifespan after create_all.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

_log = logging.getLogger("rezume.api")


def _cols(engine: Engine, table: str) -> set[str]:
    insp = inspect(engine)
    if not insp.has_table(table):
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def ensure_extra_columns(engine: Engine) -> None:
    dialect = engine.dialect.name
    existing_rank = _cols(engine, "job_candidate_rankings")
    existing_sbert = _cols(engine, "job_candidate_sbert_scores")
    existing_cand = _cols(engine, "candidates")
    existing_jobs = _cols(engine, "jobs")
    existing_clients = _cols(engine, "clients")
    existing_job_attachments = _cols(engine, "job_attachments")
    existing_ing = _cols(engine, "resume_ingestions")
    existing_users = _cols(engine, "users")
    existing_events = _cols(engine, "activity_events")
    existing_inbox_messages = _cols(engine, "inbox_messages")
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
            ("workspace_id", "UUID" if dialect == "postgresql" else "VARCHAR(36)"),
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

    # SBERT cache: add workspace_id for per-recruiter score isolation.
    if existing_sbert and "workspace_id" not in existing_sbert:
        if dialect == "postgresql":
            alters.append("ALTER TABLE job_candidate_sbert_scores ADD COLUMN IF NOT EXISTS workspace_id UUID")
        else:
            alters.append("ALTER TABLE job_candidate_sbert_scores ADD COLUMN workspace_id VARCHAR(36)")

    if existing_jobs:
        for col, ddl in [
            ("workspace_id", "UUID" if dialect == "postgresql" else "VARCHAR(36)"),
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
            ("two_factor_enabled", "BOOLEAN NOT NULL DEFAULT 0" if dialect != "postgresql" else "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("password_reset_code_hash", "VARCHAR(256) NOT NULL DEFAULT ''"),
            ("password_reset_expires_at", "TIMESTAMP"),
        ]:
            if col not in existing_users:
                if dialect == "postgresql":
                    alters.append(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {ddl}")
                else:
                    alters.append(f"ALTER TABLE users ADD COLUMN {col} {ddl}")
        if "account_role" not in existing_users:
            ddl = "VARCHAR(24) NOT NULL DEFAULT 'recruiter'"
            if dialect == "postgresql":
                alters.append(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS account_role {ddl}")
            else:
                alters.append(f"ALTER TABLE users ADD COLUMN account_role {ddl}")
        if "workspace_id" not in existing_users:
            if dialect == "postgresql":
                alters.append("ALTER TABLE users ADD COLUMN IF NOT EXISTS workspace_id UUID")
            else:
                alters.append("ALTER TABLE users ADD COLUMN workspace_id VARCHAR(36)")

    if existing_clients and "workspace_id" not in existing_clients:
        if dialect == "postgresql":
            alters.append("ALTER TABLE clients ADD COLUMN IF NOT EXISTS workspace_id UUID")
        else:
            alters.append("ALTER TABLE clients ADD COLUMN workspace_id VARCHAR(36)")

    if existing_cand and "user_id" not in existing_cand:
        if dialect == "postgresql":
            alters.append("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS user_id UUID")
        else:
            alters.append("ALTER TABLE candidates ADD COLUMN user_id VARCHAR(36)")

    # Multi-tenant ownership on candidates (and mirror on resume_ingestions so
    # the background worker can stamp the workspace when the HTTP request is long gone).
    if existing_cand and "workspace_id" not in existing_cand:
        if dialect == "postgresql":
            alters.append("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS workspace_id UUID")
        else:
            alters.append("ALTER TABLE candidates ADD COLUMN workspace_id VARCHAR(36)")
    if existing_cand and "created_by_user_id" not in existing_cand:
        if dialect == "postgresql":
            alters.append("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS created_by_user_id UUID")
        else:
            alters.append("ALTER TABLE candidates ADD COLUMN created_by_user_id VARCHAR(36)")
    if existing_ing and "workspace_id" not in existing_ing:
        if dialect == "postgresql":
            alters.append("ALTER TABLE resume_ingestions ADD COLUMN IF NOT EXISTS workspace_id UUID")
        else:
            alters.append("ALTER TABLE resume_ingestions ADD COLUMN workspace_id VARCHAR(36)")

    if existing_jobs and "created_by_user_id" not in existing_jobs:
        if dialect == "postgresql":
            alters.append("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS created_by_user_id UUID")
        else:
            alters.append("ALTER TABLE jobs ADD COLUMN created_by_user_id VARCHAR(36)")

    if existing_events and "workspace_id" not in existing_events:
        if dialect == "postgresql":
            alters.append("ALTER TABLE activity_events ADD COLUMN IF NOT EXISTS workspace_id UUID")
        else:
            alters.append("ALTER TABLE activity_events ADD COLUMN workspace_id VARCHAR(36)")

    # Per-user notification isolation: only the owning user sees this event.
    if existing_events and "user_id" not in existing_events:
        if dialect == "postgresql":
            alters.append("ALTER TABLE activity_events ADD COLUMN IF NOT EXISTS user_id UUID")
        else:
            alters.append("ALTER TABLE activity_events ADD COLUMN user_id VARCHAR(36)")

    if existing_inbox_messages and "chat_scope" not in existing_inbox_messages:
        ddl = "VARCHAR(32) NOT NULL DEFAULT 'general'"
        if dialect == "postgresql":
            alters.append(f"ALTER TABLE inbox_messages ADD COLUMN IF NOT EXISTS chat_scope {ddl}")
        else:
            alters.append(f"ALTER TABLE inbox_messages ADD COLUMN chat_scope {ddl}")

    if existing_inbox_messages:
        bool_ddl = "BOOLEAN NOT NULL DEFAULT 0" if dialect != "postgresql" else "BOOLEAN NOT NULL DEFAULT FALSE"
        for col in ("hidden_for_sender", "hidden_for_recipient"):
            if col not in existing_inbox_messages:
                if dialect == "postgresql":
                    alters.append(f"ALTER TABLE inbox_messages ADD COLUMN IF NOT EXISTS {col} {bool_ddl}")
                else:
                    alters.append(f"ALTER TABLE inbox_messages ADD COLUMN {col} {bool_ddl}")

    # Candidate pool type: public (applied via portal) vs private (uploaded by recruiter).
    if existing_cand and "is_public" not in existing_cand:
        bool_ddl = "BOOLEAN NOT NULL DEFAULT FALSE" if dialect == "postgresql" else "BOOLEAN NOT NULL DEFAULT 0"
        if dialect == "postgresql":
            alters.append(f"ALTER TABLE candidates ADD COLUMN IF NOT EXISTS is_public {bool_ddl}")
        else:
            alters.append(f"ALTER TABLE candidates ADD COLUMN is_public {bool_ddl}")

    if alters:
        with engine.begin() as conn:
            for stmt in alters:
                conn.execute(text(stmt))

    # Backfill is_public for two cases:
    #  1. Candidates with no workspace and no uploader — they are self-registered (public pool).
    #  2. Candidates that have a linked portal account (user_id IS NOT NULL) — they must always be
    #     public regardless of workspace_id, because backfill_workspaces may have assigned a
    #     recruiter workspace to them after the fact (via job-link inference), which would otherwise
    #     make them look like private/recruiter-owned candidates and expose them to hard-deletion.
    if existing_cand and "is_public" in (_cols(engine, "candidates")):
        try:
            cols_now = _cols(engine, "candidates")
            if dialect == "postgresql":
                if "user_id" in cols_now:
                    stmt = (
                        "UPDATE candidates SET is_public = TRUE "
                        "WHERE is_public = FALSE AND ("
                        "  (workspace_id IS NULL AND created_by_user_id IS NULL)"
                        "  OR user_id IS NOT NULL"
                        ")"
                    )
                else:
                    stmt = (
                        "UPDATE candidates SET is_public = TRUE "
                        "WHERE workspace_id IS NULL AND created_by_user_id IS NULL AND is_public = FALSE"
                    )
            else:
                if "user_id" in cols_now:
                    stmt = (
                        "UPDATE candidates SET is_public = 1 "
                        "WHERE is_public = 0 AND ("
                        "  (workspace_id IS NULL AND created_by_user_id IS NULL)"
                        "  OR user_id IS NOT NULL"
                        ")"
                    )
                else:
                    stmt = (
                        "UPDATE candidates SET is_public = 1 "
                        "WHERE workspace_id IS NULL AND created_by_user_id IS NULL AND is_public = 0"
                    )
            with engine.begin() as conn:
                conn.execute(text(stmt))
        except Exception:
            pass

    # Per-recruiter soft-delete mapping table.
    try:
        with engine.begin() as conn:
            if dialect == "postgresql":
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS recruiter_candidate_hidden (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                        candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
                        hidden_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        CONSTRAINT uq_hidden_workspace_candidate UNIQUE (workspace_id, candidate_id)
                    )
                """))
            else:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS recruiter_candidate_hidden (
                        id VARCHAR(36) PRIMARY KEY,
                        workspace_id VARCHAR(36) NOT NULL,
                        candidate_id VARCHAR(36) NOT NULL,
                        hidden_at TIMESTAMP NOT NULL,
                        UNIQUE (workspace_id, candidate_id)
                    )
                """))
    except Exception:
        pass

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


def backfill_workspaces(engine: Engine) -> None:
    """
    One-time data migration: recruiter users get a workspace; jobs and clients pick up workspace_id.
    Safe to run repeatedly (only fills NULLs).
    """
    insp = inspect(engine)
    if not insp.has_table("workspaces"):
        return
    existing_users = _cols(engine, "users")
    existing_jobs = _cols(engine, "jobs")
    existing_clients = _cols(engine, "clients")
    if "workspace_id" not in existing_users or "workspace_id" not in existing_jobs:
        return

    from sqlalchemy.orm import sessionmaker

    from api.models import Client, Job, User, Workspace

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        # Recruiters without workspace: create one per user
        for u in db.query(User).all():
            role = (getattr(u, "account_role", None) or "recruiter").strip().lower()
            if role == "candidate":
                continue
            if getattr(u, "workspace_id", None) is not None:
                continue
            label = (u.email or "user").split("@")[0][:48] or "workspace"
            ws = Workspace(name=f"{label} workspace")
            db.add(ws)
            db.flush()
            u.workspace_id = ws.id
        db.commit()

        # Jobs: inherit creator's workspace
        if existing_jobs:
            for job in db.query(Job).filter(Job.workspace_id.is_(None)).all():  # noqa: E711
                uid = getattr(job, "created_by_user_id", None)
                if uid:
                    creator = db.query(User).filter(User.id == uid).first()
                    if creator and creator.workspace_id:
                        job.workspace_id = creator.workspace_id
            db.commit()

        # Orphan jobs (no creator): attach to a default workspace
        if existing_jobs:
            default_ws = db.query(Workspace).order_by(Workspace.created_at.asc()).first()
            if default_ws:
                for job in db.query(Job).filter(Job.workspace_id.is_(None)).all():  # noqa: E711
                    job.workspace_id = default_ws.id
                db.commit()

        # Clients: copy workspace from any linked job
        if existing_clients and "workspace_id" in existing_clients:
            for cl in db.query(Client).filter(Client.workspace_id.is_(None)).all():  # noqa: E711
                j = db.query(Job).filter(Job.client_id == cl.id, Job.workspace_id.isnot(None)).first()
                if j:
                    cl.workspace_id = j.workspace_id
            db.commit()

        # Candidates: infer workspace from any existing applicant/ranking/shortlist
        # link. A candidate that has no job link at all stays NULL — it's a true
        # orphan from before scoping existed; we deliberately don't guess a
        # workspace for it, otherwise fresh tenants would inherit unrelated
        # resumes on first boot.
        existing_cand = _cols(engine, "candidates")
        if existing_cand and "workspace_id" in existing_cand:
            from api.models import Candidate, JobApplicant, JobCandidateRanking, JobShortlistedCandidate

            def _pick_workspace(cand_id) -> Optional[uuid.UUID]:  # type: ignore[name-defined]
                for Link in (JobApplicant, JobCandidateRanking, JobShortlistedCandidate):
                    row = (
                        db.query(Job.workspace_id)
                        .join(Link, Link.job_id == Job.id)
                        .filter(Link.candidate_id == cand_id, Job.workspace_id.isnot(None))
                        .first()
                    )
                    if row and row[0] is not None:
                        return row[0]
                return None

            for cand in db.query(Candidate).filter(Candidate.workspace_id.is_(None)).all():  # noqa: E711
                ws_id = _pick_workspace(cand.id)
                if ws_id is not None:
                    cand.workspace_id = ws_id
            db.commit()
    except Exception as e:
        _log.warning("backfill_workspaces: %s", e)
        db.rollback()
    finally:
        db.close()


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
    stmts.append("CREATE INDEX IF NOT EXISTS idx_jobs_workspace_id ON jobs (workspace_id)")
    stmts.append("CREATE INDEX IF NOT EXISTS idx_users_workspace_id ON users (workspace_id)")
    stmts.append("CREATE INDEX IF NOT EXISTS idx_clients_workspace_id ON clients (workspace_id)")
    stmts.append("CREATE INDEX IF NOT EXISTS idx_candidates_workspace_id ON candidates (workspace_id)")
    stmts.append("CREATE INDEX IF NOT EXISTS idx_candidates_created_by_user_id ON candidates (created_by_user_id)")
    stmts.append("CREATE INDEX IF NOT EXISTS idx_ingestions_workspace_id ON resume_ingestions (workspace_id)")
    stmts.append("CREATE INDEX IF NOT EXISTS idx_activity_events_workspace_id ON activity_events (workspace_id)")
    stmts.append("CREATE INDEX IF NOT EXISTS idx_hidden_workspace_id ON recruiter_candidate_hidden (workspace_id)")
    stmts.append("CREATE INDEX IF NOT EXISTS idx_hidden_candidate_id ON recruiter_candidate_hidden (candidate_id)")
    stmts.append("CREATE INDEX IF NOT EXISTS idx_rankings_workspace_id ON job_candidate_rankings (workspace_id)")
    stmts.append("CREATE INDEX IF NOT EXISTS idx_sbert_scores_workspace_id ON job_candidate_sbert_scores (workspace_id)")
    stmts.append("CREATE INDEX IF NOT EXISTS idx_activity_events_user_id ON activity_events (user_id)")

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
