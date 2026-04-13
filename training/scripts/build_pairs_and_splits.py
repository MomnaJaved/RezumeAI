"""
Build (resume, JD, weak_score) pairs and train/val/test splits WITHOUT leakage.
Splits by candidate_id so each resume appears in exactly one split.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.matching.weak_score import (
    parse_skill_str,
    weak_score,
    exp_score,
    edu_score,
)
from src.preprocessing.pii import strip_pii

JOBS_PATH = ROOT / "data" / "processed" / "jobs_enriched.csv"
CANDS_PATH = ROOT / "outputs" / "parsing" / "candidates_enriched.csv"
OUT_PAIRS_DIR = ROOT / "outputs" / "pairs"
OUT_DATA_DIR = ROOT / "outputs" / "transformer_data"


def build_job_text(row: pd.Series) -> str:
    return " ".join([
        str(row.get("job_title", "")),
        str(row.get("job_description_raw", "")),
        str(row.get("job_skills", "")),
    ]).strip()


def build_cand_text(row: pd.Series, strip_pii_text: bool = True) -> str:
    raw = " ".join([
        str(row.get("title", "")),
        str(row.get("skills", "")),
        str(row.get("raw_text", "")),
    ]).strip()
    if strip_pii_text:
        raw = strip_pii(raw)
    return raw


def main(
    train_frac: float = 0.8,
    val_frac: float = 0.1,
    seed: int = 42,
    sample_pairs_per_job: int | None = None,
    strip_pii_for_training: bool = True,
):
    if not JOBS_PATH.exists():
        raise SystemExit(f"Missing: {JOBS_PATH}")
    if not CANDS_PATH.exists():
        raise SystemExit(f"Missing: {CANDS_PATH} (run parsing + enrichment first)")

    jobs = pd.read_csv(JOBS_PATH).fillna("")
    cands = pd.read_csv(CANDS_PATH).fillna("")

    # Unique candidate IDs → split (no leakage: same candidate never in two splits)
    candidate_ids = cands["candidate_id"].astype(str).unique().tolist()
    n = len(candidate_ids)
    n_train = int(n * train_frac)
    n_val = int(n * val_frac)
    rng = np.random.default_rng(seed)
    shuffled = rng.permutation(candidate_ids)
    train_ids = set(shuffled[:n_train])
    val_ids = set(shuffled[n_train : n_train + n_val])
    test_ids = set(shuffled[n_train + n_val :])

    # Precompute candidate lookups
    cand_skill_sets = [parse_skill_str(s) for s in cands["skills"].astype(str)]
    cand_years = cands.get("years_experience_est", pd.Series([None] * len(cands))).fillna(0)
    cand_deg = cands.get("highest_degree", pd.Series([""] * len(cands))).astype(str)

    jobs["job_text"] = jobs.apply(build_job_text, axis=1)
    cands["cand_text"] = cands.apply(
        lambda r: build_cand_text(r, strip_pii_text=strip_pii_for_training), axis=1
    )

    OUT_PAIRS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DATA_DIR.mkdir(parents=True, exist_ok=True)

    train_rows, val_rows, test_rows = [], [], []

    for j_idx, job in tqdm(jobs.iterrows(), total=len(jobs), desc="Pairs"):
        job_id = str(job.get("job_id", ""))
        job_text = job["job_text"]
        job_skills = parse_skill_str(str(job.get("job_skills", "")))
        job_min_exp = job.get("min_experience")
        job_edu = str(job.get("education_required", "any"))

        for c_idx in range(len(cands)):
            cid = str(cands.iloc[c_idx]["candidate_id"])
            split = "train" if cid in train_ids else "val" if cid in val_ids else "test"
            exp_s = exp_score(cand_years.iloc[c_idx], job_min_exp)
            edu_s = edu_score(cand_deg.iloc[c_idx], job_edu)
            score = weak_score(job_skills, cand_skill_sets[c_idx], exp_s, edu_s)
            row = {
                "job_id": job_id,
                "candidate_id": cid,
                "job_text": job_text,
                "cand_text": cands.iloc[c_idx]["cand_text"],
                "weak_score": round(score, 4),
            }
            if split == "train":
                train_rows.append(row)
            elif split == "val":
                val_rows.append(row)
            else:
                test_rows.append(row)

    # Optional: subsample train/val by job for faster training
    if sample_pairs_per_job is not None and sample_pairs_per_job > 0:
        train_df = pd.DataFrame(train_rows)
        val_df = pd.DataFrame(val_rows)
        if len(train_df) > sample_pairs_per_job * len(jobs):
            train_df = (
                train_df.groupby("job_id", group_keys=False)
                .apply(
                    lambda x: x.sample(n=min(sample_pairs_per_job, len(x)), random_state=seed)
                )
                .reset_index(drop=True)
            )
            train_rows = train_df.to_dict("records")
        if len(val_df) > sample_pairs_per_job * len(jobs):
            val_df = (
                val_df.groupby("job_id", group_keys=False)
                .apply(
                    lambda x: x.sample(n=min(sample_pairs_per_job, len(x)), random_state=seed)
                )
                .reset_index(drop=True)
            )
            val_rows = val_df.to_dict("records")

    pd.DataFrame(train_rows).to_csv(OUT_DATA_DIR / "train.csv", index=False)
    pd.DataFrame(val_rows).to_csv(OUT_DATA_DIR / "val.csv", index=False)
    pd.DataFrame(test_rows).to_csv(OUT_DATA_DIR / "test.csv", index=False)

    print("Splits by candidate_id (no leakage):")
    print("  train:", len(train_rows), "pairs")
    print("  val:  ", len(val_rows), "pairs")
    print("  test: ", len(test_rows), "pairs")
    print("Written:", OUT_DATA_DIR / "train.csv", "val.csv", "test.csv")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=float, default=0.8)
    ap.add_argument("--val", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--sample-per-job", type=int, default=None, help="Subsample pairs per job (train/val)")
    ap.add_argument("--no-strip-pii", action="store_true", help="Disable PII stripping (not recommended)")
    args = ap.parse_args()
    main(
        train_frac=args.train,
        val_frac=args.val,
        seed=args.seed,
        sample_pairs_per_job=args.sample_per_job,
        strip_pii_for_training=not args.no_strip_pii,
    )
