"""Parse uploaded resume bytes → text + fields for Candidate rows."""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path

from api.paths import repo_root
from src.inference.service import classify_role
from src.parsing.skill_mining import extract_skill_candidates, is_noise, normalize
from src.parsing.feature_extractors import extract_certifications, extract_education, estimate_years_experience
from src.parsing.ocr_normalize import normalize_resume_text_for_ocr
from src.parsing.text_extractors import extract_text_any
from src.parsing.name_extractor import UNKNOWN_CANDIDATE, resolve_candidate_full_name
from src.parsing.role_labels import ROLE_LABELS_MULTI, title_to_role_label
from src.parsing.candidate_title_resolve import resolve_title_from_resume_text
from src.parsing.role_fine import infer_role_fine
from src.preprocessing.pii import extract_primary_email, strip_pii, strip_pii_keep_newlines

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}

MAX_UPLOAD_BYTES = 12 * 1024 * 1024

MIN_TEXT_CHARS = 80

_RE_SKILLS_HEADER = re.compile(r"^\s*Skills:\s*(.+?)\s*$", re.IGNORECASE)

# LinkedIn / profile paste: experience prose, locations, and UI fragments merged into `Skills:` lines.
_RE_RESUME_PROSE_IN_SKILL = re.compile(
    r"on-?site|self-?employed|zero\s+limit|achieving\s+up|cross-?functional|data-?driven|"
    r"hospital\s+data|integrating\s+ai|supporting\s+data|modules,\s*power|"
    r"and\s+\+\d+\s+skills|with\s+python\s*\(|,\s*accuracy\b|business\s+operations\s*$|"
    r"â·|·\s*on-?site",
    re.IGNORECASE,
)
_RE_LOCATIONISH_SKILL = re.compile(
    r"^(?:[\s,·]*)(?:riyadh|jeddah|dubai|doha|kuwait|manama|muscat|"
    r"pk\b|pakistan|india|saudi\s+arabia|uae|usa|uk\b|united\s+states|united\s+kingdom)\b",
    re.IGNORECASE,
)


def _mojibake_fix_skills_line(s: str) -> str:
    return (s or "").replace("â·", "·").replace("â€™", "'").replace("â€œ", '"')


def _sanitize_skills_list_tokens(parts: list[str], *, max_items: int = 80) -> list[str]:
    """
    Dedupe + drop resume prose / locations / LinkedIn UI that leaked into comma-separated skills.
    """
    out: list[str] = []
    seen: set[str] = set()
    for raw in parts:
        p = _mojibake_fix_skills_line((raw or "").strip())
        if not p or len(p) > 160:
            continue
        if p.lower().startswith("skills ") and len(p) > 8:
            p = p[7:].strip()
        if _RE_RESUME_PROSE_IN_SKILL.search(p):
            continue
        if len(p) < 60 and _RE_LOCATIONISH_SKILL.match(p):
            continue
        n = normalize(p)
        if not n or is_noise(n):
            continue
        k = n.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(n)
        if len(out) >= max_items:
            break
    return out


def _skills_from_explicit_skills_headers(text: str) -> list[str]:
    """
    Chrome extension and paste flows prepend `Skills: a, b, c` above the profile blob.
    Skill mining may return few or no tokens on noisy LinkedIn text — preserve the explicit list.
    """
    out: list[str] = []
    seen: set[str] = set()
    for line in (text or "").splitlines():
        m = _RE_SKILLS_HEADER.match(line.strip())
        if not m:
            continue
        chunk = _mojibake_fix_skills_line((m.group(1) or "").strip())
        if not chunk:
            continue
        for part in re.split(r"[,;|]\s*|\s{2,}", chunk):
            p = part.strip()
            if not p:
                continue
            if _RE_RESUME_PROSE_IN_SKILL.search(p):
                continue
            if len(p) < 60 and _RE_LOCATIONISH_SKILL.match(p):
                continue
            pn = normalize(p)
            if not pn or is_noise(pn) or len(pn) > 160:
                continue
            k = pn.lower()
            if k in seen:
                continue
            seen.add(k)
            out.append(pn)
    return out[:80]


def external_id_from_content(content: bytes) -> str:
    """Stable id for deduplicating identical uploads (prefix u_ vs dataset hex ids)."""
    return "u_" + hashlib.sha256(content).hexdigest()[:14]


def _storage_root() -> Path:
    """
    Base dir for persisted artifacts (uploads, attachments, batches).

    Precedence:
    - REZUME_STORAGE_ROOT: base dir for all runtime artifacts.
    - REZUME_UPLOAD_DIR: legacy alias for REZUME_STORAGE_ROOT (back-compat).
    - default: <repo>/backend/storage
    """
    base = Path(os.environ.get("REZUME_STORAGE_ROOT", "")).expanduser()
    if not str(base).strip():
        base = Path(os.environ.get("REZUME_UPLOAD_DIR", "")).expanduser()
    if not str(base).strip():
        base = repo_root() / "backend" / "storage"
    return base


def _safe_filename(name: str) -> str:
    # Keep it filesystem-safe but readable.
    return "".join(c if (c.isalnum() or c in ("-", "_", ".", " ")) else "_" for c in (name or "resume")).strip()[:160]


def _build_role_input(raw_clean: str, title: str, skills: str) -> str:
    """
    Help role classifier by front-loading strong signals within the 256-token budget.
    When no explicit title line exists, lead with skills so the model can infer frontend/backend/fullstack.
    """
    head = raw_clean.splitlines()[:60]
    head_txt = "\n".join(head)
    parts: list[str] = []
    t = (title or "").strip()
    sk = (skills or "").strip()
    if t:
        parts.append(f"Title: {t}")
        if sk:
            parts.append(f"Skills: {sk}")
    else:
        if sk:
            parts.append(f"Skills: {sk}")
            parts.append(f"Key skills: {sk[:400]}")
        parts.append("Title: (not stated; infer technical role from skills and experience.)")
    parts.append(head_txt)
    return "\n".join(parts).strip()


def parse_upload(filename: str, content: bytes) -> dict:
    """
    Returns dict: external_id, contact_email (first in text, if any), raw_text (PII-stripped),
    skills str, title, role_label,
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
    raw = normalize_resume_text_for_ocr(raw)
    if len(raw) < MIN_TEXT_CHARS:
        raise ValueError(
            "Could not extract enough text. For scanned PDFs/images, install Tesseract + "
            "pytesseract (see docs) or upload a text-based PDF or .docx."
        )

    # Keep a clean-but-not-stripped copy for name heuristics.
    raw_clean = raw.replace("\r\n", "\n").replace("\r", "\n").strip()
    contact_email = extract_primary_email(raw_clean)
    stripped = strip_pii(raw_clean)
    pii_safe_structural = strip_pii_keep_newlines(raw_clean)
    skills_list = extract_skill_candidates(stripped)[:120]
    header_skills = _skills_from_explicit_skills_headers(raw_clean)
    merged_in_order = header_skills + skills_list
    skills_list = _sanitize_skills_list_tokens(merged_in_order, max_items=80)
    skills = ", ".join(skills_list)

    # Years first: drives Fresher vs inferred title and seniority polish.
    years = estimate_years_experience(raw_clean)

    # Infer coarse role *before* the title so headline resolution can map e.g. frontend → "Frontend Developer"
    # when the CV has no explicit title line and skill-based role rules miss (common on sparse résumés).
    role_in = _build_role_input(raw_clean, "", skills)
    role_out = classify_role(role_in, strip_pii_input=True, return_probs=False)
    role_guess = str(role_out.get("label", "") or "").strip().lower()
    if not role_guess or role_guess not in ROLE_LABELS_MULTI:
        role_guess = "other"

    # Title: explicit line → skills inference → role headline (see candidate_title_resolve).
    title = resolve_title_from_resume_text(
        raw_clean, skills, years if years > 0 else None, role_label_hint=role_guess
    )
    title = (title or "").strip() or "Professional"

    # Coarse role label for filtering/routing (multi-dept). Prefer title mapping; else ML guess above.
    role_label = ""
    if (title or "").strip().lower() != "fresher" and (title or "").strip():
        role_label = title_to_role_label(title, multi_department=True)
    if not role_label:
        role_label = role_guess
    role_label = role_label.strip().lower()
    if role_label and role_label not in ROLE_LABELS_MULTI:
        role_label = "other"

    role_fine = infer_role_fine(title, skills, raw_hint=raw_clean[:5000])

    full_name, _name_src = resolve_candidate_full_name(raw_clean, contact_email)

    # Extension / paste often omits a "Name:" line (e.g. LinkedIn starts with About). Use .txt stem as hint.
    stem = Path(filename).stem.strip()
    stem_l = stem.lower()
    _bad_filename_stems = frozenset(
        {
            "resume",
            "candidate",
            "cv",
            "document",
            "text",
            "untitled",
            "unknown",
            "unknown candidate",
            "file",
            "export",
            "profile",
        }
    )
    if stem and len(stem) >= 2 and stem_l not in _bad_filename_stems:
        if not (full_name or "").strip() or (full_name or "").strip() == UNKNOWN_CANDIDATE:
            full_name = stem.replace("_", " ").replace("-", " ").strip()

    edu = extract_education(pii_safe_structural)
    certs = extract_certifications(pii_safe_structural)
    # Years must use newline-preserving text: strip_pii() collapses whitespace to one line,
    # which breaks section detection and makes edu hints match the entire resume.
    # (years already computed above for title resolution)

    # Persist the original file so the UI can download it later.
    store_dir = _storage_root() / "uploads" / "raw"
    store_dir.mkdir(parents=True, exist_ok=True)
    store_path = store_dir / f"{ext_id}__{_safe_filename(filename)}"
    try:
        store_path.write_bytes(content)
    except OSError:
        store_path = None

    return {
        "external_id": ext_id,
        "contact_email": contact_email,
        "raw_text": stripped,
        "skills": skills,
        "title": title,
        "role_label": role_label,
        "role_fine": role_fine,
        "full_name": full_name,
        "filename": filename,
        "storage_path": str(store_path) if store_path else "",
        "text_len": len(stripped),
        # Keep 0.0 for freshers / students so OCR and forms show a number instead of an empty field.
        "years_experience": round(float(years), 1),
        "highest_degree": edu.get("highest_degree") or "",
        "education_lines": edu.get("education_lines") or "",
        "certifications": certs or "",
    }
