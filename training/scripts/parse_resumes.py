from __future__ import annotations

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import hashlib
from typing import Dict, List

import pandas as pd
from tqdm import tqdm

from src.parsing.text_extractors import extract_text_any
from src.parsing.text_cleaning import preprocess_resume_text
from src.parsing.skill_mining import build_global_vocab, skills_for_resume

IN_DIR = ROOT / "data" / "raw" / "resumes_extracted"
OUT_DIR = ROOT / "outputs" / "parsing"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def file_id(path: Path) -> str:
    """
    Stable ID based on relative path + file size.
    """
    rel = str(path.relative_to(IN_DIR)).encode("utf-8", errors="ignore")
    size = str(path.stat().st_size).encode("utf-8")
    return hashlib.md5(rel + b"::" + size).hexdigest()[:12]


def main():
    files = []
    for ext in (".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"):
        files.extend(IN_DIR.rglob(f"*{ext}"))

    if not files:
        raise SystemExit(f"No resume files found in {IN_DIR}")

    print(f"Found {len(files)} resumes. Extracting text...")

    rows: List[Dict] = []
    texts: List[str] = []

    for p in tqdm(files):
        txt = extract_text_any(p)
        txt = preprocess_resume_text((txt or "").strip())
        texts.append(txt)

        rows.append({
            "candidate_id": file_id(p),
            "filename": str(p.relative_to(IN_DIR)),
            "file_ext": p.suffix.lower(),
            "text_len": len(txt),
            "raw_text": txt,
        })

    df = pd.DataFrame(rows)

    # Drop totally empty text (scanned images etc.)
    df = df[df["text_len"] >= 200].reset_index(drop=True)
    texts = df["raw_text"].tolist()

    print(f"After dropping low-text files: {len(df)} resumes remain.")

    print("Building global skills vocabulary (data-driven)...")
    vocab_counter = build_global_vocab(texts, min_freq=10, top_k=4000)
    vocab_set = set(vocab_counter.keys())

    print(f"Skills vocab size: {len(vocab_set)}")

    print("Assigning skills per resume...")
    df["skills_list"] = [skills_for_resume(t, vocab_set) for t in tqdm(texts)]
    df["skills"] = df["skills_list"].apply(lambda xs: ", ".join(xs))

    # save candidates
    candidates_path = OUT_DIR / "candidates.csv"
    df_out = df[["candidate_id", "filename", "file_ext", "text_len", "skills", "raw_text"]]
    df_out.to_csv(candidates_path, index=False)

    # save skills vocab
    skills_vocab_path = OUT_DIR / "skills_vocab.csv"
    vocab_df = pd.DataFrame(
        [{"skill": k, "doc_freq": v} for k, v in vocab_counter.most_common()]
    )
    vocab_df.to_csv(skills_vocab_path, index=False)

    print("✅ Outputs created:")
    print(f" - {candidates_path}")
    print(f" - {skills_vocab_path}")
    print("\nSample skills:")
    sample = vocab_df.head(25)["skill"].tolist()
    print(", ".join(sample))


if __name__ == "__main__":
    main()
