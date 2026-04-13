from __future__ import annotations

import sys
from pathlib import Path
import math
import pandas as pd
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

JOBS_PATH = ROOT / "data" / "processed" / "jobs_enriched.csv"
CANDS_PATH = ROOT / "outputs" / "parsing" / "candidates_enriched.csv"  # preferred
OUT_DIR = ROOT / "outputs" / "pairs"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / "job_candidate_pairs.csv"


# ----------------------------
# Helpers
# ----------------------------
def parse_skill_str(s: str) -> set[str]:
    if not isinstance(s, str) or not s.strip():
        return set()
    return {x.strip().lower() for x in s.split(",") if x.strip()}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def overlap_ratio(job: set[str], cand: set[str]) -> float:
    # % of job skills covered by candidate
    if not job:
        return 0.0
    return len(job & cand) / len(job)


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def exp_score(cand_years: float | int | None, job_min: float | int | None) -> float:
    """
    Simple experience scoring:
    - if job doesn't specify -> neutral 0.5
    - if candidate meets/exceeds -> near 1
    - if below -> scaled down
    """
    if job_min is None or (isinstance(job_min, float) and math.isnan(job_min)):
        return 0.5

    try:
        jm = float(job_min)
    except:
        return 0.5

    if cand_years is None or (isinstance(cand_years, float) and math.isnan(cand_years)):
        return 0.0

    cy = float(cand_years)
    if cy >= jm:
        return 1.0
    # partial credit if close
    return clamp(cy / jm)


EDU_RANK = {"any": 0, "intermediate": 1, "bachelors": 2, "masters": 3, "phd": 4}

def edu_score(cand_deg: str, job_req: str) -> float:
    jr = (job_req or "any").strip().lower()
    cd = (cand_deg or "").strip().lower()

    # if job doesn't care
    if jr not in EDU_RANK or jr == "any":
        return 0.5

    # if candidate unknown
    if cd not in EDU_RANK:
        return 0.0

    return 1.0 if EDU_RANK[cd] >= EDU_RANK[jr] else 0.0


def weak_score(job_skills: set[str], cand_skills: set[str], exp_s: float, edu_s: float) -> float:
    """
    Weighted scoring (transparent + viva-friendly):
    - skills matter most
    """
    skill_cov = overlap_ratio(job_skills, cand_skills)      # main
    skill_jac = jaccard(job_skills, cand_skills)            # secondary
    skills_final = 0.75 * skill_cov + 0.25 * skill_jac

    score = 0.70 * skills_final + 0.20 * exp_s + 0.10 * edu_s
    return clamp(score)


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
