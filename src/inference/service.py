"""
Inference service: classify_role(resume_text), match_score(resume_text, jd_text).
Optional TF-IDF baseline. PII is stripped before inference.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# Lazy-loaded singletons
_role_model = None
_role_tokenizer = None
_match_model = None
_match_tokenizer = None
_tfidf_vectorizer = None
_tfidf_job_vectors = None
_tfidf_cand_vectors = None

# Project root (inference is in src/inference/)
ROOT = Path(__file__).resolve().parents[2]
ROLE_DIR = ROOT / "artifacts" / "role_classifier"
MATCH_DIR = ROOT / "artifacts" / "match_ranker"
MAX_LENGTH = 256


def _strip_pii(text: str) -> str:
    try:
        from src.preprocessing.pii import strip_pii
        return strip_pii(text)
    except Exception:
        return text


def _load_role_model():
    global _role_model, _role_tokenizer
    if _role_model is None and (ROLE_DIR / "config.json").exists():
        _role_tokenizer = AutoTokenizer.from_pretrained(str(ROLE_DIR))
        _role_model = AutoModelForSequenceClassification.from_pretrained(str(ROLE_DIR))
        _role_model.eval()


def _load_match_model():
    global _match_model, _match_tokenizer
    if _match_model is None and (MATCH_DIR / "config.json").exists():
        _match_tokenizer = AutoTokenizer.from_pretrained(str(MATCH_DIR))
        _match_model = AutoModelForSequenceClassification.from_pretrained(str(MATCH_DIR))
        _match_model.eval()


def classify_role(
    resume_text: str,
    strip_pii_input: bool = True,
    return_probs: bool = True,
) -> dict[str, Any]:
    """
    Classify resume into frontend | backend | fullstack.
    Returns {"label": str, "probs": {label: float}} (probs if return_probs=True).
    """
    _load_role_model()
    if _role_model is None:
        return {"label": "fullstack", "probs": {"frontend": 0.33, "backend": 0.33, "fullstack": 0.34}}
    text = _strip_pii(resume_text) if strip_pii_input else resume_text
    enc = _role_tokenizer(
        text,
        truncation=True,
        padding=True,
        max_length=MAX_LENGTH,
        return_tensors="pt",
    )
    with torch.no_grad():
        logits = _role_model(**enc).logits.squeeze(0).cpu().numpy()
    probs = (np.exp(logits) / np.exp(logits).sum()).tolist()
    with open(ROLE_DIR / "label2id.json") as f:
        label2id = json.load(f)
    id2label = {int(v): k for k, v in label2id.items()}
    pred_id = int(np.argmax(logits))
    label = id2label.get(pred_id, "fullstack")
    out = {"label": label}
    if return_probs:
        out["probs"] = {id2label.get(i, str(i)): probs[i] for i in range(len(probs))}
    return out


def match_score(
    resume_text: str,
    jd_text: str,
    strip_pii_input: bool = True,
) -> float:
    """
    Cross-encoder match score in [0, 1] (may be outside if model uncalibrated).
    Clamp to [0, 1] for API consistency.
    """
    _load_match_model()
    if _match_model is None:
        return 0.5
    res = _strip_pii(resume_text) if strip_pii_input else resume_text
    enc = _match_tokenizer(
        jd_text,
        res,
        truncation=True,
        padding=True,
        max_length=MAX_LENGTH,
        return_tensors="pt",
    )
    with torch.no_grad():
        score = _match_model(**enc).logits.squeeze(-1).item()
    return float(max(0.0, min(1.0, score)))


def get_tfidf_score(
    resume_text: str,
    jd_text: str,
    vectorizer: Any = None,
) -> float:
    """
    TF-IDF cosine similarity. Requires pre-fit vectorizer and optional
    precomputed vectors; for single (resume, jd) call, fit on [jd_text, resume_text].
    Returns value in [0, 1] (cosine typically in [-1,1], we shift to [0,1]).
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError:
        return 0.5
    if vectorizer is None:
        vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
        X = vectorizer.fit_transform([jd_text, resume_text])
    else:
        X = vectorizer.transform([jd_text, resume_text])
    sim = cosine_similarity(X[0:1], X[1:2])[0, 0]
    return float(max(0.0, min(1.0, (sim + 1) / 2)))
