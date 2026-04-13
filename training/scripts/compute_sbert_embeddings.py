from __future__ import annotations

"""
Compute Sentence-BERT embeddings for jobs and candidates.
Outputs:
  - outputs/sbert_embeddings/jobs.npy
  - outputs/sbert_embeddings/jobs_ids.npy
  - outputs/sbert_embeddings/candidates.npy
  - outputs/sbert_embeddings/candidates_ids.npy
"""

import sys
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.embeddings.sbert import SbertConfig, load_sbert, encode_texts  # noqa: E402

JOBS_PATH = ROOT / "data" / "processed" / "jobs_enriched.csv"
CANDS_PATH = ROOT / "outputs" / "parsing" / "candidates_enriched.csv"
OUT_DIR = ROOT / "outputs" / "sbert_embeddings"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def build_job_text(row: pd.Series) -> str:
    return " ".join(
        [
            str(row.get("job_title", "")),
            str(row.get("job_description_raw", "")),
            str(row.get("job_skills", "")),
        ]
    ).strip()


def build_cand_text(row: pd.Series) -> str:
    return " ".join(
        [
            str(row.get("title", "")),
            str(row.get("skills", "")),
            str(row.get("raw_text", "")),
        ]
    ).strip()


def main(model_name: str = "sentence-transformers/all-MiniLM-L6-v2", batch_size: int = 64) -> None:
    if not JOBS_PATH.exists():
        raise SystemExit(f"Missing: {JOBS_PATH}")
    if not CANDS_PATH.exists():
        raise SystemExit(f"Missing: {CANDS_PATH}")

    jobs = pd.read_csv(JOBS_PATH).fillna("")
    cands = pd.read_csv(CANDS_PATH).fillna("")

    job_ids: List[str] = jobs["job_id"].astype(str).tolist()
    cand_ids: List[str] = cands["candidate_id"].astype(str).tolist()

    job_texts: List[str] = jobs.apply(build_job_text, axis=1).tolist()
    cand_texts: List[str] = cands.apply(build_cand_text, axis=1).tolist()

    print("Jobs:", len(job_ids), "| Candidates:", len(cand_ids))
    print("Loading SBERT model:", model_name)

    cfg = SbertConfig(model_name=model_name, batch_size=batch_size)
    model = load_sbert(cfg)

    print("Encoding job descriptions...")
    job_embs = encode_texts(model, job_texts, batch_size=batch_size)
    print("Encoding candidate resumes...")
    cand_embs = encode_texts(model, cand_texts, batch_size=batch_size)

    np.save(OUT_DIR / "jobs.npy", job_embs)
    np.save(OUT_DIR / "jobs_ids.npy", np.array(job_ids, dtype=object))
    np.save(OUT_DIR / "candidates.npy", cand_embs)
    np.save(OUT_DIR / "candidates_ids.npy", np.array(cand_ids, dtype=object))

    print("✅ SBERT embeddings saved to:", OUT_DIR)


if __name__ == "__main__":
    # Simple CLI: allow overriding model/batch size via env or quick edit
    main()

