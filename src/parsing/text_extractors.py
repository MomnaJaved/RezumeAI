from __future__ import annotations

import os
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


def _pil_variants_for_resume_ocr(im_rgb):
    """Contrast / invert passes help Tesseract read white-on-dark sidebar text (e.g. teal panels)."""
    from PIL import ImageEnhance, ImageOps

    variants = [im_rgb]
    L = im_rgb.convert("L")
    variants.append(L)
    try:
        variants.append(ImageOps.autocontrast(L, cutoff=1))
        variants.append(ImageEnhance.Contrast(L).enhance(2.2))
        inv = ImageOps.invert(L)
        variants.append(inv)
        variants.append(ImageOps.autocontrast(inv, cutoff=2))
        variants.append(ImageEnhance.Contrast(inv).enhance(1.9))
    except Exception:
        pass
    return variants


def _pil_variants_fast_for_resume_ocr(im_rgb):
    """First-pass variants only — enough for most printed/light-background résumés."""
    from PIL import ImageOps

    L = im_rgb.convert("L")
    try:
        return [im_rgb, L, ImageOps.autocontrast(L, cutoff=1)]
    except Exception:
        return [im_rgb, L]


def _tesseract_thread_suffix() -> str:
    raw = (os.environ.get("REZUME_OCR_TESS_THREADS") or "").strip()
    if not raw.isdigit():
        return ""
    n = max(1, min(int(raw), 8))
    return f" -c tessedit_num_threads={n}"


def _tesseract_config(base: str) -> str | None:
    """Merge PSM/OEM flags with optional thread count for Tesseract 4/5."""
    sfx = _tesseract_thread_suffix()
    s = f"{(base or '').strip()}{sfx}".strip()
    return s or None


def extract_text_image(image_path: Path) -> str:
    """
    OCR for scanned resumes (PNG/JPEG/TIFF/WebP). Requires Pillow + pytesseract
    and the Tesseract binary installed on the system.
    On Windows, auto-detects the default Tesseract install path if not on PATH.

    Speed: two-phase Tesseract — fast passes (3 image modes × PSM 6/3) first, then
    full variants × extra PSMs only if text still looks thin. Tune with REZUME_OCR_MAX_SIDE
    (default 1600), REZUME_OCR_TESS_THREADS (e.g. 4).
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return ""

    _configure_tesseract()

    _EMAILISH = re.compile(r"[A-Za-z0-9._%+-]{2,}@[A-Za-z0-9.-]{2,}\.[A-Za-z]{2,}")
    # Phase 1: document layout modes that work best on single-column résumés.
    _PSMS_FAST = (r"--psm 6 --oem 3", r"--psm 3 --oem 3")
    # Phase 2 (heavy image passes): all PSMs — inverted / high-contrast frames need 6/3 too for sidebars.
    _PSMS_ALL = _PSMS_FAST + (
        r"--psm 4 --oem 3",
        r"--psm 11 --oem 3",
        r"--psm 13 --oem 3",
        "",
    )

    def _merged_good(merged: str) -> bool:
        n = len(merged)
        if n >= 780:
            return True
        if n >= 420 and _EMAILISH.search(merged):
            return True
        # Strong body without email yet (e.g. no address on CV)
        if n >= 1100:
            return True
        return False

    try:
        im = Image.open(str(image_path))
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        w, h = im.size
        try:
            _max_px = int((os.environ.get("REZUME_OCR_MAX_SIDE") or "1600").strip())
        except ValueError:
            _max_px = 1600
        _max_px = max(960, min(_max_px, 2400))
        if max(w, h) > _max_px:
            scale = _max_px / float(max(w, h))
            im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)

        blobs: list[str] = []
        seen: set[str] = set()

        def _run_pass(frame, cfg: str) -> None:
            try:
                raw = pytesseract.image_to_string(frame, config=_tesseract_config(cfg)) or ""
            except Exception:
                return
            t = raw.strip()
            if len(t) < 12 or t in seen:
                return
            seen.add(t)
            blobs.append(t)

        # Phase 1 — typically 6 Tesseract runs; enough for many phone captures.
        for frame in _pil_variants_fast_for_resume_ocr(im):
            for cfg in _PSMS_FAST:
                _run_pass(frame, cfg)
                merged = "\n".join(blobs)
                if _merged_good(merged):
                    return merged[:42000]

        # Phase 2 — contrast + invert variants; run full PSM set (phase 1 only hit first 3 frames).
        all_variants = _pil_variants_for_resume_ocr(im)
        for frame in all_variants[3:]:
            for cfg in _PSMS_ALL:
                _run_pass(frame, cfg)
                merged = "\n".join(blobs)
                if _merged_good(merged):
                    return merged[:42000]

        if not blobs:
            return ""
        blobs.sort(
            key=lambda s: (1 if _EMAILISH.search(s) else 0, 1 if "@" in s else 0, len(s)),
            reverse=True,
        )
        return "\n".join(blobs[:18])[:42000]
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
