from __future__ import annotations

import sys
import re
import hashlib
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from tqdm import tqdm

from src.parsing.skill_mining import skills_for_resume
from src.parsing.skill_taxonomy import DOMAIN_KEYWORDS

IN_DIR = ROOT / "data" / "raw" / "jobs_inbox"
OUT_DIR = ROOT / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_PATH = OUT_DIR / "jobs.csv"

# ✅ Use the SAME vocab as candidates for consistency
CAND_VOCAB_PATH = ROOT / "outputs" / "parsing" / "skills_vocab.csv"


# ----------------------------
# Cleaning
# ----------------------------
BULLET_CHARS = r"[\u2022\u2023\u25E6\u2043\u2219\u00B7\u25CF\u25AA\u25AB\u25A0\u25A1\uF0B7\uF0A7\uF0D8\uF0FC\uFEFF]"
RE_BULLETS = re.compile(BULLET_CHARS)
RE_MULTI_SPACE = re.compile(r"\s+")
RE_PIPES = re.compile(r"[|]+")

def clean_text(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = RE_BULLETS.sub(" ", s)
    s = RE_PIPES.sub(" ", s)
    s = re.sub(r"(?m)^\s*[-–—]+\s*", "", s)
    s = RE_MULTI_SPACE.sub(" ", s).strip()
    return s


# ----------------------------
# Requirement extraction
# ----------------------------
RE_RANGE = re.compile(r"\b(\d{1,2})\s*[-–to]+\s*(\d{1,2})\s*(?:years?|yrs?)\b", re.IGNORECASE)
RE_YEARS  = re.compile(r"\b(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", re.IGNORECASE)
RE_XP     = re.compile(r"\b(\d{1,2})\s*\+?\s*(?:years?|yrs?)\s+of\s+experience\b", re.IGNORECASE)

EDU_PATTERNS = [
    (re.compile(r"\b(ph\.?d|doctorate)\b", re.IGNORECASE), "phd"),
    (re.compile(r"\b(master'?s|msc|ms)\b", re.IGNORECASE), "masters"),
    (re.compile(r"\b(bachelor'?s|bs|bsc|be|b\.e)\b", re.IGNORECASE), "bachelors"),
    (re.compile(r"\b(intermediate|a-?levels|fsc)\b", re.IGNORECASE), "intermediate"),
]

def extract_min_experience_years(text: str) -> int | None:
    t = text.lower()

    m = RE_RANGE.search(t)
    if m:
        return int(m.group(1))

    m = RE_XP.search(t)
    if m:
        return int(m.group(1))

    years = [int(x) for x in RE_YEARS.findall(t)]
    return min(years) if years else None

def extract_education_required(text: str) -> str:
    t = text.lower()
    for pat, label in EDU_PATTERNS:
        if pat.search(t):
            return label
    return "any"


# ----------------------------
# Department inference (skills + fallback keywords)
# ----------------------------
DEPT_FALLBACK = {
    "engineering": {"software", "developer", "backend", "frontend", "full stack", "react", "node", "nestjs"},
    "qa": {"qa", "sqa", "testing", "selenium", "cypress", "playwright", "postman"},
    "design": {"ui", "ux", "ui/ux", "figma", "wireframe", "prototype", "graphic"},
    "data": {"data", "ml", "machine learning", "python", "sql", "pandas", "tensorflow"},
    "devops": {"devops", "aws", "docker", "kubernetes", "ci/cd", "jenkins", "terraform"},
    "product": {"product", "roadmap", "user stories", "backlog", "scrum", "prd", "mvp"},
    "marketing": {"marketing", "seo", "ads", "google analytics", "content"},
    "sales": {"sales", "business development", "lead generation", "crm"},
    "hr": {"hr", "recruitment", "talent", "payroll"},
    "finance": {"finance", "accounting", "audit", "ifrs", "budgeting"},
    "operations": {"operations", "process", "sop", "compliance", "vendor", "procurement"},
}

def infer_department(job_title: str, job_desc: str, skills: List[str]) -> str:
    # 1) skill-based (most reliable if skills exist)
    sset = set(skills)
    hits = []
    for dept, keys in DOMAIN_KEYWORDS.items():
        inter = sset.intersection(keys)
        if inter:
            hits.append((dept, len(inter)))
    if hits:
        hits.sort(key=lambda x: x[1], reverse=True)
        return hits[0][0]

    # 2) fallback keyword-based
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


def job_id_from_file(path: Path) -> str:
    b = (path.name + "::" + str(path.stat().st_size)).encode("utf-8", errors="ignore")
    return hashlib.md5(b).hexdigest()[:10]

def clean_title_from_filename(stem: str) -> str:
    # remove leading "001 " / "001_" style prefixes
    s = stem.replace("_", " ").strip()
    s = re.sub(r"^\d+\s*", "", s).strip()
    return s


def load_candidate_vocab() -> set[str]:
    if not CAND_VOCAB_PATH.exists():
        raise SystemExit(f"Missing {CAND_VOCAB_PATH}. Run resume parsing first to generate skills_vocab.csv.")
    sv = pd.read_csv(CAND_VOCAB_PATH)
    return set(sv["skill"].dropna().astype(str).str.strip().str.lower().tolist())


def main():
    files = sorted(IN_DIR.rglob("*.txt"))
    if not files:
        raise SystemExit(f"No .txt job files found in: {IN_DIR}")

    vocab_set = load_candidate_vocab()

    rows: List[Dict] = []
    print(f"Found {len(files)} job descriptions.")

    for p in tqdm(files):
        raw = p.read_text(encoding="utf-8", errors="ignore").strip()
        jd = clean_text(raw)

        job_title = clean_title_from_filename(p.stem)

        # Extract skills using SAME vocab as candidates
        skills = skills_for_resume(jd, vocab_set)
        dept = infer_department(job_title, jd, skills)

        rows.append({
            "job_id": job_id_from_file(p),
            "source_file": str(p.relative_to(ROOT)),
            "job_title": job_title,
            "department": dept,
            "job_description_raw": jd,
            "job_skills": ", ".join(skills),
            "min_experience": extract_min_experience_years(jd),
            "education_required": extract_education_required(jd),
        })

    df = pd.DataFrame(rows)
    df.to_csv(OUT_PATH, index=False)

    print("✅ Written:", OUT_PATH)
    print(df[["job_id","job_title","department","min_experience","education_required"]].to_string(index=False))


if __name__ == "__main__":
    main()
