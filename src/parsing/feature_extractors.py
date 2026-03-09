from __future__ import annotations
import re
from typing import Dict, List, Tuple

# ---------- EDUCATION ----------
DEGREE_PATTERNS = [
    r"\bph\.?d\b|\bdoctorate\b",
    r"\bmaster\b|\bm\.?s\b|\bm\.?sc\b|\bmba\b|\bm\.?phil\b",
    r"\bbachelor\b|\bb\.?s\b|\bbs\b|\bb\.?sc\b|\bbe\b|\bbeng\b|\bba\b",
    r"\bintermediate\b|\bfsc\b|\bics\b|\ba-?levels\b",
    r"\bmatric\b|\bssc\b|\bo-?levels\b",
]
DEGREE_RANK = ["phd", "master", "bachelor", "intermediate", "matric"]

RE_EDU_LINE = re.compile(r"^(.*\b(university|college|institute|school)\b.*)$", re.IGNORECASE)

def extract_education(text: str) -> Dict:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    edu_lines = [l for l in lines if RE_EDU_LINE.search(l)]
    found = set()

    t = text.lower()
    for p in DEGREE_PATTERNS:
        if re.search(p, t, re.IGNORECASE):
            # map to rank bucket
            if "ph" in p or "doctorate" in p:
                found.add("phd")
            elif "master" in p or "mba" in p or "m.sc" in p or "mphil" in p:
                found.add("master")
            elif "bachelor" in p or "b.sc" in p or "bs" in p or "be" in p or "beng" in p or "ba" in p:
                found.add("bachelor")
            elif "intermediate" in p or "fsc" in p or "ics" in p or "a-" in p:
                found.add("intermediate")
            else:
                found.add("matric")

    highest = ""
    for r in DEGREE_RANK:
        if r in found:
            highest = r
            break

    return {
        "highest_degree": highest,
        "education_lines": " | ".join(edu_lines[:8])  # keep short
    }

# ---------- CERTIFICATIONS ----------
RE_CERT = re.compile(r"\b(certification|certified|certificate)\b", re.IGNORECASE)
RE_CERT_LINE = re.compile(r"^(.*\b(certification|certified|certificate)\b.*)$", re.IGNORECASE)

def extract_certifications(text: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    cert_lines = [l for l in lines if RE_CERT_LINE.search(l)]
    # light cleanup
    cert_lines = [re.sub(r"\s+", " ", l) for l in cert_lines]
    return " | ".join(cert_lines[:10])

# ---------- YEARS OF EXPERIENCE ----------
# We’ll estimate by finding year ranges: 2019–2023, 2020-2024, etc.
RE_YEAR = re.compile(r"\b(19[8-9]\d|20[0-3]\d)\b")
RE_RANGE = re.compile(r"\b(19[8-9]\d|20[0-3]\d)\s*[-–]\s*(19[8-9]\d|20[0-3]\d|present|current)\b", re.IGNORECASE)

def estimate_years_experience(text: str, current_year: int = 2026) -> float:
    t = text.lower()
    ranges = RE_RANGE.findall(t)

    total = 0.0
    for start, end in ranges:
        try:
            s = int(start)
        except:
            continue
        if end in ("present", "current"):
            e = current_year
        else:
            try:
                e = int(end)
            except:
                e = current_year
        if 1980 <= s <= current_year and 1980 <= e <= current_year and e >= s:
            total += (e - s)

    # fallback: if no ranges, return 0
    # we cap to avoid crazy outputs
    return round(min(total, 40.0), 1)
