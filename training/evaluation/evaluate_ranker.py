#!/usr/bin/env python3
"""
Evaluate cross-encoder ranker: Spearman vs weak_score, NDCG@K, MAP, Precision@K, Recall@K.
Uses held-out pair file (outputs/transformer_data/test.csv) or --mock for synthetic pairs.

Writes:
  outputs/evaluation/ranker_metrics.json
  outputs/evaluation/ranker_metrics.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from scipy.stats import spearmanr
from transformers import AutoModelForSequenceClassification, AutoTokenizer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from training.evaluation.metrics_ranking import (  # noqa: E402
    mean_average_precision,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)

TEST_CSV = ROOT / "outputs" / "transformer_data" / "test.csv"
MOCK_CSV = Path(__file__).resolve().parent / "fixtures" / "mock_rank_pairs.csv"
MODEL_DIR = ROOT / "artifacts" / "match_ranker"
OUT_DIR = ROOT / "outputs" / "evaluation"
MAX_LENGTH = 256
BATCH_SIZE = 16
RELEVANCE_THRESHOLD = 0.5


def ensure_mock_fixtures() -> Path:
    MOCK_CSV.parent.mkdir(parents=True, exist_ok=True)
    if MOCK_CSV.exists():
        return MOCK_CSV
    rows = []
    rng = np.random.default_rng(42)
    for j in range(3):
        job_id = f"MOCK_J{j}"
        job_text = f"Software engineer role {j} requiring Python and SQL."
        for c in range(12):
            cand_text = f"Candidate {j}_{c}: " + (
                "Python, SQL, AWS backend experience."
                if c % 3 == 0
                else "Graphic design and marketing portfolio."
            )
            weak = rng.uniform(0.2, 0.95) if c % 3 else rng.uniform(0.55, 0.9)
            rows.append(
                {
                    "job_id": job_id,
                    "job_text": job_text,
                    "cand_text": cand_text,
                    "weak_score": weak,
                }
            )
    pd.DataFrame(rows).to_csv(MOCK_CSV, index=False)
    print("Wrote mock pairs to:", MOCK_CSV)
    return MOCK_CSV


def score_pairs(
    model: torch.nn.Module,
    tokenizer,
    job_text: str,
    cand_texts: list[str],
    device: torch.device,
) -> list[float]:
    scores: list[float] = []
    model.eval()
    with torch.inference_mode():
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
            enc = {k: v.to(device) for k, v in enc.items()}
            out = model(**enc)
            s = out.logits.reshape(-1).float().cpu().numpy()
            scores.extend(s.tolist())
    return scores


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate match ranker")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use synthetic mock pairs (no transformer_data/test.csv required)",
    )
    parser.add_argument("--k", type=int, default=10, help="K for NDCG/Precision/Recall")
    args = parser.parse_args()

    data_path = ensure_mock_fixtures() if args.mock or not TEST_CSV.exists() else TEST_CSV
    if not data_path.exists():
        data_path = ensure_mock_fixtures()

    if not MODEL_DIR.exists() or not (MODEL_DIR / "config.json").exists():
        print("ERROR: Missing cross-encoder at", MODEL_DIR, "(train_match_ranker.py first).")
        print("With --mock, model is still required for forward scores.")
        sys.exit(1)

    df = pd.read_csv(data_path).fillna("")
    required = {"job_id", "job_text", "cand_text", "weak_score"}
    if not required.issubset(df.columns):
        raise SystemExit(f"CSV must have columns {required}; got {df.columns.tolist()}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR))
    model = AutoModelForSequenceClassification.from_pretrained(str(MODEL_DIR))
    model.to(device)
    model.eval()

    jobs = df["job_id"].unique()
    spearman_list: list[float] = []
    ndcg_list: list[float] = []
    prec_list: list[float] = []
    rec_list: list[float] = []
    query_masks: list[list[bool]] = []

    k = max(1, args.k)

    for job_id in jobs:
        sub = df[df["job_id"] == job_id].copy()
        job_text = str(sub["job_text"].iloc[0])
        cand_texts = sub["cand_text"].astype(str).tolist()
        weak_scores = sub["weak_score"].astype(float).tolist()

        scores = score_pairs(model, tokenizer, job_text, cand_texts, device)
        order = np.argsort(scores)[::-1].tolist()
        ranked_weak = [weak_scores[i] for i in order]
        ranked_binary = [w >= RELEVANCE_THRESHOLD for w in ranked_weak]
        n_rel = sum(1 for w in weak_scores if w >= RELEVANCE_THRESHOLD)

        sp, _ = spearmanr(scores, weak_scores)
        if not np.isnan(sp):
            spearman_list.append(float(sp))

        ndcg_list.append(ndcg_at_k(ranked_weak, k))
        prec_list.append(precision_at_k(ranked_binary, k))
        rec_list.append(recall_at_k(ranked_binary, k, n_rel))
        query_masks.append(ranked_binary)

    map_score = mean_average_precision(query_masks)

    summary = {
        "data_source": str(data_path),
        "n_jobs": int(len(jobs)),
        "label_type": "weak_score_continuous_and_binary_ge_0.5",
        "k": k,
        "spearman_mean": float(np.mean(spearman_list)) if spearman_list else None,
        "ndcg_at_k_mean": float(np.mean(ndcg_list)) if ndcg_list else 0.0,
        "map_mean": map_score,
        "precision_at_k_mean": float(np.mean(prec_list)) if prec_list else 0.0,
        "recall_at_k_mean": float(np.mean(rec_list)) if rec_list else 0.0,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "ranker_metrics.json"
    csv_path = OUT_DIR / "ranker_metrics.csv"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary.keys()))
        w.writeheader()
        flat = {k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in summary.items()}
        w.writerow(flat)

    print("Match ranker evaluation")
    print("  Data:", data_path)
    print("  Spearman (mean vs weak_score):", summary["spearman_mean"])
    print(f"  NDCG@{k} (mean, graded weak):", summary["ndcg_at_k_mean"])
    print("  MAP (binary relevance weak>=0.5):", summary["map_mean"])
    print(f"  Precision@{k} (mean):", summary["precision_at_k_mean"])
    print(f"  Recall@{k} (mean):", summary["recall_at_k_mean"])
    print("  Wrote:", json_path, csv_path)


if __name__ == "__main__":
    main()
