from __future__ import annotations
from pathlib import Path
import pandas as pd
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.parsing.role_inference import infer_title_from_skills

P = ROOT / "outputs" / "parsing" / "candidates_enriched.csv"

def main():
    df = pd.read_csv(P).fillna("")

    df["title"] = df["skills"].apply(infer_title_from_skills)

    df.to_csv(P, index=False)

    print("✅ Titles inferred from skills. Sample:")
    print(df[["candidate_id","title"]].head(10).to_string(index=False))

if __name__ == "__main__":
    main()
