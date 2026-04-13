"""Ranking metrics: NDCG@K, MAP, Precision@K, Recall@K (weak-label or binary relevance)."""
from __future__ import annotations

import math
from typing import Iterable, Sequence


def _dcg(relevances: Sequence[float]) -> float:
    return sum(rel / math.log2(i + 2) for i, rel in enumerate(relevances))


def ndcg_at_k(ranked_relevances: Sequence[float], k: int) -> float:
    """ranked_relevances: relevance in model rank order (best rank first)."""
    rel = list(ranked_relevances[:k])
    if not rel:
        return 0.0
    dcg = _dcg(rel)
    ideal = sorted(rel, reverse=True)
    idcg = _dcg(ideal)
    return float(dcg / idcg) if idcg > 0 else 0.0


def precision_at_k(relevant_mask: Sequence[bool], k: int) -> float:
    """relevant_mask in ranked order."""
    top = relevant_mask[:k]
    if not top:
        return 0.0
    return float(sum(1 for x in top if x) / min(k, len(top)))


def recall_at_k(relevant_mask: Sequence[bool], k: int, total_relevant: int) -> float:
    if total_relevant <= 0:
        return 0.0
    found = sum(1 for i, x in enumerate(relevant_mask[:k]) if x)
    return float(found / total_relevant)


def average_precision(ranked_relevant: Sequence[bool]) -> float:
    """AP for one query; ranked_relevant[i] True if item at rank i+1 is relevant."""
    rel_count = sum(1 for x in ranked_relevant if x)
    if rel_count == 0:
        return 0.0
    precisions = []
    hits = 0
    for i, is_rel in enumerate(ranked_relevant):
        if is_rel:
            hits += 1
            precisions.append(hits / (i + 1))
    return float(sum(precisions) / rel_count) if precisions else 0.0


def mean_average_precision(
    queries_ranked_masks: Iterable[Sequence[bool]],
) -> float:
    aps = [average_precision(list(m)) for m in queries_ranked_masks]
    return float(sum(aps) / len(aps)) if aps else 0.0
