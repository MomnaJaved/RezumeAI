from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MODEL_DIR = ROOT / "models" / "transformer" / "ranker_roberta"
JOBS_PATH = ROOT / "data" / "processed" / "jobs_enriched.csv"
CANDS_PATH = ROOT / "outputs" / "parsing" / "candidates_enriched.csv"
OUT_DIR = ROOT / "outputs" / "rankings"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def build_job_text(row: pd.Series) -> str:
    return " ".join([
        str(row.get("job_title", "")),
        str(row.get("job_description_raw", "")),
        str(row.get("job_skills", "")),
    ]).strip()

def build_cand_text(row: pd.Series) -> str:
    return " ".join([
        str(row.get("title", "")),
        str(row.get("skills", "")),
        str(row.get("raw_text", "")),
    ]).strip()


@torch.no_grad()
def score_pairs(model, tokenizer, job_text: str, cand_texts: list[str], batch_size: int = 16) -> np.ndarray:
    scores = []
    model.eval()

    for i in range(0, len(cand_texts), batch_size):
        batch = cand_texts[i:i+batch_size]
        enc = tokenizer(
            [job_text]*len(batch),
            batch,
            truncation=True,
            padding=True,
            max_length=256,
            return_tensors="pt"
        )
        out = model(**enc)
        # regression -> logits shape [B,1]
        s = out.logits.squeeze(-1).cpu().numpy()
        scores.append(s)

    return np.concatenate(scores, axis=0)


def main(job_id: str = "J004", top_k: int = 25):
    jobs = pd.read_csv(JOBS_PATH).fillna("")
    cands = pd.read_csv(CANDS_PATH).fillna("")

    m = jobs[jobs["job_id"].astype(str) == str(job_id)]
    if len(m) == 0:
        raise SystemExit(f"Job not found: {job_id}")

    job_row = m.iloc[0]
    job_text = build_job_text(job_row)

    cand_texts = [build_cand_text(r) for _, r in cands.iterrows()]

    tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR))
    model = AutoModelForSequenceClassification.from_pretrained(str(MODEL_DIR))

    print("Scoring candidates for job:", job_id, "-", job_row.get("job_title", ""))

    scores = score_pairs(model, tokenizer, job_text, cand_texts, batch_size=16)

    out = cands[["candidate_id", "filename", "title", "skills"]].copy()
    out["transformer_score"] = scores
    out = out.sort_values("transformer_score", ascending=False).reset_index(drop=True)
    out["rank"] = np.arange(1, len(out) + 1)

    out_path = OUT_DIR / f"transformer_rankings_{job_id}.csv"
    out.head(top_k).to_csv(out_path, index=False)

    print("✅ Written:", out_path)
    print(out.head(top_k)[["rank","candidate_id","title","transformer_score","skills"]].to_string(index=False))


if __name__ == "__main__":
    # change job_id here or pass later by editing
    main(job_id="J004", top_k=25)
