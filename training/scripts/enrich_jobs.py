from __future__ import annotations

import sys
import re
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from src.parsing.skill_mining import skills_for_resume
from src.parsing.skill_taxonomy import DOMAIN_KEYWORDS

JOBS_PATH = ROOT / "data" / "processed" / "jobs.csv"
OUT_PATH = ROOT / "data" / "processed" / "jobs_enriched.csv"
CAND_VOCAB_PATH = ROOT / "outputs" / "parsing" / "skills_vocab.csv"


# ----------------------------
# Experience + education extraction
# ----------------------------
RE_RANGE = re.compile(r"\b(\d{1,2})\s*[-–to]+\s*(\d{1,2})\s*(?:years?|yrs?)\b", re.IGNORECASE)
RE_YEARS  = re.compile(r"\b(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", re.IGNORECASE)
RE_XP     = re.compile(r"\b(\d{1,2})\s*\+?\s*(?:years?|yrs?)\s+of\s+experience\b", re.IGNORECASE)
RE_MIN    = re.compile(r"\b(minimum|min)\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", re.IGNORECASE)
RE_ATLEAST= re.compile(r"\b(at\s+least)\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", re.IGNORECASE)

EDU_PATTERNS = [
    (re.compile(r"\b(ph\.?d|doctorate)\b", re.IGNORECASE), "phd"),
    (re.compile(r"\b(master'?s|msc|ms)\b", re.IGNORECASE), "masters"),
    (re.compile(r"\b(bachelor'?s|bs|bsc|be|b\.e)\b", re.IGNORECASE), "bachelors"),
]

def extract_min_experience_years(text: str) -> int | None:
    if not isinstance(text, str):
        return None
    t = text.lower()

    m = RE_RANGE.search(t)
    if m:
        return int(m.group(1))

    m = RE_MIN.search(t)
    if m:
        return int(m.group(2))

    m = RE_ATLEAST.search(t)
    if m:
        return int(m.group(2))

    m = RE_XP.search(t)
    if m:
        return int(m.group(1))

    years = [int(x) for x in RE_YEARS.findall(t)]
    return min(years) if years else None

def extract_education_required(text: str) -> str:
    if not isinstance(text, str):
        return "any"
    t = text.lower()
    for pat, label in EDU_PATTERNS:
        if pat.search(t):
            return label
    return "any"


# ----------------------------
# Department inference
# ----------------------------
DEPT_FALLBACK = {
    "engineering": {"software", "developer", "backend", "frontend", "full stack", "api", "react", "node", "nestjs"},
    "qa": {"qa", "sqa", "testing", "selenium", "cypress", "playwright", "postman", "jira"},
    "design": {"ui", "ux", "ui/ux", "figma", "wireframe", "prototype", "graphic", "illustrator", "photoshop"},
    "data": {"data", "data analyst", "data analytics", "ml", "machine learning", "python", "sql", "pandas", "power bi", "excel"},
    "devops": {"devops", "aws", "docker", "kubernetes", "ci/cd", "jenkins", "terraform"},
    "product": {"product", "roadmap", "user stories", "backlog", "scrum", "prd", "mvp"},
    "marketing": {"marketing", "seo", "ads", "google analytics", "content", "social media"},
    "sales": {"sales", "business development", "lead generation", "crm", "pipeline"},
    "hr": {"hr", "recruitment", "talent", "onboarding", "payroll", "hris", "ats"},
    "finance": {"finance", "accounting", "audit", "ifrs", "budgeting", "forecasting", "ledger"},
    "operations": {"operations", "process", "sop", "compliance", "vendor", "procurement", "logistics"},
}

def infer_department(job_title: str, job_desc: str, skills: List[str]) -> str:
    sset = set(skills)

    # 1) skill-based (preferred)
    hits = []
    for dept, keys in DOMAIN_KEYWORDS.items():
        inter = sset.intersection(keys)
        if inter:
            hits.append((dept, len(inter)))
    if hits:
        hits.sort(key=lambda x: x[1], reverse=True)
        return hits[0][0]

    # 2) keyword fallback (title + description)
    blob = f"{job_title} {job_desc}".lower()
    fb = []
    for dept, kws in DEPT_FALLBACK.items():
        score = sum(1 for k in kws if k in blob)
        if score:
            fb.append((dept, score))
    if fb:
        fb.sort(key=lambda x: x[1], reverse=True)
        return fb[0][0]

    return "general"


def load_candidate_vocab() -> set[str]:
    if not CAND_VOCAB_PATH.exists():
        raise SystemExit(f"Missing {CAND_VOCAB_PATH}. Run resume parsing first to generate skills vocab.")
    sv = pd.read_csv(CAND_VOCAB_PATH)
    return set(sv["skill"].dropna().astype(str).str.strip().str.lower().tolist())


def parse_manual_skills(s: str) -> List[str]:
    if not isinstance(s, str) or not s.strip():
        return []
    return [x.strip().lower() for x in s.split(",") if x.strip()]

def merge_skills(a: List[str], b: List[str]) -> str:
    seen = set()
    out = []
    for x in a + b:
        x = x.strip().lower()
        if not x:
            continue
        if x not in seen:
            seen.add(x)
            out.append(x)
    return ", ".join(out)


def main():
    if not JOBS_PATH.exists():
        raise SystemExit(f"Missing {JOBS_PATH}")

    df = pd.read_csv(JOBS_PATH).fillna("")
    vocab_set = load_candidate_vocab()

    for col in ["job_skills", "min_experience", "education_required", "department"]:
        if col not in df.columns:
            df[col] = ""

    out_job_skills = []
    out_min_exp = []
    out_edu = []
    out_dept = []

    for _, row in df.iterrows():
        title = str(row.get("job_title", "")).strip()
        desc = str(row.get("job_description_raw", "")).strip()

        # 1) Skills: merge manual + extracted
        manual_sk = parse_manual_skills(str(row.get("job_skills", "")))
        extracted_sk = skills_for_resume(desc, vocab_set)
        out_job_skills.append(merge_skills(manual_sk, extracted_sk))

        # 2) Min experience: keep manual if present
        manual_min = str(row.get("min_experience", "")).strip()
        if manual_min != "":
            try:
                out_min_exp.append(int(float(manual_min)))
            except:
                out_min_exp.append(extract_min_experience_years(desc))
        else:
            out_min_exp.append(extract_min_experience_years(desc))

        # 3) Education: keep manual if present and valid
        manual_edu = str(row.get("education_required", "")).strip().lower()
        if manual_edu in {"any", "bachelors", "masters", "phd"}:
            out_edu.append(manual_edu)
        elif manual_edu:
            # if user wrote something else, try to normalize via extractor
            out_edu.append(extract_education_required(manual_edu))
        else:
            out_edu.append(extract_education_required(desc))

        # 4) Department: keep manual if present; else infer
        manual_dept = str(row.get("department", "")).strip().lower()
        if manual_dept and manual_dept != "general":
            out_dept.append(manual_dept)
        else:
            out_dept.append(infer_department(title, desc, extracted_sk))

    df["job_skills"] = out_job_skills
    df["min_experience"] = out_min_exp
    df["education_required"] = out_edu
    df["department"] = out_dept

    df.to_csv(OUT_PATH, index=False)
    print("✅ Written:", OUT_PATH)
    print(df[["job_id","job_title","department","min_experience","education_required"]].to_string(index=False))


if __name__ == "__main__":
    main()
