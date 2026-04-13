"""
Evaluate match/ranking: Spearman with weak_score, NDCG@10, Recall@10.
Simulates "one JD vs many resumes" per job on test set.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from scipy.stats import spearmanr
from transformers import AutoModelForSequenceClassification, AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TEST_CSV = ROOT / "outputs" / "transformer_data" / "test.csv"
MODEL_DIR = ROOT / "artifacts" / "match_ranker"
MAX_LENGTH = 256
BATCH_SIZE = 16


def ndcg_at_k(relevances: list[float], k: int = 10) -> float:
    """NDCG@k; relevances = list of relevance scores in ranked order."""
    relevances = np.asarray(relevances[:k])
    if relevances.size == 0:
        return 0.0
    dcg = np.sum(relevances / np.log2(np.arange(2, len(relevances) + 2)))
    ideal = np.sort(relevances)[::-1][:k]
    idcg = np.sum(ideal / np.log2(np.arange(2, len(ideal) + 2)))
    if idcg <= 0:
        return 0.0
    return float(dcg / idcg)


def recall_at_k(relevances: list[float], k: int = 10, threshold: float = 0.5) -> float:
    """Recall@k: fraction of relevant (>= threshold) in top-k."""
    relevances = np.asarray(relevances[:k])
    return float(np.sum(relevances >= threshold) / max(1, np.sum(np.asarray(relevances) >= threshold)))


def main():
    if not TEST_CSV.exists():
        raise SystemExit(f"Missing: {TEST_CSV}")
    if not MODEL_DIR.exists() or not (MODEL_DIR / "config.json").exists():
        raise SystemExit(f"Missing model: {MODEL_DIR} (run train_match_ranker.py first)")

    df = pd.read_csv(TEST_CSV).fillna("")
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR))
    model = AutoModelForSequenceClassification.from_pretrained(str(MODEL_DIR))
    model.eval()

    # Per-job: get all candidates and their weak_scores; rank by model score
    jobs = df["job_id"].unique()
    spearman_list = []
    ndcg10_list = []
    recall10_list = []

    for job_id in jobs:
        sub = df[df["job_id"] == job_id].copy()
        job_text = sub["job_text"].iloc[0]
        cand_texts = sub["cand_text"].tolist()
        weak_scores = sub["weak_score"].astype(float).tolist()

        # Model scores in batches
        scores = []
        with torch.no_grad():
            for i in range(0, len(cand_texts), BATCH_SIZE):
                batch = cand_texts[i : i + BATCH_SIZE]
                enc = tokenizer(
                    [job_text] * len(batch),
                    batch,
                    truncation=True,
                    padding=True,
                    max_length=MAX_LENGTH,
                    return_tensors="pt",
                )
                out = model(**enc)
                s = out.logits.squeeze(-1).cpu().numpy()
                scores.extend(s.tolist() if s.ndim else [float(s)])

        # Rank by model score (descending)
        order = np.argsort(scores)[::-1]
        ranked_weak = [weak_scores[i] for i in order]
        spearman_list.append(spearmanr(scores, weak_scores)[0])
        ndcg10_list.append(ndcg_at_k(ranked_weak, 10))
        # Recall@10: fraction of relevant (weak_score >= 0.5) that appear in top-10
        n_relevant = sum(1 for w in weak_scores if w >= 0.5)
        if n_relevant > 0:
            recall10_list.append(min(1.0, sum(1 for w in ranked_weak[:10] if w >= 0.5) / n_relevant))
        else:
            recall10_list.append(0.0)

    spearman_list = [x for x in spearman_list if not np.isnan(x)]
    print("Match / ranking evaluation (test set, by job):")
    print("  Spearman(r) with weak_score:", np.mean(spearman_list) if spearman_list else "N/A")
    print("  NDCG@10 (mean):", np.mean(ndcg10_list))
    print("  Recall@10 (mean):", np.mean(recall10_list))


if __name__ == "__main__":
    main()
