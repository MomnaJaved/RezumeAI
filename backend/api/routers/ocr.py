"""OCR endpoint: accept an image of a printed resume, run OCR + parsing pipeline,
and return structured fields WITHOUT saving to the database.

The frontend shows a preview / edit step; the user corrects any OCR errors
and then explicitly saves by posting the (same) image to POST /uploads/resume.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Request, UploadFile

from api.dependencies import get_current_user_optional
from api.errors import RezumeAPIError
from api.models import User
from api.schemas import OcrParseResponse, OcrParsedFields
from api.services.resume_ingest import MAX_UPLOAD_BYTES, parse_upload
from api.slow_limiter import limiter

router = APIRouter(prefix="/ocr", tags=["ocr"])
_log = logging.getLogger("rezume.api")

_ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}
_ALLOWED_IMAGE_CT = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/tiff",
    "image/bmp",
    "application/octet-stream",
}


@router.post("/parse-resume", response_model=OcrParseResponse)
@limiter.limit("20/minute")
def ocr_parse_resume(
    request: Request,
    file: UploadFile = File(...),
    user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Accept an image file of a printed resume. Runs OCR (Tesseract) and the full
    parsing pipeline. Returns raw OCR text plus structured fields extracted from
    it. **Nothing is written to the database** — the response is intended for a
    preview / edit step before the user commits via POST /uploads/resume.

    Requires Tesseract + pytesseract installed on the server.
    Supported formats: PNG, JPEG, WebP, TIFF, BMP.
    """
    if not file.filename:
        raise RezumeAPIError("MISSING_FILENAME", "Missing filename.", 400)

    dot_suffix = Path(file.filename).suffix.lower()
    if dot_suffix not in _ALLOWED_IMAGE_EXT:
        raise RezumeAPIError(
            "UNSUPPORTED_FILE_TYPE",
            f"OCR only supports image files. Allowed: {', '.join(sorted(_ALLOWED_IMAGE_EXT))}.",
            415,
        )

    ct = (file.content_type or "").split(";")[0].strip().lower()
    if ct and ct not in _ALLOWED_IMAGE_CT:
        raise RezumeAPIError(
            "UNSUPPORTED_MEDIA_TYPE",
            f"Content-Type not accepted for OCR: {ct}",
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
        _log.exception("ocr_parse_resume failed: %s", e)
        raise RezumeAPIError("INFERENCE_ERROR", "OCR resume processing failed.", 503) from e

    fields = OcrParsedFields(
        full_name=parsed.get("full_name") or "",
        contact_email=parsed.get("contact_email") or "",
        title=parsed.get("title") or "",
        role_label=parsed.get("role_label") or "",
        skills=parsed.get("skills") or "",
        years_experience=parsed.get("years_experience"),
        highest_degree=parsed.get("highest_degree") or "",
        education_lines=parsed.get("education_lines") or "",
        certifications=parsed.get("certifications") or "",
    )

    return OcrParseResponse(
        raw_text=parsed.get("raw_text") or "",
        parsed_fields=fields,
        filename=parsed.get("filename") or file.filename,
        text_len=parsed.get("text_len", 0),
    )
