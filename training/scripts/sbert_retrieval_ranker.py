from __future__ import annotations

"""
SBERT retrieval ranker:
  - Loads precomputed SBERT embeddings for jobs and candidates.
  - Computes cosine similarity (dot product of normalized embeddings).
  - Outputs top-K candidates per job_id to outputs/rankings/sbert_rankings.csv.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

EMB_DIR = ROOT / "outputs" / "sbert_embeddings"
OUT_DIR = ROOT / "outputs" / "rankings"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / "sbert_rankings.csv"


def main(top_k: int = 100) -> None:
    jobs_emb_path = EMB_DIR / "jobs.npy"
    jobs_ids_path = EMB_DIR / "jobs_ids.npy"
    cands_emb_path = EMB_DIR / "candidates.npy"
    cands_ids_path = EMB_DIR / "candidates_ids.npy"

    if not all(p.exists() for p in [jobs_emb_path, jobs_ids_path, cands_emb_path, cands_ids_path]):
        raise SystemExit(
            "Missing SBERT embeddings. Run scripts/compute_sbert_embeddings.py first."
        )

    job_embs = np.load(jobs_emb_path)
    job_ids = np.load(jobs_ids_path, allow_pickle=True).astype(str)
    cand_embs = np.load(cands_emb_path)
    cand_ids = np.load(cands_ids_path, allow_pickle=True).astype(str)

    # Embeddings are already L2-normalized in encode_texts, so cosine == dot product
    out_rows = []
    n_jobs = job_embs.shape[0]
    n_cands = cand_embs.shape[0]
    print(f"Jobs: {n_jobs} | Candidates: {n_cands} | top_k: {top_k}")

    # For each job: compute similarity with all candidates and take top_k
    for j_idx in range(n_jobs):
        j_vec = job_embs[j_idx : j_idx + 1]  # shape (1, d)
        sims = np.dot(j_vec, cand_embs.T).reshape(-1)  # (n_candidates,)
        # Get top_k indices
        k = min(top_k, len(sims))
        top_idx = np.argpartition(-sims, k - 1)[:k]
        # Sort those by descending similarity
        top_idx = top_idx[np.argsort(-sims[top_idx])]

        job_id = job_ids[j_idx]
        for rank, c_idx in enumerate(top_idx, start=1):
            out_rows.append(
                {
                    "job_id": job_id,
                    "candidate_id": cand_ids[c_idx],
                    "cosine_similarity": float(sims[c_idx]),
                    "rank": rank,
                }
            )
        if (j_idx + 1) % 10 == 0 or j_idx == n_jobs - 1:
            print(f"Ranked {j_idx+1}/{n_jobs} jobs")

    out_df = pd.DataFrame(out_rows)
    out_df.to_csv(OUT_PATH, index=False)
    print("✅ Written SBERT rankings to:", OUT_PATH)


if __name__ == "__main__":
    main()

