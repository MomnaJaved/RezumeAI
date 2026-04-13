"""Parse uploaded resume bytes → text + fields for Candidate rows."""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from src.inference.service import classify_role
from src.parsing.skill_mining import extract_skill_candidates
from src.parsing.feature_extractors import extract_certifications, extract_education, estimate_years_experience
from src.parsing.text_extractors import extract_text_any
from src.parsing.name_extractor import extract_name_from_raw
from src.parsing.title_extractor import extract_title_from_raw
from src.parsing.role_fine import infer_role_fine
from src.preprocessing.pii import strip_pii


ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}

MAX_UPLOAD_BYTES = 12 * 1024 * 1024

MIN_TEXT_CHARS = 80


def external_id_from_content(content: bytes) -> str:
    """Stable id for deduplicating identical uploads (prefix u_ vs dataset hex ids)."""
    return "u_" + hashlib.sha256(content).hexdigest()[:14]


def _storage_root() -> Path:
    root = Path(os.environ.get("REZUME_UPLOAD_DIR", "")).expanduser()
    if str(root).strip():
        return root
    return Path.cwd() / "uploads" / "raw"


def _safe_filename(name: str) -> str:
    # Keep it filesystem-safe but readable.
    return "".join(c if (c.isalnum() or c in ("-", "_", ".", " ")) else "_" for c in (name or "resume")).strip()[:160]


def _build_role_input(raw_clean: str, title: str, skills: str) -> str:
    """
    Help role classifier by front-loading strong signals within the 256-token budget.
    """
    head = raw_clean.splitlines()[:60]
    head_txt = "\n".join(head)
    parts = []
    if title.strip():
        parts.append(f"Title: {title.strip()}")
    if skills.strip():
        parts.append(f"Skills: {skills.strip()}")
    parts.append(head_txt)
    return "\n".join(parts).strip()


def parse_upload(filename: str, content: bytes) -> dict:
    """
    Returns dict: external_id, raw_text (PII-stripped), skills str, title, role_label,
    full_name hint from filename, original filename, text_len.
    Raises ValueError with user-facing message on failure.
    """
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError(f"File too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).")

    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported type {suffix or '(none)'}. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
        )

    ext_id = external_id_from_content(content)

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        raw = extract_text_any(tmp_path) or ""
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass

    raw = raw.strip()
    if len(raw) < MIN_TEXT_CHARS:
        raise ValueError(
            "Could not extract enough text. For scanned PDFs/images, install Tesseract + "
            "pytesseract (see docs) or upload a text-based PDF or .docx."
        )

    # Keep a clean-but-not-stripped copy for name heuristics.
    raw_clean = raw.replace("\r\n", "\n").replace("\r", "\n").strip()
    stripped = strip_pii(raw_clean)
    skills_list = extract_skill_candidates(stripped)[:80]
    skills = ", ".join(skills_list)
    # Title extraction needs real line breaks; use raw_clean (strip_pii() collapses whitespace).
    title = extract_title_from_raw(raw_clean)
    role_in = _build_role_input(raw_clean, title if title != "unknown" else "", skills)
    role_out = classify_role(role_in, strip_pii_input=True, return_probs=False)
    role_label = str(role_out.get("label", ""))
    role_fine = infer_role_fine(title if title != "unknown" else "", skills, raw_hint=raw_clean[:5000])

    stem = Path(filename).stem.replace("_", " ").strip()
    guessed = extract_name_from_raw(raw_clean)

    edu = extract_education(stripped)
    certs = extract_certifications(stripped)
    # Years must use newline-preserving text: strip_pii() collapses whitespace to one line,
    # which breaks section detection and makes edu hints match the entire resume.
    years = estimate_years_experience(raw_clean)

    # Persist the original file so the UI can download it later.
    store_dir = _storage_root()
    store_dir.mkdir(parents=True, exist_ok=True)
    store_path = store_dir / f"{ext_id}__{_safe_filename(filename)}"
    try:
        store_path.write_bytes(content)
    except OSError:
        store_path = None

    return {
        "external_id": ext_id,
        "raw_text": stripped,
        "skills": skills,
        "title": title if title != "unknown" else "",
        "role_label": role_label,
        "role_fine": role_fine,
        "full_name": guessed or stem or "candidate",
        "filename": filename,
        "storage_path": str(store_path) if store_path else "",
        "text_len": len(stripped),
        "years_experience": years if years > 0 else None,
        "highest_degree": edu.get("highest_degree") or "",
        "education_lines": edu.get("education_lines") or "",
        "certifications": certs or "",
    }
