from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pathlib import Path
import pandas as pd
from tqdm import tqdm

from src.parsing.skill_mining import build_global_vocab, skills_for_resume

ROOT = Path(__file__).resolve().parents[1]
CAND_PATH = ROOT / "outputs" / "parsing" / "candidates.csv"
OUT_DIR = ROOT / "outputs" / "parsing"
OUT_DIR.mkdir(parents=True, exist_ok=True)

def main():
    df = pd.read_csv(CAND_PATH)
    if "raw_text" not in df.columns:
        raise SystemExit("candidates.csv must contain raw_text column.")

    texts = df["raw_text"].fillna("").astype(str).tolist()

    print("Building improved skills vocabulary from existing raw_text...")
    vocab_counter = build_global_vocab(texts, min_freq=12, top_k=4000)
    vocab = set(vocab_counter.keys())

    print(f"New vocab size: {len(vocab)}")
    print("Assigning improved skills per resume...")
    df["skills_list"] = [skills_for_resume(t, vocab) for t in tqdm(texts)]
    df["skills"] = df["skills_list"].apply(lambda xs: ", ".join(xs))

    # overwrite candidates.csv (skills updated)
    df_out = df.drop(columns=["skills_list"], errors="ignore")
    df_out.to_csv(OUT_DIR / "candidates.csv", index=False)

    # overwrite skills_vocab.csv
    vocab_df = pd.DataFrame([{"skill": k, "doc_freq": v} for k, v in vocab_counter.most_common()])
    vocab_df.to_csv(OUT_DIR / "skills_vocab.csv", index=False)

    print("✅ Updated:")
    print(f" - {OUT_DIR / 'candidates.csv'} (skills refreshed)")
    print(f" - {OUT_DIR / 'skills_vocab.csv'} (vocab refreshed)")
    print("Top 25 skills:", ", ".join(vocab_df.head(25)['skill'].tolist()))

if __name__ == "__main__":
    main()
