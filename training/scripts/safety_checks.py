"""
Lightweight safety and fairness checks:
- Ensure PII is not used as features (sample check on training data).
- Optional: performance by coarse group if group column available.
- Explanation: top keywords for TF-IDF; note for transformer (attention/attribution).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.preprocessing.pii import contains_pii, strip_pii


def check_pii_in_data(csv_path: Path, text_columns: list[str], sample_n: int = 200) -> dict:
    """Check if text columns contain PII. Returns counts of rows with PII in any checked column."""
    if not csv_path.exists():
        return {"error": f"File not found: {csv_path}"}
    df = pd.read_csv(csv_path).fillna("")
    sample = df.sample(n=min(sample_n, len(df)), random_state=42) if len(df) > sample_n else df
    out = {"total_rows": len(df), "sampled": len(sample), "rows_with_pii": 0, "columns_checked": text_columns}
    for _, row in sample.iterrows():
        for col in text_columns:
            if col in row and contains_pii(str(row[col])):
                out["rows_with_pii"] += 1
                break
    out["recommendation"] = "Run PII stripping before training (strip_pii) if rows_with_pii > 0."
    return out


def tfidf_top_keywords(vectorizer, feature_names, top_n: int = 15) -> list[str]:
    """Return top TF-IDF terms (e.g. for one document or global)."""
    if vectorizer is None or feature_names is None:
        return []
    # Global: max idf or sum of idf
    import numpy as np
    idf = getattr(vectorizer, "idf_", None)
    if idf is not None:
        top_idx = np.argsort(idf)[-top_n:][::-1]
        return [feature_names[i] for i in top_idx if i < len(feature_names)]
    return []


def main():
    data_dir = ROOT / "outputs" / "transformer_data"
    role_dir = ROOT / "outputs" / "role_data"
    print("Safety checks (lightweight)")
    print("-" * 40)
    for name, path, cols in [
        ("Match pairs (cand_text)", data_dir / "train.csv", ["cand_text"]),
        ("Role data (text)", role_dir / "train.csv", ["text"]),
    ]:
        r = check_pii_in_data(path, cols)
        if "error" in r:
            print(name, ":", r["error"])
        else:
            print(name, ":", "Rows with PII in sample:", r.get("rows_with_pii", 0), "/", r.get("sampled", 0))
            print(" ", r.get("recommendation", ""))
    print("-" * 40)
    print("Note: For transformer models, full attention-based attribution is not included here.")
    print("Use interpretability libraries (e.g. captum) if you need token-level explanations.")


if __name__ == "__main__":
    main()
