from __future__ import annotations

import sys
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

JOBS_PATH = ROOT / "data" / "processed" / "jobs_enriched.csv"
CANDS_PATH = ROOT / "outputs" / "parsing" / "candidates_enriched.csv"
OUT_DIR = ROOT / "outputs" / "rankings"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / "tfidf_rankings.csv"

# -----------------------------
# Text building (simple + effective)
# -----------------------------
RE_MULTI_SPACE = re.compile(r"\s+")

def norm(s: str) -> str:
    s = "" if not isinstance(s, str) else s
    s = s.lower()
    s = RE_MULTI_SPACE.sub(" ", s).strip()
    return s

def build_job_text(row: pd.Series) -> str:
    # combine title + description + skills (skills are very strong signal)
    return " ".join([
        norm(row.get("job_title", "")),
        norm(row.get("job_description_raw", "")),
        norm(row.get("job_skills", "")),
    ]).strip()

def build_cand_text(row: pd.Series) -> str:
    # combine title + skills + (optionally) raw resume text
    # raw_text is large; keeping it helps recall but increases compute.
    return " ".join([
        norm(row.get("title", "")),
        norm(row.get("skills", "")),
        norm(row.get("raw_text", "")),  # keep for stronger matching
    ]).strip()

def main():
    if not JOBS_PATH.exists():
        raise SystemExit(f"Missing {JOBS_PATH}")
    if not CANDS_PATH.exists():
        raise SystemExit(f"Missing {CANDS_PATH}")

    jobs = pd.read_csv(JOBS_PATH).fillna("")
    cands = pd.read_csv(CANDS_PATH).fillna("")

    # Prepare texts
    job_texts = jobs.apply(build_job_text, axis=1).tolist()
    cand_texts = cands.apply(build_cand_text, axis=1).tolist()

    print("Jobs:", len(jobs), "| Candidates:", len(cands))
    print("Vectorizing...")

    # TF-IDF on combined corpus so vocab is shared
    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.95,
    )
    X = vectorizer.fit_transform(job_texts + cand_texts)
    X_jobs = X[: len(jobs)]
    X_cands = X[len(jobs) :]

    print("Computing similarities and ranking...")

    out_rows = []
    top_k = 50  # store top 50 candidates per job (change if you want)

    # For each job: cosine similarity with all candidates
    for j_idx in range(len(jobs)):
        sims = linear_kernel(X_jobs[j_idx], X_cands).flatten()

        # Get top K indices
        top_idx = sims.argsort()[::-1][:top_k]

        job_id = str(jobs.iloc[j_idx].get("job_id", ""))
        job_title = str(jobs.iloc[j_idx].get("job_title", ""))
        job_dept = str(jobs.iloc[j_idx].get("department", ""))

        for rank, c_idx in enumerate(top_idx, start=1):
            out_rows.append({
                "job_id": job_id,
                "job_title": job_title,
                "job_department": job_dept,
                "rank": rank,
                "candidate_id": str(cands.iloc[c_idx].get("candidate_id", "")),
                "candidate_title": str(cands.iloc[c_idx].get("title", "")),
                "tfidf_score": float(sims[c_idx]),
            })

        print(f"✅ Ranked job {job_id} ({j_idx+1}/{len(jobs)})")

    out = pd.DataFrame(out_rows)
    out.to_csv(OUT_PATH, index=False)
    print("✅ Written:", OUT_PATH)
    print(out.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
