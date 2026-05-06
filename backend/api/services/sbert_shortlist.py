from __future__ import annotations

"""
SBERT-based semantic shortlist for ATS-style two-stage ranking.

We store candidate embeddings in DB (`candidates.embedding_sbert`) so ranking can:
1) compute job embedding once
2) cosine against many candidate vectors cheaply
3) cross-encoder rerank only top-K
"""

import logging
from functools import lru_cache
from typing import Iterable, Optional, Tuple

import numpy as np

_log = logging.getLogger("rezume.api.sbert")

# Default model `all-MiniLM-L6-v2` embedding size (used only for offline / failure fallback).
_SBERT_DIM_DEFAULT = 384


@lru_cache(maxsize=1)
def _load_model(model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
    from src.embeddings.sbert import SbertConfig, load_sbert  # lazy import

    cfg = SbertConfig(model_name=model_name, batch_size=64)
    return load_sbert(cfg)


def embed_text(text: str, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> np.ndarray:
    """
    Encode one text to a float32 vector. On Hugging Face / network / disk errors, returns a
    zero vector so API routes (e.g. match preview) still respond instead of HTTP 500.
    """
    from src.embeddings.sbert import encode_texts  # lazy import

    try:
        model = _load_model(model_name=model_name)
        emb = encode_texts(model, [text], batch_size=1)
        return emb[0].astype(np.float32, copy=False)
    except Exception as e:
        _log.warning(
            "embed_text failed (%s); using zero vector. "
            "Ensure Hugging Face is reachable once to cache the model, or work offline with HF_HOME populated.",
            e,
        )
        return np.zeros(_SBERT_DIM_DEFAULT, dtype=np.float32)


def bytes_to_vec(b: bytes) -> np.ndarray:
    # Stored as raw float32 bytes.
    return np.frombuffer(b, dtype=np.float32)


def cosine_topk(
    query_vec: np.ndarray,
    candidates: Iterable[Tuple[str, bytes]],
    k: int,
) -> list[Tuple[str, float]]:
    """
    candidates: iterable of (candidate_external_id, embedding_bytes)
    returns: top-k list of (candidate_external_id, cosine_similarity)
    """
    q = query_vec.astype(np.float32, copy=False)
    qn = float(np.linalg.norm(q) + 1e-12)

    ids: list[str] = []
    sims: list[float] = []
    for cid, b in candidates:
        v = bytes_to_vec(b)
        if v.size != q.size:
            # Skip mismatched dimension (e.g. changed model).
            continue
        denom = float((np.linalg.norm(v) + 1e-12) * qn)
        sims.append(float(np.dot(v, q) / denom))
        ids.append(cid)

    if not ids:
        return []

    k = max(1, min(int(k), len(ids)))
    idx = np.argpartition(np.asarray(sims), -k)[-k:]
    # Sort selected indices by sim desc
    idx = idx[np.argsort(np.asarray(sims)[idx])[::-1]]
    return [(ids[i], sims[i]) for i in idx]

