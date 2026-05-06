from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from api.database import get_db
from api.dependencies import get_current_user_optional
from api.errors import RezumeAPIError
from api.models import Candidate, RecruiterCandidateHidden, User
from api.schemas import CandidateRead, OcrScanSavePayload, ResumeUploadResponse
from api.services.resume_ingest import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES, parse_upload, parse_upload_from_ocr_preview
from api.services.workspace_scope import ensure_workspace_for_recruiter
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
    scan_save_json: Optional[str] = Form(
        None,
        description="If set, JSON of OcrScanSavePayload matching this file's external_id — skips full re-parse/OCR.",
    ),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
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

    # Always require a signed-in user. Anonymous uploads created Candidate rows
    # without user_id, so portal users lost their profile after reload and could
    # not apply or appear to recruiters (REQUIRE_AUTH=false used to allow this).
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to upload a resume. Your profile is saved on your account.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    content = file.file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise RezumeAPIError(
            "FILE_TOO_LARGE",
            f"File too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).",
            413,
        )

    try:
        if scan_save_json and scan_save_json.strip():
            try:
                payload = OcrScanSavePayload.model_validate_json(scan_save_json)
            except Exception as e:
                raise RezumeAPIError("INVALID_SCAN_SAVE", f"Invalid scan_save_json: {e}", 422) from e
            parsed = parse_upload_from_ocr_preview(file.filename, content, payload)
        else:
            parsed = parse_upload(file.filename, content)
    except ValueError as e:
        raise RezumeAPIError("PARSE_FAILED", str(e), 422) from e
    except Exception as e:
        _log.exception("parse_upload failed: %s", e)
        raise RezumeAPIError("INFERENCE_ERROR", "Resume processing failed.", 503) from e

    # Resolve the uploading recruiter's workspace up-front so both new and
    # existing-but-unowned candidate rows get stamped. Without this, uploaded
    # resumes stay invisible to the recruiter who uploaded them (the dashboard
    # and /candidates lists are workspace-scoped).
    recruiter_workspace_id = None
    recruiter_user_id = None
    if user is not None and (getattr(user, "account_role", "recruiter") or "recruiter").strip().lower() != "candidate":
        recruiter_workspace_id = ensure_workspace_for_recruiter(db, user)
        recruiter_user_id = user.id

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
        # Force SBERT recompute so updated resume content feeds into matching.
        existing.embedding_sbert = None
        # Claim any unowned candidate (workspace_id still NULL) into the
        # recruiter's workspace.  This covers two cases:
        #   a) A purely anonymous upload the recruiter now re-uploads → claim it.
        #   b) A portal candidate (is_public=True / user_id set) whose resume the
        #      recruiter is explicitly uploading.  The recruiter is saying "I want
        #      this person in my pool."  We honour that by stamping workspace_id
        #      so they appear in the candidates table.  Crucially we do NOT touch
        #      is_public or user_id — the candidate keeps full portal ownership.
        # We never overwrite a workspace that is already set (that would let a
        # tenant yank another tenant's row).
        existing_has_portal_link = getattr(existing, "user_id", None) is not None
        existing_is_public = getattr(existing, "is_public", False)
        if (
            recruiter_workspace_id is not None
            and getattr(existing, "workspace_id", None) is None
        ):
            existing.workspace_id = recruiter_workspace_id
            if getattr(existing, "created_by_user_id", None) is None and not existing_has_portal_link:
                existing.created_by_user_id = recruiter_user_id
            # Only mark non-portal candidates as private.  Portal candidates keep
            # their is_public=True so the candidate can still manage their profile.
            if not existing_has_portal_link and not existing_is_public:
                existing.is_public = False
        # If this recruiter previously "deleted" (soft-hid) this candidate from their pool,
        # and they are explicitly uploading the candidate again, unhide it so it reappears.
        if recruiter_workspace_id is not None:
            db.query(RecruiterCandidateHidden).filter(
                RecruiterCandidateHidden.workspace_id == recruiter_workspace_id,
                RecruiterCandidateHidden.candidate_id == existing.id,
            ).delete(synchronize_session=False)
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
            workspace_id=recruiter_workspace_id,
            created_by_user_id=recruiter_user_id,
            is_public=False,
        )
        db.add(cand)
        db.commit()
        db.refresh(cand)
        note = "created"

    if user is not None and getattr(user, "account_role", "recruiter") == "candidate":
        # Find old linked candidate row (if any) before we unlink it.
        # When the candidate uploads a *different* file, a brand-new Candidate row
        # is created (different external_id).  We copy workspace_id from the old row
        # so recruiters who previously claimed this person still see the updated profile.
        old_linked = (
            db.query(Candidate)
            .filter(Candidate.user_id == user.id, Candidate.id != cand.id)
            .first()
        )
        if old_linked is not None and getattr(cand, "workspace_id", None) is None:
            cand.workspace_id = getattr(old_linked, "workspace_id", None)
            cand.created_by_user_id = getattr(old_linked, "created_by_user_id", None)

        db.query(Candidate).filter(Candidate.user_id == user.id, Candidate.id != cand.id).update({"user_id": None}, synchronize_session=False)
        cand.user_id = user.id
        cand.is_public = True
        # Force SBERT embedding recompute so matching uses the new resume content.
        cand.embedding_sbert = None
        db.commit()
        db.refresh(cand)

    _log.info("Resume upload %s external_id=%s bytes=%s", note, cand.external_id, len(content))
    return ResumeUploadResponse(
        status=note,
        text_len=parsed["text_len"],
        candidate=CandidateRead.model_validate(cand),
    )
