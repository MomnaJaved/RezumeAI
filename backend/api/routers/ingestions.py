from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

import numpy as np
from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, Request, UploadFile
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from api.database import get_db
from api.dependencies import get_current_user_optional, require_user_if_auth_enabled
from api.errors import RezumeAPIError
from api.models import Candidate, ResumeIngestion, User
from api.schemas import (
    IngestionBatchOut,
    IngestionCreateText,
    IngestionOut,
    IngestionStatusOut,
)
from api.services import ml_ranking
from api.services.resume_ingest import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES, _storage_root, parse_upload
from api.services.sbert_shortlist import embed_text
from api.services.activity_log import log_activity
from api.services.candidate_display import display_full_name_from_db
from api.services.workspace_scope import ensure_workspace_for_recruiter
from src.parsing.name_extractor import UNKNOWN_CANDIDATE
from api.slow_limiter import limiter

router = APIRouter(prefix="/ingestions", tags=["ingestions"])
_log = logging.getLogger("rezume.api")

_STALE_PROCESSING_MINUTES = int(os.environ.get("REZUME_INGESTION_STALE_MINUTES", "20") or "20")

_ALLOWED_CT = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/tiff",
    "application/octet-stream",
}


def _touch_updated(row: ResumeIngestion) -> None:
    row.updated_at = datetime.utcnow()


def _mark_stale_processing_failed(db: Session, rows: list[ResumeIngestion]) -> None:
    """
    Ingestions are processed via in-process BackgroundTasks.
    If the API server restarts/reloads, those tasks die and rows can remain "processing" forever.
    Mark old processing rows as failed so the UI doesn't hang indefinitely.
    """
    if _STALE_PROCESSING_MINUTES <= 0:
        return
    now = datetime.utcnow()
    changed = False
    for r in rows:
        if r.status != "processing":
            continue
        age_s = (now - (r.updated_at or r.created_at or now)).total_seconds()
        if age_s >= float(_STALE_PROCESSING_MINUTES) * 60.0:
            r.status = "failed"
            r.error = (
                r.error.strip()
                or "Ingestion worker was interrupted (server restart/reload). Please retry the ingestion."
            )
            _touch_updated(r)
            changed = True
    if changed:
        db.commit()


def _process_one_ingestion(ingestion_id: UUID, engine: Engine) -> None:
    """
    Background worker: parse + create/update candidate + compute embedding.
    Uses a fresh DB session bound to the same engine as the request.
    """
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db: Session = SessionLocal()
    try:
        ing = db.query(ResumeIngestion).filter(ResumeIngestion.id == ingestion_id).first()
        if not ing:
            return

        ing.status = "processing"
        ing.error = ""
        _touch_updated(ing)
        db.commit()

        parsed = None
        extracted_text = ""

        if ing.input_text.strip():
            # Extension / text mode: treat input_text as the extracted resume text.
            extracted_text = ing.input_text.strip()
            # Build a fake "upload" parse result with stable ID from bytes of text.
            parsed = parse_upload(ing.filename or "resume.txt", extracted_text.encode("utf-8", errors="ignore"))
        else:
            if not ing.storage_path:
                raise ValueError("Missing storage_path and input_text")
            p = Path(ing.storage_path)
            if not p.exists():
                raise ValueError("Stored file not found")
            content = p.read_bytes()
            parsed = parse_upload(ing.filename or p.name, content)
            extracted_text = parsed.get("raw_text", "")

        ing.extracted_text = extracted_text[:200000]  # avoid runaway storage
        ing.candidate_external_id = str(parsed.get("external_id", "") or "")
        _touch_updated(ing)
        db.commit()

        # Workspace ownership was captured on the ingestion row at request
        # time — carry it onto the candidate so the uploader's workspace sees
        # the new profile even before it's attached to a job.
        ing_workspace_id = getattr(ing, "workspace_id", None)

        # Upsert candidate
        ext_id = parsed["external_id"]
        existing = db.query(Candidate).filter(Candidate.external_id == ext_id).first()
        if existing:
            existing.full_name = parsed["full_name"]
            existing.title = parsed["title"]
            existing.role_label = parsed["role_label"]
            existing.role_fine = parsed.get("role_fine") or getattr(existing, "role_fine", "unknown")
            existing.skills = parsed["skills"]
            existing.raw_text = parsed["raw_text"]
            existing.filename = parsed["filename"]
            if parsed.get("storage_path"):
                existing.storage_path = parsed["storage_path"]
            existing.years_experience = parsed.get("years_experience")
            existing.highest_degree = parsed.get("highest_degree") or ""
            existing.education_lines = parsed.get("education_lines") or ""
            existing.certifications = parsed.get("certifications") or ""
            if parsed.get("contact_email"):
                existing.contact_email = parsed["contact_email"]
            if not getattr(existing, "status", ""):
                existing.status = "new"
            # Claim unowned candidates; don't overwrite another workspace's ownership.
            if ing_workspace_id is not None and getattr(existing, "workspace_id", None) is None:
                existing.workspace_id = ing_workspace_id
            cand = existing
        else:
            cand = Candidate(
                external_id=ext_id,
                full_name=parsed["full_name"],
                title=parsed["title"],
                role_label=parsed["role_label"],
                role_fine=parsed.get("role_fine") or "unknown",
                skills=parsed["skills"],
                raw_text=parsed["raw_text"],
                filename=parsed["filename"],
                storage_path=parsed.get("storage_path") or "",
                years_experience=parsed.get("years_experience"),
                highest_degree=parsed.get("highest_degree") or "",
                education_lines=parsed.get("education_lines") or "",
                certifications=parsed.get("certifications") or "",
                contact_email=parsed.get("contact_email") or "",
                status="new",
                workspace_id=ing_workspace_id,
            )
            db.add(cand)

        db.commit()
        db.refresh(cand)

        # Compute and store SBERT embedding for shortlist (semantic vectors)
        try:
            cand_text = (ml_ranking.build_cand_text_from_db(cand) or "").strip()
            if cand_text:
                v = embed_text(cand_text).astype(np.float32, copy=False)
                cand.embedding_sbert = v.tobytes()
                db.commit()
        except Exception as e:
            _log.info("Embedding skipped for cand=%s (%s)", cand.external_id, e)

        # Stage-1 matching: refresh SBERT shortlist cache (background worker already).
        try:
            from api.services.sbert_cache import refresh_sbert_for_all_jobs

            # Update Top-K shortlists for all jobs (fast retrieval cache). Cross-encoder remains user-triggered.
            refresh_sbert_for_all_jobs(db, top_k=200, only_active=False)
        except Exception as e:
            _log.info("SBERT shortlist refresh skipped (%s)", e)

        ing.status = "done"
        _touch_updated(ing)
        db.commit()
        # User-facing notification (history/log). Best-effort.
        try:
            label = display_full_name_from_db(cand.full_name) if cand else UNKNOWN_CANDIDATE
            log_activity(db, kind="candidate_added", message=f"{label} added to the pool", href="/candidates")
        except Exception:
            pass
    except Exception as e:
        try:
            ing = db.query(ResumeIngestion).filter(ResumeIngestion.id == ingestion_id).first()
            if ing:
                ing.status = "failed"
                ing.error = str(e)[:4000]
                _touch_updated(ing)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


@router.post("/bulk", response_model=IngestionBatchOut)
@limiter.limit("10/minute")
def ingest_bulk_resumes(
    request: Request,
    background: BackgroundTasks,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
    _: Optional[User] = Depends(require_user_if_auth_enabled),
):
    """
    Bulk upload many resumes at once (PDF/DOCX/TXT/images). Returns batch_id immediately,
    processes each file asynchronously, and creates Candidate rows.
    """
    if not files:
        raise RezumeAPIError("NO_FILES", "No files uploaded.", 400)

    # Resolve the uploading recruiter's workspace once so every ingestion row
    # in this batch carries it; the background worker reads it off the row.
    upload_workspace_id = None
    if user is not None and (getattr(user, "account_role", "recruiter") or "recruiter").strip().lower() != "candidate":
        upload_workspace_id = ensure_workspace_for_recruiter(db, user)

    batch_id = uuid4()
    root = _storage_root() / "ingestions" / "raw" / str(batch_id)
    root.mkdir(parents=True, exist_ok=True)

    accepted: list[IngestionOut] = []
    failed: list[IngestionOut] = []

    for f in files:
        fn = f.filename or ""
        if not fn:
            row = ResumeIngestion(
                batch_id=batch_id,
                source="bulk_upload",
                status="failed",
                error="Missing filename",
                workspace_id=upload_workspace_id,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            failed.append(IngestionOut.model_validate(row))
            continue

        ext = Path(fn).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            row = ResumeIngestion(
                batch_id=batch_id,
                source="bulk_upload",
                status="failed",
                filename=fn,
                content_type=f.content_type or "",
                error=f"Unsupported file type: {ext}",
                workspace_id=upload_workspace_id,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            failed.append(IngestionOut.model_validate(row))
            continue

        ct = (f.content_type or "").split(";")[0].strip().lower()
        if ct and ct not in _ALLOWED_CT:
            row = ResumeIngestion(
                batch_id=batch_id,
                source="bulk_upload",
                status="failed",
                filename=fn,
                content_type=ct,
                error=f"Content-Type not accepted: {ct}",
                workspace_id=upload_workspace_id,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            failed.append(IngestionOut.model_validate(row))
            continue

        content = f.file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            row = ResumeIngestion(
                batch_id=batch_id,
                source="bulk_upload",
                status="failed",
                filename=fn,
                content_type=ct,
                error="File too large",
                workspace_id=upload_workspace_id,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            failed.append(IngestionOut.model_validate(row))
            continue

        # Save raw file to disk
        safe_name = f"{int(time.time()*1000)}_{Path(fn).name}"
        disk_path = root / safe_name
        disk_path.write_bytes(content)

        row = ResumeIngestion(
            batch_id=batch_id,
            source="bulk_upload",
            status="queued",
            filename=fn,
            content_type=ct,
            storage_path=str(disk_path),
            workspace_id=upload_workspace_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        accepted.append(IngestionOut.model_validate(row))

        engine = db.get_bind()
        assert isinstance(engine, Engine)
        background.add_task(_process_one_ingestion, row.id, engine)

    return IngestionBatchOut(batch_id=batch_id, accepted=accepted, failed=failed)


@router.post("/text", response_model=IngestionOut)
@limiter.limit("30/minute")
def ingest_resume_text(
    request: Request,
    body: IngestionCreateText,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
    _: Optional[User] = Depends(require_user_if_auth_enabled),
):
    """
    Text ingestion (Chrome extension / LinkedIn copy-paste / OCR text already extracted on-device).
    """
    upload_workspace_id = None
    if user is not None and (getattr(user, "account_role", "recruiter") or "recruiter").strip().lower() != "candidate":
        upload_workspace_id = ensure_workspace_for_recruiter(db, user)

    batch_id = body.batch_id or uuid4()
    row = ResumeIngestion(
        batch_id=batch_id,
        source=body.source or "extension",
        status="queued",
        filename=body.filename or "resume.txt",
        content_type="text/plain",
        input_text=body.text.strip(),
        workspace_id=upload_workspace_id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    engine = db.get_bind()
    assert isinstance(engine, Engine)
    background.add_task(_process_one_ingestion, row.id, engine)
    return IngestionOut.model_validate(row)


@router.get("/batch/{batch_id}", response_model=IngestionStatusOut)
def get_batch_status(batch_id: UUID, db: Session = Depends(get_db)):
    rows = (
        db.query(ResumeIngestion)
        .filter(ResumeIngestion.batch_id == batch_id)
        .order_by(ResumeIngestion.created_at.asc())
        .all()
    )
    if not rows:
        raise RezumeAPIError("BATCH_NOT_FOUND", "Batch not found.", 404)
    _mark_stale_processing_failed(db, rows)
    return IngestionStatusOut(
        batch_id=batch_id,
        total=len(rows),
        queued=sum(1 for r in rows if r.status == "queued"),
        processing=sum(1 for r in rows if r.status == "processing"),
        done=sum(1 for r in rows if r.status == "done"),
        failed=sum(1 for r in rows if r.status == "failed"),
        items=[IngestionOut.model_validate(r) for r in rows],
    )


@router.get("/recent", response_model=list[IngestionOut])
def list_recent_ingestions(
    status: str = Query(..., description="queued | processing | done"),
    since_hours: Optional[int] = Query(
        None,
        ge=1,
        le=168,
        description="When status=done, only rows updated within this many hours (e.g. 24 for dashboard).",
    ),
    limit: int = Query(25, ge=1, le=50),
    db: Session = Depends(get_db),
    _: Optional[User] = Depends(require_user_if_auth_enabled),
):
    """
    Recent resume ingestions across all batches (for dashboard drill-down).
    Must stay above GET /{ingestion_id} so 'recent' is not parsed as a UUID.
    """
    st = (status or "").strip().lower()
    if st not in ("queued", "processing", "done"):
        raise RezumeAPIError("BAD_STATUS", "status must be queued, processing, or done.", 400)
    try:
        q = db.query(ResumeIngestion).filter(ResumeIngestion.status == st)
        if st == "done" and since_hours is not None:
            since = datetime.utcnow() - timedelta(hours=since_hours)
            q = q.filter(ResumeIngestion.updated_at >= since)
        rows = q.order_by(ResumeIngestion.updated_at.desc()).limit(limit).all()
    except Exception:
        return []
    _mark_stale_processing_failed(db, rows)
    return [IngestionOut.model_validate(r) for r in rows]


@router.get("/{ingestion_id}", response_model=IngestionOut)
def get_ingestion(ingestion_id: UUID, db: Session = Depends(get_db)):
    row = db.query(ResumeIngestion).filter(ResumeIngestion.id == ingestion_id).first()
    if not row:
        raise RezumeAPIError("INGESTION_NOT_FOUND", "Ingestion not found.", 404)
    _mark_stale_processing_failed(db, [row])
    return IngestionOut.model_validate(row)


@router.post("/{ingestion_id}/retry", response_model=IngestionOut)
def retry_ingestion(
    ingestion_id: UUID,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    _: Optional[User] = Depends(require_user_if_auth_enabled),
):
    """
    Retry a failed/stale ingestion. Useful when an in-process background task was interrupted.
    """
    row = db.query(ResumeIngestion).filter(ResumeIngestion.id == ingestion_id).first()
    if not row:
        raise RezumeAPIError("INGESTION_NOT_FOUND", "Ingestion not found.", 404)
    if row.status == "done":
        return IngestionOut.model_validate(row)
    row.status = "queued"
    row.error = ""
    _touch_updated(row)
    db.commit()
    db.refresh(row)
    engine = db.get_bind()
    assert isinstance(engine, Engine)
    background.add_task(_process_one_ingestion, row.id, engine)
    return IngestionOut.model_validate(row)

