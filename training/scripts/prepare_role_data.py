
"""
Prepare role classification data: one row per candidate with text + role_label.
Uses same candidate_id split as build_pairs_and_splits (no leakage).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.parsing.role_labels import title_to_role_label, ROLE_LABELS
from src.preprocessing.pii import strip_pii

CANDS_PATH = ROOT / "outputs" / "parsing" / "candidates_enriched.csv"
OUT_DIR = ROOT / "outputs" / "role_data"
TRAIN_FRAC = 0.8
VAL_FRAC = 0.1
SEED = 42


def build_text(row: pd.Series, strip_pii_text: bool = True) -> str:
    raw = " ".join([
        str(row.get("title", "")),
        str(row.get("skills", "")),
        str(row.get("raw_text", "")),
    ]).strip()
    if strip_pii_text:
        raw = strip_pii(raw)
    return raw


def main(seed: int = SEED, strip_pii_for_training: bool = True):
    if not CANDS_PATH.exists():
        raise SystemExit(f"Missing: {CANDS_PATH}")

    df = pd.read_csv(CANDS_PATH).fillna("")
    df["text"] = df.apply(
        lambda r: build_text(r, strip_pii_text=strip_pii_for_training), axis=1
    )
    df["role_label"] = df["title"].astype(str).map(title_to_role_label)

    # Drop if role_label not in ROLE_LABELS (shouldn't happen with default mapping)
    df = df[df["role_label"].isin(ROLE_LABELS)].reset_index(drop=True)

    # Split by candidate_id (same logic as build_pairs_and_splits)
    candidate_ids = df["candidate_id"].astype(str).unique().tolist()
    n = len(candidate_ids)
    n_train = int(n * TRAIN_FRAC)
    n_val = int(n * VAL_FRAC)
    rng = np.random.default_rng(seed)
    shuffled = rng.permutation(candidate_ids)
    train_ids = set(shuffled[:n_train])
    val_ids = set(shuffled[n_train : n_train + n_val])
    test_ids = set(shuffled[n_train + n_val :])

    def split(cid: str) -> str:
        if cid in train_ids:
            return "train"
        if cid in val_ids:
            return "val"
        return "test"

    df["split"] = df["candidate_id"].astype(str).map(split)
    # One row per candidate
    out = df[["candidate_id", "text", "role_label", "split"]].drop_duplicates(
        subset=["candidate_id"], keep="first"
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out[out["split"] == "train"][["candidate_id", "text", "role_label"]].to_csv(
        OUT_DIR / "train.csv", index=False
    )
    out[out["split"] == "val"][["candidate_id", "text", "role_label"]].to_csv(
        OUT_DIR / "val.csv", index=False
    )
    out[out["split"] == "test"][["candidate_id", "text", "role_label"]].to_csv(
        OUT_DIR / "test.csv", index=False
    )
    print("Role data (split by candidate_id):")
    print("  train:", (out["split"] == "train").sum())
    print("  val:  ", (out["split"] == "val").sum())
    print("  test: ", (out["split"] == "test").sum())
    print("Written:", OUT_DIR / "train.csv", "val.csv", "test.csv")


if __name__ == "__main__":
    main()
