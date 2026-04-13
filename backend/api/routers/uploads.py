from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.orm import Session

from api.database import get_db
from api.dependencies import require_user_if_auth_enabled
from api.errors import RezumeAPIError
from api.models import Candidate, User
from api.schemas import CandidateRead, ResumeUploadResponse
from api.services.resume_ingest import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES, parse_upload
from api.slow_limiter import limiter

router = APIRouter(prefix="/uploads", tags=["uploads"])
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


@router.post("/resume", response_model=ResumeUploadResponse)
@limiter.limit("40/minute")
def upload_resume(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: Optional[User] = Depends(require_user_if_auth_enabled),
):
    """
    Accept PDF, DOCX, TXT, or image (OCR if Tesseract is installed).
    Creates or updates a **Candidate** row so you can rank them with
    `POST /api/v1/jobs/{job_id}/rank-database-candidates`.
    """
    if not file.filename:
        raise RezumeAPIError("MISSING_FILENAME", "Missing filename.", 400)

    dot_suffix = Path(file.filename).suffix.lower()
    if dot_suffix not in ALLOWED_EXTENSIONS:
        raise RezumeAPIError(
            "UNSUPPORTED_FILE_TYPE",
            f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}.",
            415,
        )

    ct = (file.content_type or "").split(";")[0].strip().lower()
    if ct and ct not in _ALLOWED_CT:
        raise RezumeAPIError(
            "UNSUPPORTED_MEDIA_TYPE",
            f"Content-Type not accepted: {ct}",
            415,
        )

    content = file.file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise RezumeAPIError(
            "FILE_TOO_LARGE",
            f"File too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).",
            413,
        )

    try:
        parsed = parse_upload(file.filename, content)
    except ValueError as e:
        raise RezumeAPIError("PARSE_FAILED", str(e), 422) from e
    except Exception as e:
        _log.exception("parse_upload failed: %s", e)
        raise RezumeAPIError("INFERENCE_ERROR", "Resume processing failed.", 503) from e

    existing = db.query(Candidate).filter(Candidate.external_id == parsed["external_id"]).first()
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
        # Keep existing.status unless it's empty (back-compat).
        if not getattr(existing, "status", ""):
            existing.status = "new"
        db.commit()
        db.refresh(existing)
        cand = existing
        note = "updated_existing"
    else:
        cand = Candidate(
            external_id=parsed["external_id"],
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
        note = "created"

    _log.info("Resume upload %s external_id=%s bytes=%s", note, cand.external_id, len(content))
    return ResumeUploadResponse(
        status=note,
        text_len=parsed["text_len"],
        candidate=CandidateRead.model_validate(cand),
    )
