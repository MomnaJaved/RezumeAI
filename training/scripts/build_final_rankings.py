from __future__ import annotations
import pandas as pd

JOB_ID = "J004"  # change job id when needed

tfidf_path = "outputs/rankings/tfidf_rankings.csv"
transformer_path = f"outputs/rankings/transformer_rankings_{JOB_ID}.csv"
weak_path = "outputs/pairs/job_candidate_pairs.csv"

tfidf = pd.read_csv(tfidf_path)
transformer = pd.read_csv(transformer_path)
weak = pd.read_csv(weak_path)

# Filter job
tfidf = tfidf[tfidf["job_id"] == JOB_ID]
weak = weak[weak["job_id"] == JOB_ID]

df = transformer.merge(
    tfidf[["candidate_id", "tfidf_score"]],
    on="candidate_id",
    how="left"
)

df = df.merge(
    weak[["candidate_id", "weak_score", "skills_matched"]],
    on="candidate_id",
    how="left"
)

df = df.fillna(0)

df["final_score"] = (
    0.2 * df["weak_score"] +
    0.3 * df["tfidf_score"] +
    0.5 * df["transformer_score"]
)

df = df.sort_values("final_score", ascending=False)

job_title = "backend developer"  # or load from jobs_enriched.csv by JOB_ID

def title_boost(candidate_title: str) -> float:
    t = str(candidate_title).lower()
    if "backend" in t:
        return 0.03
    if "full stack" in t or "fullstack" in t:
        return 0.015
    return 0.0

df["final_score"] = df["final_score"] + df["title"].apply(title_boost)
df = df.sort_values("final_score", ascending=False)

out_path = f"outputs/rankings/final_rankings_{JOB_ID}.csv"
df.to_csv(out_path, index=False)

print("✅ Final rankings saved to:", out_path)
print(df.head(10)[["candidate_id","title","final_score","skills_matched"]])
