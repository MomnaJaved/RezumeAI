from __future__ import annotations

from pathlib import Path
import pandas as pd
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[1]

PAIRS_PATH = ROOT / "outputs" / "pairs" / "job_candidate_pairs.csv"
JOBS_PATH = ROOT / "data" / "processed" / "jobs_enriched.csv"
CANDS_PATH = ROOT / "outputs" / "parsing" / "candidates_enriched.csv"

OUT_DIR = ROOT / "outputs" / "transformer_data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TRAIN_PATH = OUT_DIR / "train.csv"
VAL_PATH = OUT_DIR / "val.csv"
TEST_PATH = OUT_DIR / "test.csv"


def main(sample_per_job: int = 2000, random_state: int = 42):
    pairs = pd.read_csv(PAIRS_PATH)
    jobs = pd.read_csv(JOBS_PATH).fillna("")
    cands = pd.read_csv(CANDS_PATH).fillna("")

    # Merge job text
    jobs["job_text"] = (
        jobs["job_title"].astype(str) + " " +
        jobs["job_description_raw"].astype(str) + " " +
        jobs["job_skills"].astype(str)
    )

    # Merge candidate text
    cands["cand_text"] = (
        cands.get("title", "").astype(str) + " " +
        cands.get("skills", "").astype(str) + " " +
        cands.get("raw_text", "").astype(str)
    )

    # Attach texts to pairs
    df = pairs.merge(jobs[["job_id", "job_text"]], on="job_id", how="left")
    df = df.merge(cands[["candidate_id", "cand_text"]], on="candidate_id", how="left")

    df = df[["job_id", "candidate_id", "job_text", "cand_text", "weak_score"]].dropna()

    # Sample per job (keeps diversity, reduces training time)
    df = (
        df.groupby("job_id", group_keys=False)
          .apply(lambda x: x.sample(n=min(sample_per_job, len(x)), random_state=random_state))
          .reset_index(drop=True)
    )

    # Split
    train, temp = train_test_split(df, test_size=0.2, random_state=random_state)
    val, test = train_test_split(temp, test_size=0.5, random_state=random_state)

    train.to_csv(TRAIN_PATH, index=False)
    val.to_csv(VAL_PATH, index=False)
    test.to_csv(TEST_PATH, index=False)

    print("✅ Written:")
    print(" -", TRAIN_PATH, "rows:", len(train))
    print(" -", VAL_PATH, "rows:", len(val))
    print(" -", TEST_PATH, "rows:", len(test))


if __name__ == "__main__":
    main()
