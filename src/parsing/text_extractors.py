from __future__ import annotations

import os
import re
from pathlib import Path

import pdfplumber
import fitz  # pymupdf
import docx


def extract_text_pdf(pdf_path: Path) -> str:
    """
    PyMuPDF (fitz) first — usually faster on text-based PDFs.
    If text is still short, try pdfplumber (sometimes better on odd layouts).
    If still short, rasterize pages and OCR (scanned PDFs) when Tesseract + pytesseract are available.
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

    if len(text) < 200:
        ocr = _extract_text_pdf_via_ocr(pdf_path)
        if len(ocr) > len(text):
            text = ocr

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
# Known installs when `tesseract` is not on a minimal PATH (IDE launches, partial brew runs).
_TESSERACT_KNOWN_PATHS: tuple[str, ...] = (
    "/opt/miniconda3/bin/tesseract",
    "/opt/anaconda3/bin/tesseract",
    "/opt/homebrew/bin/tesseract",
    "/usr/local/bin/tesseract",
)


def _configure_tesseract() -> None:
    """Point pytesseract at the Tesseract binary.

    Priority:
    1. TESSERACT_CMD env var (explicit override).
    2. 'tesseract' already on PATH — do nothing.
    3. conda-forge / Homebrew common absolute paths (macOS).
    4. ~/.miniconda3 / ~/anaconda3 (user-local installs).
    5. Windows default install location.
    """
    import shutil
    import pytesseract

    env_cmd = os.environ.get("TESSERACT_CMD", "").strip()
    if env_cmd:
        pytesseract.pytesseract.tesseract_cmd = env_cmd
        return

    if shutil.which("tesseract"):
        return

    home = Path.home()
    candidates: list[Path] = [Path(p) for p in _TESSERACT_KNOWN_PATHS]
    candidates.extend(
        (
            home / "miniconda3" / "bin" / "tesseract",
            home / "anaconda3" / "bin" / "tesseract",
        )
    )
    for p in candidates:
        if p.is_file():
            pytesseract.pytesseract.tesseract_cmd = str(p)
            return

    if Path(_TESSERACT_WINDOWS_PATH).exists():
        pytesseract.pytesseract.tesseract_cmd = _TESSERACT_WINDOWS_PATH


def _require_tesseract_binary() -> None:
    """Raise ValueError with install hints if the Tesseract executable is unusable."""
    import pytesseract
    from pytesseract.pytesseract import TesseractNotFoundError

    _configure_tesseract()
    try:
        pytesseract.get_tesseract_version()
    except TesseractNotFoundError as e:
        raise ValueError(
            "Tesseract OCR is not installed or not found. Options: (1) brew install tesseract — "
            "run only one install at a time; if brew reports a 'locked' error, wait for the other "
            "terminal to finish or close it. (2) conda install -c conda-forge tesseract "
            "(then restart the API). (3) Set TESSERACT_CMD to the full path to the tesseract binary."
        ) from e


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


def _maybe_deskew_rgb_pil(im):
    """
    Deskew scanned pages (camera skew) before Tesseract. Uses OpenCV when installed;
    set REZUME_OCR_DESKEW=0 to skip. No-op if opencv-python-headless is missing.
    """
    if (os.environ.get("REZUME_OCR_DESKEW") or "1").strip().lower() in ("0", "false", "no"):
        return im
    try:
        import cv2  # type: ignore[import-untyped]
        import numpy as np
        from PIL import Image
    except ImportError:
        return im

    try:
        rgb = im.convert("RGB")
        arr = np.asarray(rgb)
        h, w = arr.shape[:2]
        if min(h, w) < 120:
            return im
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        inv = cv2.bitwise_not(gray)
        thr = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        coords = np.column_stack(np.where(thr > 0))
        if coords.shape[0] < 80:
            return im
        ang = float(cv2.minAreaRect(coords)[-1])
        if ang < -45:
            ang = 90 + ang
        else:
            ang = -ang
        if abs(ang) < 0.12 or abs(ang) > 18:
            return im
        center = (w // 2, h // 2)
        m = cv2.getRotationMatrix2D(center, ang, 1.0)
        rot = cv2.warpAffine(arr, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        return Image.fromarray(rot)
    except Exception:
        return im


def _ocr_resume_pil(im) -> str:
    """Shared Tesseract pass for one page/image (RGB/L). Returns '' if deps missing or OCR fails."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError as e:
        raise ValueError(
            "OCR requires pytesseract and Pillow in this environment. Run: pip install pytesseract"
        ) from e

    _require_tesseract_binary()

    _EMAILISH = re.compile(r"[A-Za-z0-9._%+-]{2,}@[A-Za-z0-9.-]{2,}\.[A-Za-z]{2,}")
    _PSMS_FAST = (r"--psm 6 --oem 3", r"--psm 3 --oem 3")
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
        if n >= 1100:
            return True
        return False

    try:
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

        im = _maybe_deskew_rgb_pil(im)

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

        for frame in _pil_variants_fast_for_resume_ocr(im):
            for cfg in _PSMS_FAST:
                _run_pass(frame, cfg)
                merged = "\n".join(blobs)
                if _merged_good(merged):
                    return merged[:42000]

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


def _extract_text_pdf_via_ocr(pdf_path: Path) -> str:
    """Rasterize PDF pages and OCR (scanned résumés). Requires Pillow, pytesseract, and Tesseract binary."""
    try:
        from PIL import Image
    except ImportError:
        return ""

    parts: list[str] = []
    doc = None
    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        return ""

    max_pages = 10
    try:
        zoom = float((os.environ.get("REZUME_PDF_OCR_ZOOM") or "2.5").strip())
    except ValueError:
        zoom = 2.5
    zoom = max(1.5, min(zoom, 4.0))
    mat = fitz.Matrix(zoom, zoom)

    try:
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            try:
                pix = page.get_pixmap(matrix=mat, alpha=False)
            except Exception:
                continue
            if pix.n == 1:
                im = Image.frombytes("L", (pix.width, pix.height), pix.samples)
                im = im.convert("RGB")
            elif pix.n == 3:
                im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            elif pix.n == 4:
                im = Image.frombytes("RGBA", (pix.width, pix.height), pix.samples).convert("RGB")
            else:
                continue
            chunk = _ocr_resume_pil(im)
            if chunk.strip():
                parts.append(chunk.strip())
    finally:
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass

    return "\n\n".join(parts)[:42000]


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
        from PIL import Image
    except ImportError:
        return ""

    try:
        im = Image.open(str(image_path))
        return _ocr_resume_pil(im)
    except ValueError:
        raise
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
