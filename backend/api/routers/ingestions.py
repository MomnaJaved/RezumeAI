from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

import numpy as np
from fastapi import APIRouter, BackgroundTasks, Depends, File, Request, UploadFile
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from api.database import get_db
from api.dependencies import require_user_if_auth_enabled
from api.errors import RezumeAPIError
from api.models import Candidate, ResumeIngestion, User
from api.schemas import (
    IngestionBatchOut,
    IngestionCreateText,
    IngestionOut,
    IngestionStatusOut,
)
from api.services import ml_ranking
from api.services.resume_ingest import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES, parse_upload
from api.services.sbert_shortlist import embed_text
from api.slow_limiter import limiter

router = APIRouter(prefix="/ingestions", tags=["ingestions"])
_log = logging.getLogger("rezume.api")

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


def _storage_root() -> Path:
    # Store under repo root by default (works in docker-compose if volume mounted).
    root = Path(os.environ.get("REZUME_UPLOAD_DIR", "")).expanduser()
    if str(root).strip():
        return root
    return Path.cwd() / "uploads" / "raw"


def _touch_updated(row: ResumeIngestion) -> None:
    row.updated_at = datetime.utcnow()


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

        ing.status = "done"
        _touch_updated(ing)
        db.commit()
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
    _: Optional[User] = Depends(require_user_if_auth_enabled),
):
    """
    Bulk upload many resumes at once (PDF/DOCX/TXT/images). Returns batch_id immediately,
    processes each file asynchronously, and creates Candidate rows.
    """
    if not files:
        raise RezumeAPIError("NO_FILES", "No files uploaded.", 400)

    batch_id = uuid4()
    root = _storage_root() / str(batch_id)
    root.mkdir(parents=True, exist_ok=True)

    accepted: list[IngestionOut] = []
    failed: list[IngestionOut] = []

    for f in files:
        fn = f.filename or ""
        if not fn:
            row = ResumeIngestion(batch_id=batch_id, source="bulk_upload", status="failed", error="Missing filename")
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
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        accepted.append(IngestionOut.model_validate(row))

        background.add_task(_process_one_ingestion, row.id, db.get_bind())

    return IngestionBatchOut(batch_id=batch_id, accepted=accepted, failed=failed)


@router.post("/text", response_model=IngestionOut)
@limiter.limit("30/minute")
def ingest_resume_text(
    request: Request,
    body: IngestionCreateText,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    _: Optional[User] = Depends(require_user_if_auth_enabled),
):
    """
    Text ingestion (Chrome extension / LinkedIn copy-paste / OCR text already extracted on-device).
    """
    batch_id = body.batch_id or uuid4()
    row = ResumeIngestion(
        batch_id=batch_id,
        source=body.source or "extension",
        status="queued",
        filename=body.filename or "resume.txt",
        content_type="text/plain",
        input_text=body.text.strip(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    background.add_task(_process_one_ingestion, row.id, db.get_bind())
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
    return IngestionStatusOut(
        batch_id=batch_id,
        total=len(rows),
        queued=sum(1 for r in rows if r.status == "queued"),
        processing=sum(1 for r in rows if r.status == "processing"),
        done=sum(1 for r in rows if r.status == "done"),
        failed=sum(1 for r in rows if r.status == "failed"),
        items=[IngestionOut.model_validate(r) for r in rows],
    )


@router.get("/{ingestion_id}", response_model=IngestionOut)
def get_ingestion(ingestion_id: UUID, db: Session = Depends(get_db)):
    row = db.query(ResumeIngestion).filter(ResumeIngestion.id == ingestion_id).first()
    if not row:
        raise RezumeAPIError("INGESTION_NOT_FOUND", "Ingestion not found.", 404)
    return IngestionOut.model_validate(row)

