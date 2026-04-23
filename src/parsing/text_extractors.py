from __future__ import annotations

from pathlib import Path

import pdfplumber
import fitz  # pymupdf
import docx

from src.parsing.ocr_layer import extract_text_image, extract_text_pdf_via_ocr


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
        ocr = extract_text_pdf_via_ocr(pdf_path)
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
