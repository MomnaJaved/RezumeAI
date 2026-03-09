from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer


@dataclass
class SbertConfig:
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    batch_size: int = 64


def get_device() -> str:
    """
    Choose device; keep simple and robust for this project.
    Prefers CUDA, then MPS (Apple), else CPU.
    """
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_sbert(config: SbertConfig | None = None) -> SentenceTransformer:
    cfg = config or SbertConfig()
    device = get_device()
    model = SentenceTransformer(cfg.model_name, device=device)
    return model


def encode_texts(
    model: SentenceTransformer,
    texts: List[str],
    batch_size: int = 64,
) -> np.ndarray:
    """
    Encode a list of texts into a numpy array of embeddings.
    Embeddings are L2-normalized so cosine similarity == dot product.
    """
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        convert_to_numpy=True,
        show_progress_bar=True,
        normalize_embeddings=True,
    )
    return embeddings

