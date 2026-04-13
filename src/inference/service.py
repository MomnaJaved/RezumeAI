"""
Inference service: classify_role(resume_text), match_score(resume_text, jd_text).
Optional TF-IDF baseline. PII is stripped before inference.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# Lazy-loaded singletons
_role_model = None
_role_tokenizer = None
_role_id2label: Optional[Dict[int, str]] = None
_role_device: Optional[torch.device] = None
_match_model = None
_match_tokenizer = None
_match_device: Optional[torch.device] = None
_tfidf_vectorizer = None
_tfidf_job_vectors = None
_tfidf_cand_vectors = None

# Project root (inference is in src/inference/)
ROOT = Path(__file__).resolve().parents[2]
ROLE_DIR = ROOT / "artifacts" / "role_classifier"
MATCH_DIR = ROOT / "artifacts" / "match_ranker"
MAX_LENGTH = 256
_ml_log = logging.getLogger("rezume.ml")


def _infer_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _role_forward(enc: dict[str, torch.Tensor]) -> torch.Tensor:
    """Single forward; autocast on CUDA only."""
    assert _role_model is not None
    dev = _role_device or torch.device("cpu")
    if dev.type == "cuda":
        with torch.autocast(device_type="cuda", dtype=torch.float16):
            return _role_model(**enc).logits.squeeze(0).float()
    return _role_model(**enc).logits.squeeze(0).float()


def _warmup_role_forward() -> None:
    if _role_model is None or _role_tokenizer is None or _role_device is None:
        return
    try:
        # Pad to MAX_LENGTH so attention runs at full budget (same as real uploads) without huge tokenize cost.
        enc = _role_tokenizer(
            "warmup",
            truncation=True,
            padding="max_length",
            max_length=MAX_LENGTH,
            return_tensors="pt",
        )
        enc = {k: v.to(_role_device) for k, v in enc.items()}
        with torch.inference_mode():
            _role_forward(enc)
        if _role_device.type == "cuda":
            torch.cuda.synchronize()
    except Exception:
        pass


def _strip_pii(text: str) -> str:
    try:
        from src.preprocessing.pii import strip_pii
        return strip_pii(text)
    except Exception:
        return text


def _load_role_model():
    global _role_model, _role_tokenizer, _role_id2label, _role_device
    if _role_model is not None:
        return
    if not (ROLE_DIR / "config.json").exists():
        return
    with open(ROLE_DIR / "label2id.json") as f:
        label2id = json.load(f)
    _role_id2label = {int(v): k for k, v in label2id.items()}

    _role_tokenizer = AutoTokenizer.from_pretrained(str(ROLE_DIR))
    _role_model = AutoModelForSequenceClassification.from_pretrained(str(ROLE_DIR))
    _role_model.eval()

    _role_device = _infer_device()
    if _role_device.type == "cpu":
        disable_q = os.environ.get("REZUME_ROLE_NO_DYNAMIC_QUANT", "").lower() in ("1", "true", "yes")
        if not disable_q:
            try:
                _role_model = torch.quantization.quantize_dynamic(
                    _role_model, {torch.nn.Linear}, dtype=torch.qint8, inplace=False
                )
            except Exception:
                pass
    else:
        try:
            _role_model = _role_model.to(_role_device)
        except Exception:
            _role_device = torch.device("cpu")

    if os.environ.get("REZUME_TORCH_COMPILE", "").lower() in ("1", "true", "yes") and _role_device.type == "cuda":
        try:
            _role_model = torch.compile(_role_model, mode="reduce-overhead")  # type: ignore[assignment]
        except Exception:
            pass

    _warmup_role_forward()


def _match_forward_logits(enc: dict[str, torch.Tensor]) -> torch.Tensor:
    """Batch logits [batch] from cross-encoder; autocast on CUDA only."""
    assert _match_model is not None
    dev = _match_device or torch.device("cpu")
    if dev.type == "cuda":
        with torch.autocast(device_type="cuda", dtype=torch.float16):
            logits = _match_model(**enc).logits
    else:
        logits = _match_model(**enc).logits
    return logits.reshape(-1).float()


def _warmup_match_forward() -> None:
    if _match_model is None or _match_tokenizer is None or _match_device is None:
        return
    try:
        enc = _match_tokenizer(
            ["warmup jd"],
            ["warmup resume"],
            truncation=True,
            padding="max_length",
            max_length=MAX_LENGTH,
            return_tensors="pt",
        )
        enc = {k: v.to(_match_device) for k, v in enc.items()}
        with torch.inference_mode():
            _match_forward_logits(enc)
        if _match_device.type == "cuda":
            torch.cuda.synchronize()
    except Exception:
        pass


def warmup_role_classifier() -> bool:
    """
    Load role weights into memory and run a tiny forward pass. Call at API startup so the first
    POST /uploads/resume is not stuck on disk I/O + model init + kernel warmup.
    Returns True if artifacts were found and load was attempted.
    """
    if not (ROLE_DIR / "config.json").exists():
        return False
    _load_role_model()
    return True


def warmup_match_ranker() -> bool:
    """Preload cross-encoder (and one forward) so rank endpoints skip cold start."""
    if not (MATCH_DIR / "config.json").exists():
        return False
    _load_match_model()
    return True


def _load_match_model():
    global _match_model, _match_tokenizer, _match_device
    if _match_model is not None:
        return
    if not (MATCH_DIR / "config.json").exists():
        return
    _match_tokenizer = AutoTokenizer.from_pretrained(str(MATCH_DIR))
    _match_model = AutoModelForSequenceClassification.from_pretrained(str(MATCH_DIR))
    _match_model.eval()

    _match_device = _infer_device()
    if _match_device.type == "cpu":
        disable_q = os.environ.get("REZUME_MATCH_NO_DYNAMIC_QUANT", "").lower() in ("1", "true", "yes")
        if not disable_q:
            try:
                _match_model = torch.quantization.quantize_dynamic(
                    _match_model, {torch.nn.Linear}, dtype=torch.qint8, inplace=False
                )
            except Exception:
                pass
    else:
        try:
            _match_model = _match_model.to(_match_device)
        except Exception:
            _match_device = torch.device("cpu")

    if os.environ.get("REZUME_TORCH_COMPILE", "").lower() in ("1", "true", "yes") and _match_device.type == "cuda":
        try:
            _match_model = torch.compile(_match_model, mode="reduce-overhead")  # type: ignore[assignment]
        except Exception:
            pass

    _warmup_match_forward()


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
    if _role_model is None or _role_tokenizer is None:
        return {"label": "fullstack", "probs": {"frontend": 0.33, "backend": 0.33, "fullstack": 0.34}}
    text = _strip_pii(resume_text) if strip_pii_input else resume_text
    enc = _role_tokenizer(
        text,
        truncation=True,
        padding=True,
        max_length=MAX_LENGTH,
        return_tensors="pt",
    )
    dev = _role_device or torch.device("cpu")
    enc = {k: v.to(dev) for k, v in enc.items()}
    with torch.inference_mode():
        logits_t = _role_forward(enc)
    logits = logits_t.detach().cpu().numpy()
    max_log = float(np.max(logits))
    e = np.exp(logits - max_log)
    probs = (e / e.sum()).tolist()
    id2label = _role_id2label
    if not id2label:
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
    scores = match_scores_batch(
        jd_text,
        [resume_text],
        strip_pii_input=strip_pii_input,
        batch_size=1,
    )
    return scores[0] if scores else 0.5


def match_scores_batch(
    jd_text: str,
    resume_texts: List[str],
    strip_pii_input: bool = True,
    batch_size: Optional[int] = None,
) -> List[float]:
    """
    Score many (jd, resume) pairs with one cross-encoder; batches forwards for GPU/CPU throughput.
    Order matches ``resume_texts``. Empty input → empty list.
    """
    if not resume_texts:
        return []
    _load_match_model()
    if _match_model is None or _match_tokenizer is None:
        return [0.5] * len(resume_texts)

    bs = batch_size
    if bs is None:
        try:
            bs = int(os.environ.get("REZUME_MATCH_BATCH_SIZE", "32"))
        except ValueError:
            bs = 32
    bs = max(1, min(bs, 128))

    texts = [_strip_pii(t) if strip_pii_input else t for t in resume_texts]
    dev = _match_device or torch.device("cpu")
    out: List[float] = []
    for i in range(0, len(texts), bs):
        chunk = texts[i : i + bs]
        enc = _match_tokenizer(
            [jd_text] * len(chunk),
            chunk,
            truncation=True,
            padding=True,
            max_length=MAX_LENGTH,
            return_tensors="pt",
        )
        enc = {k: v.to(dev) for k, v in enc.items()}
        with torch.inference_mode():
            logits = _match_forward_logits(enc)
        logits_cpu = logits.detach().cpu()
        for j in range(logits_cpu.shape[0]):
            out.append(float(max(0.0, min(1.0, logits_cpu[j].item()))))
    _ml_log.info(
        "match_scores_batch total_pairs=%s batch_size=%s device=%s",
        len(resume_texts),
        bs,
        dev,
    )
    return out


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
