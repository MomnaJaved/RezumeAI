from __future__ import annotations
import re
from datetime import datetime
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
# Goal: estimate WORK experience only (avoid counting education date ranges).
# Year token we can capture as group(1)
_YEAR = r"(?:19[8-9]\d|20\d{2})"  # 1980–2099
# Hyphen, en dash, em dash, or "to" between years / present.
RE_RANGE = re.compile(
    rf"\b({_YEAR})\s*[-–—]{{1,2}}\s*({_YEAR}|present|current)\b",
    re.IGNORECASE,
)
RE_RANGE_TO = re.compile(
    rf"\b({_YEAR})\s+to\s+({_YEAR}|present|current)\b",
    re.IGNORECASE,
)
# 1/2020 – 6/2024 or 01/2020-12/2023 (requires 4-digit year; avoids day-first ambiguity).
RE_RANGE_SLASH = re.compile(
    rf"\b\d{{1,2}}/({_YEAR})\s*[-–—]\s*\d{{1,2}}/({_YEAR}|present|current)\b",
    re.IGNORECASE,
)
RE_RANGE_SLASH_PRESENT = re.compile(
    rf"\b\d{{1,2}}/({_YEAR})\s*[-–—]\s*(present|current|now|ongoing)\b",
    re.IGNORECASE,
)
# Year/month using dash: 2020/01 - 2024/06 or 2020-01 – 2024-06
RE_RANGE_YM = re.compile(
    rf"\b({_YEAR})[/-]\d{{1,2}}\s*[-–—]\s*({_YEAR}|present|current|now|ongoing)(?:[/-]\d{{1,2}})?\b",
    re.IGNORECASE,
)
# Jan 2020 – Mar 2024 / January 2020 - Present
_RE_MO = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
    r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)
RE_RANGE_MONTH = re.compile(
    rf"\b(?:{_RE_MO})\.?\s+({_YEAR})\s*[-–—]\s*(?:(?:{_RE_MO})\.?\s+)?({_YEAR}|present|current|now|ongoing)\b",
    re.IGNORECASE,
)
RE_YEARS_PHRASE = re.compile(
    r"\b(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years|yrs|yr)\b(?:\s+of)?",
    re.IGNORECASE,
)
RE_YEARS_PHRASE_LEADING = re.compile(
    r"\b(?:over|more than|at least)\s+(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years|yrs|yr)\b",
    re.IGNORECASE,
)
# Optional bullets / numbering before section titles (PDFs often prepend • or ·).
_LINE_LEAD = r"^\s*(?:[\u2022\u2023\u25CF\u25CB●○·\*•\-–]|\d{1,2}[.)]\s*)?\s*"
RE_EXP_START = re.compile(
    _LINE_LEAD
    + r"(work experience|working experience|professional experience|employment history|work history|career history|"
    r"industry experience|relevant experience|relevant work experience|professional background|"
    r"employment|experience|career)\b",
    re.IGNORECASE,
)
# Major section headings that should end the experience block (when they appear as headings).
# We intentionally avoid matching inline phrases like "Skills: Python, AWS" (handled below).
# Treat these as section headings even if they have trailing content
# (e.g. "EDUCATION 2010-2014" from PDF extraction).
RE_SECTION_HEADING = re.compile(
    _LINE_LEAD
    + r"(?P<h>"
    r"education|academic|certifications?|certification|skills|projects?|publications?|languages?|awards?|"
    r"references?|interests?|summary|profile|objective|about|contact"
    r")\b",
    re.IGNORECASE,
)
RE_INLINE_LABEL = re.compile(r"^\s*[A-Za-z][A-Za-z /&+-]{0,40}:\s+\S+", re.IGNORECASE)
# Education-ish keywords; keep broad to avoid counting degree date ranges as work.
RE_EDU_HINT = re.compile(
    r"\b("
    r"university|college|institute|school|"
    r"education|academic|"
    r"bachelor|master|ph\.?d|doctorate|"
    r"b\.?s\b|bs\b|b\.?sc\b|bsc\b|b\.?a\b|ba\b|"
    r"m\.?s\b|ms\b|m\.?sc\b|msc\b|mba\b|"
    r"gpa|graduat(?:e|ion)|coursework|major|minor"
    r")\b",
    re.IGNORECASE,
)
RE_WORK_HINT = re.compile(
    r"\b(engineer|developer|analyst|manager|consultant|specialist|architect|designer|lead|"
    r"intern|freelance|contractor|inc\.?|ltd\.?|llc|corp\.?|company|technologies|solutions|"
    r"director|vp|cto|ceo|cfo|founder|president|scientist|researcher|product|programmer|"
    r"technician|nurse|physician|attorney|accountant|sales|marketing|coordinator|associate|"
    r"executive|officer|head\s+of|partner|principal|owner)\b",
    re.IGNORECASE,
)

# Insert newlines before common headers so PDFs that extract as one long line still section-parse.
_BREAK_BEFORE = re.compile(
    r"(?<!\n)[\s\u00a0]+"
    r"(?=(?:work experience|working experience|professional experience|employment history|work history|career history|"
    r"industry experience|relevant experience|relevant work experience|professional background|employment)\b)",
    re.IGNORECASE,
)
# Headings often appear as EXPERIENCE or "Experience QA Engineer ..." when the PDF omits line breaks.
_BREAK_EXPERIENCE_HEADING = re.compile(
    r"(?<!\n)[\s\u00a0]+(?=EXPERIENCE\b|Experience\b(?=\s+[A-Z]))"
)
_BREAK_EDU_ETC = re.compile(
    r"(?<!\n)[\s\u00a0]+(?=(?:education|educational background|academic background)\b)",
    re.IGNORECASE,
)


def _preprocess_resume_text_for_years(text: str) -> str:
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    # Normalize NBSP and horizontal spaces (common in PDFs) to regular space for regexes.
    t = t.replace("\u00a0", " ").replace("\u2009", " ").replace("\u2002", " ")
    # OCR / PDF: "2 0 2 0 - 2 0 2 4" → "2020-2024"
    t = re.sub(r"(?<!\d)(?:\d(?:\s+\d){3})(?!\d)", lambda m: re.sub(r"\s+", "", m.group(0)), t)
    t = _BREAK_BEFORE.sub("\n", t)
    t = _BREAK_EXPERIENCE_HEADING.sub("\n", t)
    t = _BREAK_EDU_ETC.sub("\n", t)
    return t

_RANGE_PATTERNS = (
    RE_RANGE,
    RE_RANGE_TO,
    RE_RANGE_SLASH,
    RE_RANGE_SLASH_PRESENT,
    RE_RANGE_YM,
    RE_RANGE_MONTH,
)


def _end_token_to_year(end: str, current_year: int) -> int:
    el = end.lower()
    if el in ("present", "current", "now", "ongoing"):
        return current_year
    try:
        return int(end)
    except ValueError:
        return current_year


def _span_years(start: str, end: str, current_year: int) -> float:
    # start/end are year tokens only
    try:
        s = int(start)
    except ValueError:
        return 0.0
    e = _end_token_to_year(end, current_year)
    if 1980 <= s <= current_year and 1980 <= e <= current_year and e >= s:
        return float(e - s)
    return 0.0


def _range_year_interval(start_year: int, end_year: int) -> tuple[float, float]:
    # Use [start, end] as continuous years; treat year-only as whole-year boundaries.
    # Example: 2020-2024 → 4.0 years.
    return float(start_year), float(end_year)


def _range_month_interval(start_year: int, start_month: int, end_year: int, end_month: int) -> tuple[float, float]:
    # Convert to fractional years; months are 1-12.
    s = start_year + (max(1, min(12, start_month)) - 1) / 12.0
    e = end_year + (max(1, min(12, end_month)) - 1) / 12.0
    return float(s), float(e)


def _merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not intervals:
        return []
    intervals = sorted(intervals, key=lambda x: (x[0], x[1]))
    merged: list[tuple[float, float]] = [intervals[0]]
    for s, e in intervals[1:]:
        ps, pe = merged[-1]
        # Overlap or touch → merge
        if s <= pe:
            merged[-1] = (ps, max(pe, e))
        else:
            merged.append((s, e))
    return merged


def _interval_years(intervals: list[tuple[float, float]], cap: float = 40.0) -> float:
    total = 0.0
    for s, e in _merge_intervals([(a, b) for a, b in intervals if b >= a]):
        total += max(0.0, e - s)
    return min(total, cap)


_MO_NUM = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def _sum_ranges_in_text(blob: str, current_year: int) -> float:
    """
    Extract all ranges and compute UNION duration (avoid double-counting overlaps).
    """
    intervals: list[tuple[float, float]] = []
    low = blob.lower()

    # Year-only and "to" year-only
    for pat in (RE_RANGE, RE_RANGE_TO):
        for start, end in pat.findall(low):
            try:
                s = int(start)
            except ValueError:
                continue
            e = _end_token_to_year(end, current_year)
            if 1980 <= s <= current_year and 1980 <= e <= current_year and e >= s:
                intervals.append(_range_year_interval(s, e))

    # MM/YYYY – MM/YYYY or MM/YYYY – Present
    for m in re.finditer(
        rf"\b(?P<sm>\d{{1,2}})/(?P<sy>{_YEAR})\s*[-–—]\s*(?:(?P<em>\d{{1,2}})/(?P<ey>{_YEAR})|(?P<ep>present|current|now|ongoing))\b",
        low,
        flags=re.IGNORECASE,
    ):
        sm = int(m.group("sm"))
        sy = int(m.group("sy"))
        if m.group("ep"):
            ey = current_year
            em = 12
        else:
            em = int(m.group("em"))
            ey = int(m.group("ey"))
        if 1980 <= sy <= current_year and 1980 <= ey <= current_year and (ey, em) >= (sy, sm):
            intervals.append(_range_month_interval(sy, sm, ey, em))

    # Month name ranges (Jan 2020 – Mar 2024 / Jan 2020 – Present)
    for m in re.finditer(
        rf"\b(?P<sm>{_RE_MO})\.?\s+(?P<sy>{_YEAR})\s*[-–—]\s*(?:(?P<em>{_RE_MO})\.?\s+(?P<ey>{_YEAR})|(?P<ep>present|current|now|ongoing))\b",
        low,
        flags=re.IGNORECASE,
    ):
        sm_txt = m.group("sm")[:4].lower().replace(".", "")
        sm_txt = "sept" if sm_txt.startswith("sept") else sm_txt[:3]
        sm = _MO_NUM.get(sm_txt[:3], 1)
        sy = int(m.group("sy"))
        if m.group("ep"):
            ey = current_year
            em = 12
        else:
            em_txt = m.group("em")[:4].lower().replace(".", "")
            em_txt = "sept" if em_txt.startswith("sept") else em_txt[:3]
            em = _MO_NUM.get(em_txt[:3], 12)
            ey = int(m.group("ey"))
        if 1980 <= sy <= current_year and 1980 <= ey <= current_year and (ey, em) >= (sy, sm):
            intervals.append(_range_month_interval(sy, sm, ey, em))

    # YM compact (2020/01 - 2024/06); we only keep year precision if months are missing in capture
    for m in re.finditer(
        rf"\b(?P<sy>{_YEAR})[/-](?P<sm>\d{{1,2}})\s*[-–—]\s*(?:(?P<ey>{_YEAR})[/-](?P<em>\d{{1,2}})|(?P<ep>present|current|now|ongoing))\b",
        low,
        flags=re.IGNORECASE,
    ):
        sy = int(m.group("sy"))
        sm = int(m.group("sm"))
        if m.group("ep"):
            ey = current_year
            em = 12
        else:
            ey = int(m.group("ey"))
            em = int(m.group("em"))
        if 1980 <= sy <= current_year and 1980 <= ey <= current_year and (ey, em) >= (sy, sm):
            intervals.append(_range_month_interval(sy, sm, ey, em))

    return round(_interval_years(intervals), 4)


def _sum_ranges_last_resort(text: str, current_year: int, *, require_work_hint: bool) -> float:
    intervals: list[tuple[float, float]] = []
    full = text.lower()
    for pat in _RANGE_PATTERNS:
        for m in pat.finditer(full):
            lo = max(0, m.start() - 140)
            hi = min(len(full), m.end() + 140)
            ctx = full[lo:hi]
            if RE_EDU_HINT.search(ctx) and not RE_WORK_HINT.search(ctx):
                continue
            if require_work_hint and not RE_WORK_HINT.search(ctx):
                # If we couldn't find an experience section, only accept ranges that look work-related.
                continue
            # For last-resort, treat everything as year-only interval based on captured groups.
            try:
                s = int(m.group(1))
            except Exception:
                continue
            e = _end_token_to_year(m.group(2), current_year)
            if 1980 <= s <= current_year and 1980 <= e <= current_year and e >= s:
                intervals.append(_range_year_interval(s, e))
    return _interval_years(intervals)


def estimate_years_experience(text: str, current_year: int | None = None) -> float:
    """
    Heuristic:
    - Prefer explicit 'X years' phrase if present (common on resumes).
    - Else, sum year ranges but only from WORK/EXPERIENCE sections, and avoid education hints.
    """
    if current_year is None:
        current_year = datetime.now().year

    if not isinstance(text, str) or not text.strip():
        return 0.0

    text = _preprocess_resume_text_for_years(text.strip())

    # 1) Explicit "X years" (take max)
    years_phr = [float(m) for m in RE_YEARS_PHRASE.findall(text)]
    years_phr += [float(m) for m in RE_YEARS_PHRASE_LEADING.findall(text)]
    if years_phr:
        return round(min(max(years_phr), 40.0), 1)

    lines = [ln.strip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").splitlines()]

    def _line_has_range(ln: str) -> bool:
        low = ln.lower()
        return any(p.search(low) for p in _RANGE_PATTERNS)

    # 2) Focus on experience-ish sections: start at an experience heading, stop at next heading.
    in_exp = False
    exp_lines: list[str] = []
    saw_exp_header = False
    for ln in lines:
        if not ln:
            continue
        m_start = RE_EXP_START.search(ln)
        if m_start:
            in_exp = True
            saw_exp_header = True
            tail = ln[m_start.end() :].strip()
            if tail:
                exp_lines.append(tail)
            continue
        if in_exp:
            # End experience section on the next standalone heading (Education, Skills, Projects, etc.).
            # But do NOT end on inline labels like "Skills: Python, AWS".
            if RE_SECTION_HEADING.search(ln) and not RE_INLINE_LABEL.search(ln):
                in_exp = False
                continue
        if in_exp:
            exp_lines.append(ln)

    # Strict behavior: if we didn't find an experience section, don't guess from education dates.
    # (We still allow "X years" phrases globally in step (1) above.)
    if not exp_lines and not saw_exp_header:
        return 0.0

    t = "\n".join(exp_lines).lower()
    total = _sum_ranges_in_text(t, current_year)

    if total <= 0:
        # If we had an experience header but couldn't parse ranges from the section text,
        # try last-resort matching within the whole text but require work hint.
        total = _sum_ranges_last_resort(text, current_year, require_work_hint=True)

    return round(min(total, 40.0), 1)
