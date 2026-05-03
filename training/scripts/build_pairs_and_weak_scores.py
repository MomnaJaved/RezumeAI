from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

JOBS_PATH = ROOT / "data" / "processed" / "jobs_enriched.csv"
CANDS_PATH = ROOT / "outputs" / "parsing" / "candidates_enriched.csv"  # preferred
OUT_DIR = ROOT / "outputs" / "pairs"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / "job_candidate_pairs.csv"

from src.matching.weak_score import (  # noqa: E402
    edu_score,
    exp_score,
    overlap_ratio,
    parse_skill_str,
    weak_score,
)


def main():
    if not JOBS_PATH.exists():
        raise SystemExit(f"Missing: {JOBS_PATH}")
    if not CANDS_PATH.exists():
        raise SystemExit(f"Missing: {CANDS_PATH} (run candidate enrichment first)")

    jobs = pd.read_csv(JOBS_PATH).fillna("")
    cands = pd.read_csv(CANDS_PATH).fillna("")

    print("Jobs:", len(jobs), "| Candidates:", len(cands))
    print("This will create pairs =", len(jobs) * len(cands))

    # Pre-parse candidate skills once (speed)
    cand_skill_sets = [parse_skill_str(s) for s in cands["skills"].astype(str).tolist()]
    cand_years = cands.get("years_experience_est", pd.Series([None] * len(cands))).tolist()
    cand_deg = cands.get("highest_degree", pd.Series([""] * len(cands))).astype(str).tolist()

    out_rows = []
    chunk_size = 200_000
    wrote_header = False

    for j_idx in range(len(jobs)):
        j = jobs.iloc[j_idx]
        job_id = str(j.get("job_id", ""))
        job_title = str(j.get("job_title", ""))
        job_dept = str(j.get("department", ""))

        job_skill_set = parse_skill_str(str(j.get("job_skills", "")))
        job_min_exp = j.get("min_experience", None)
        job_edu_req = str(j.get("education_required", "any"))

        for c_idx in range(len(cands)):
            exp_s = exp_score(cand_years[c_idx], job_min_exp)
            edu_s = edu_score(cand_deg[c_idx], job_edu_req)
            score = weak_score(job_skill_set, cand_skill_sets[c_idx], exp_s, edu_s)

            # store top matching skills for explainability
            matched = sorted(list(job_skill_set & cand_skill_sets[c_idx]))[:25]

            out_rows.append({
                "job_id": job_id,
                "job_title": job_title,
                "job_department": job_dept,
                "candidate_id": cands.iloc[c_idx]["candidate_id"],
                "candidate_title": cands.iloc[c_idx].get("title", ""),
                "skills_matched": ", ".join(matched),
                "skill_coverage": overlap_ratio(job_skill_set, cand_skill_sets[c_idx]),
                "exp_score": exp_s,
                "edu_score": edu_s,
                "weak_score": score,
            })

            # write in chunks to avoid RAM issues
            if len(out_rows) >= chunk_size:
                pd.DataFrame(out_rows).to_csv(
                    OUT_PATH,
                    mode="a",
                    header=not wrote_header,
                    index=False
                )
                wrote_header = True
                out_rows = []

        print(f"✅ Finished job {job_id} ({j_idx+1}/{len(jobs)})")

    # write remaining
    if out_rows:
        pd.DataFrame(out_rows).to_csv(
            OUT_PATH,
            mode="a",
            header=not wrote_header,
            index=False
        )

    print("✅ Written:", OUT_PATH)
    print("Tip: This file can be large. Use sampling for quick experiments.")


if __name__ == "__main__":
    main()
