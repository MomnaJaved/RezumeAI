from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import pdfplumber
import fitz  # pymupdf
import docx


def extract_text_pdf(pdf_path: Path) -> str:
    """
    PyMuPDF (fitz) first — usually faster on text-based PDFs.
    If text is still short, try pdfplumber (sometimes better on odd layouts).
    """
    text = ""
    try:
        doc = fitz.open(str(pdf_path))
        parts = []
        for page in doc:
            parts.append(page.get_text("text"))
        doc.close()
        text = "\n".join(parts).strip()
    except Exception:
        text = ""

    if len(text) < 200:
        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                parts = []
                for page in pdf.pages:
                    t = page.extract_text() or ""
                    if t:
                        parts.append(t)
                text2 = "\n".join(parts).strip()
                if len(text2) > len(text):
                    text = text2
        except Exception:
            pass

    return text


def extract_text_docx(docx_path: Path) -> str:
    try:
        d = docx.Document(str(docx_path))
        parts = [p.text for p in d.paragraphs if p.text and p.text.strip()]
        return "\n".join(parts).strip()
    except Exception:
        return ""


def extract_text_txt(txt_path: Path) -> str:
    try:
        return txt_path.read_text(errors="ignore").strip()
    except Exception:
        return ""


_TESSERACT_WINDOWS_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def _configure_tesseract() -> None:
    """Point pytesseract at the Tesseract binary.

    Priority:
    1. TESSERACT_CMD env var (explicit override).
    2. 'tesseract' already on PATH — do nothing.
    3. Windows default install location.
    """
    import os
    import shutil
    import pytesseract

    env_cmd = os.environ.get("TESSERACT_CMD", "").strip()
    if env_cmd:
        pytesseract.pytesseract.tesseract_cmd = env_cmd
        return

    if shutil.which("tesseract"):
        return

    from pathlib import Path as _Path
    if _Path(_TESSERACT_WINDOWS_PATH).exists():
        pytesseract.pytesseract.tesseract_cmd = _TESSERACT_WINDOWS_PATH


def extract_text_image(image_path: Path) -> str:
    """
    OCR for scanned resumes (PNG/JPEG/TIFF/WebP). Requires Pillow + pytesseract
    and the Tesseract binary installed on the system.
    On Windows, auto-detects the default Tesseract install path if not on PATH.
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return ""

    _configure_tesseract()

    try:
        im = Image.open(str(image_path))
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        # Single-column résumés often read better with PSM 6; multi-block / sidebar layouts with PSM 3.
        # Pick the run that looks most like a résumé (has an email-shaped token or longest text).
        _EMAILISH = re.compile(r"[A-Za-z0-9._%+-]{2,}@[A-Za-z0-9.-]{2,}\.[A-Za-z]{2,}")
        candidates: list[str] = []
        for cfg in (r"--psm 6 --oem 3", r"--psm 3 --oem 3", r"--psm 4 --oem 3", ""):
            try:
                raw = pytesseract.image_to_string(im, config=cfg.strip() or None) or ""
            except Exception:
                continue
            t = raw.strip()
            if t:
                candidates.append(t)
        if not candidates:
            return ""
        best = max(
            candidates,
            key=lambda s: (1 if _EMAILISH.search(s) else 0, len(s)),
        )
        return best
    except Exception:
        return ""


def extract_text_any(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return extract_text_pdf(path)
    if ext == ".docx":
        return extract_text_docx(path)
    if ext == ".txt":
        return extract_text_txt(path)
    if ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"):
        return extract_text_image(path)
    return ""
