from __future__ import annotations

from pathlib import Path
from typing import Optional

import pdfplumber
import fitz  # pymupdf
import docx


def extract_text_pdf(pdf_path: Path) -> str:
    """
    Try pdfplumber first (good for most text PDFs).
    If it yields too little text, fall back to PyMuPDF (fitz).
    """
    text = ""
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            parts = []
            for page in pdf.pages:
                t = page.extract_text() or ""
                if t:
                    parts.append(t)
            text = "\n".join(parts).strip()
    except Exception:
        text = ""

    # fallback if empty/very small (likely scanned or extraction failed)
    if len(text) < 200:
        try:
            doc = fitz.open(str(pdf_path))
            parts = []
            for page in doc:
                parts.append(page.get_text("text"))
            doc.close()
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


def extract_text_any(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return extract_text_pdf(path)
    if ext == ".docx":
        return extract_text_docx(path)
    if ext == ".txt":
        return extract_text_txt(path)
    return ""
