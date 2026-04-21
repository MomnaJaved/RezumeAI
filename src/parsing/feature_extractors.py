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

RE_EDU_LINE = re.compile(
    r"^(.*(?:\b(university|college|institute|school|academy|polytechnic|conservatory|univ\.?)\b"
    r"|(?:^|\s)(?:MIT|CMU|NYU|USC|GT|UIUC)(?:\s|,|$))).*$",
    re.IGNORECASE,
)

# Lines that leaked in from other resume sections (whole-line filter).
_RE_EDU_LEAK = re.compile(
    r"\b(work experience|employment history|professional experience|career history|"
    r"^skills\s*:|\bskills\s+and\b|\btechnical skills\b)\b",
    re.IGNORECASE,
)
_RE_CERT_LEAK = re.compile(
    r"\b(work experience|employment history|education\s*:|\beducation\s+background\b)\b",
    re.IGNORECASE,
)

# PDFs often glue EDUCATION + SKILLS into one line separated by " | " (or fullwidth ｜, ZWSP noise).
_RE_INLINE_SKILLS_OR_TOOLS_TAIL = re.compile(
    r"\s*(?:\|\s*|｜\s*|/\s*)("
    r"technical\s+skills|"
    r"professional\s+skills|"
    r"core\s+competencies|"
    r"key\s+skills|"
    r"relevant\s+skills|"
    r"soft\s+skills|"
    r"skills\s+overview|"
    r"programming\s*(?:&|\+|and)\s*development|"
    r"web\s+technologies|"
    r"backend\s*(?:&|\+|and)\s*databases|"
    r"frontend\s*(?:&|\+|and)\s*backend|"
    r"languages?\s*(?:&|\+|and)\s*frameworks|"
    r"tools\s*(?:&|\+|and)\s*technologies|"
    r"frameworks?\s*(?:&|\+|and)\s*libraries|"
    r"mobile\s+development|"
    r"devops|"
    r"cloud\s+platforms?|"
    r"skills\s*:|"
    r"ui/ux\s+implementation|"
    r"responsive\s+web\s+design"
    r")\b",
    re.IGNORECASE,
)


def _normalize_resume_inline_noise(s: str) -> str:
    s = re.sub(r"[\u200b\u200c\u200d\ufeff\u00ad]", "", s)
    s = s.replace("\uff5c", "|")  # fullwidth vertical line
    return s


def _segment_looks_like_skills_block(seg: str) -> bool:
    """True when a |...| segment is clearly a skills/tools heading, not a degree line."""
    t = re.sub(r"\s+", " ", seg).strip().lower()
    if not t:
        return False
    # Short heading-only segments
    heads = (
        "technical skills",
        "professional skills",
        "programming & development",
        "programming and development",
        "web technologies",
        "backend & databases",
        "backend and databases",
        "languages & frameworks",
        "tools & technologies",
        "frameworks & libraries",
        "core competencies",
        "key skills",
        "relevant skills",
        "soft skills",
        "skills overview",
        "mobile development",
        "devops",
        "cloud platforms",
        "ui/ux implementation",
        "responsive web design",
    )
    if any(t == h or t.startswith(h + " ") or t.startswith(h + "|") for h in heads):
        return True
    if t.startswith("technical skills"):
        return True
    if re.match(r"^skills\s*:", t):
        return True
    # Bullet-heavy tech line without school words
    if re.search(r"[●•·]", t) and not re.search(
        r"\b(university|college|bachelor|master|diploma|degree|gpa|graduat)\b", t, re.I
    ):
        if re.search(
            r"\b(javascript|typescript|python|react|node\.?js|nestjs|express|html\d?|css|tailwind|mongodb|postgres|sql|aws|azure|docker|kubernetes)\b",
            t,
            re.I,
        ):
            return True
    return False


def _truncate_education_by_pipe_segments(s: str) -> str:
    """If CV used ' | ' between degree and skills, keep only education-side segments."""
    if "|" not in s and "｜" not in s:
        return s
    s2 = _normalize_resume_inline_noise(s)
    parts = [p.strip() for p in re.split(r"\s*[|｜]\s*", s2) if p.strip()]
    if len(parts) < 2:
        return s
    kept: list[str] = []
    for p in parts:
        if _segment_looks_like_skills_block(p):
            break
        kept.append(p)
    if not kept or (len(kept) == len(parts) and not any(_segment_looks_like_skills_block(x) for x in parts)):
        return s
    return " | ".join(kept).strip(" |—–-")


def _truncate_education_at_skills_tail(s: str) -> str:
    """Strip skills/tools blocks that were merged onto the same line as education (common PDF layout)."""
    if not s:
        return s
    s_norm = _normalize_resume_inline_noise(s)
    s_cut = _truncate_education_by_pipe_segments(s_norm)
    if len(s_cut) < len(s_norm):
        s_norm = s_cut
    m = _RE_INLINE_SKILLS_OR_TOOLS_TAIL.search(s_norm)
    if m:
        return s_norm[: m.start()].strip(" \t|—–-/")
    # "…2026 Technical Skills…" without a pipe before the heading
    m_ts = re.search(r"\btechnical\s+skills\b", s_norm, re.I)
    if m_ts and m_ts.start() > 20:
        tail = s_norm[m_ts.start() :]
        if re.search(r"[●•·]|\b(javascript|typescript|python|react)\b", tail, re.I):
            return s_norm[: m_ts.start()].strip(" \t|—–-/")
    # Dense bullet line after degree years: "... 2026 ● JavaScript ..."
    if re.search(r"\b(20\d{2})\b.*[●•·]", s_norm) and re.search(
        r"[●•·]\s*(JavaScript|TypeScript|Python|React|Node\.?js|HTML|CSS)\b", s_norm, re.I
    ):
        m2 = re.search(r"\s*[|｜·]\s*[●•]", s_norm)
        if m2:
            return s_norm[: m2.start()].strip(" \t|—–-/")
    return s_norm.strip()


def _split_resume_bullet_line(line: str, max_chunk: int) -> list[str]:
    """Split an overlong or multi-bullet line into separate entries."""
    s = re.sub(r"\s+", " ", line).strip()
    if not s or len(s) < 2:
        return []
    if len(s) <= max_chunk:
        return [s]
    parts = re.split(r"\s*[•·▪▫●○]\s+|;\s+(?=[A-Za-z])|(?<=\d{4})\s{2,}(?=[A-Z])", s)
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if len(p) < 10:
            continue
        if len(p) > max_chunk:
            p = p[: max_chunk - 1].rsplit(" ", 1)[0] + "…"
        out.append(p)
    return out if out else [s[:max_chunk]]


def _refine_education_lines(lines: list[str]) -> list[str]:
    refined: list[str] = []
    seen: set[str] = set()
    for line in lines:
        for part in _split_resume_bullet_line(line, 200):
            part = _truncate_education_at_skills_tail(part)
            if not part.strip():
                continue
            if _RE_EDU_LEAK.search(part) and len(part) > 80:
                continue
            if part in seen:
                continue
            seen.add(part)
            refined.append(part)
    return refined[:14]


def _refine_certification_lines(lines: list[str]) -> list[str]:
    refined: list[str] = []
    seen: set[str] = set()
    for line in lines:
        for part in _split_resume_bullet_line(line, 180):
            if _RE_CERT_LEAK.search(part) and len(part) > 70:
                continue
            if part in seen:
                continue
            seen.add(part)
            refined.append(part)
    return refined[:16]


def _line_has_degree_token(line: str) -> bool:
    low = line.lower()
    for p in DEGREE_PATTERNS:
        if re.search(p, low, re.IGNORECASE):
            return True
    return bool(re.search(r"\b(g\.?pa|major|minor|graduat|diploma|dipl\.)\b", low))


def _line_has_institution(line: str) -> bool:
    return bool(
        re.search(
            r"\b(university|college|institute|school|academy|univ\.?|polytechnic|conservatory)\b",
            line,
            re.IGNORECASE,
        )
    )


def _merge_adjacent_education_lines(lines: list[str]) -> list[str]:
    """Join split PDF lines, e.g. degree line then school name on the next line."""
    if len(lines) < 2:
        return lines
    out: list[str] = []
    i = 0
    while i < len(lines):
        a = lines[i]
        b = lines[i + 1] if i + 1 < len(lines) else ""
        if b:
            inst_a = _line_has_institution(a)
            inst_b = _line_has_institution(b)
            deg_a = _line_has_degree_token(a)
            deg_b = _line_has_degree_token(b)
            if (inst_a and deg_b and not deg_a) or (inst_b and deg_a and not deg_b):
                left, right = (a, b) if inst_a and deg_b else (b, a)
                left_n = re.sub(r"\s+", " ", left).strip()
                right_n = re.sub(r"\s+", " ", right).strip()
                merged = f"{left_n} — {right_n}"
                out.append(merged)
                i += 2
                continue
        out.append(a)
        i += 1
    return out


def _lines_after_heading(lines: list[str], header_re: re.Pattern, allowed_repeat_heads: frozenset[str]) -> list[str]:
    """Collect body lines after a section header until another major section starts."""
    out: list[str] = []
    for i, line in enumerate(lines):
        if not header_re.match(line):
            continue
        j = i + 1
        while j < len(lines):
            nxt = lines[j]
            sm = RE_SECTION_HEADING.match(nxt)
            if sm:
                h = sm.group("h").lower()
                if h not in allowed_repeat_heads:
                    break
            if len(nxt) > 500:
                break
            out.append(nxt)
            j += 1
            if len(out) >= 24:
                break
        break
    return out


def _finalize_education_joined(joined: str) -> str:
    """Last pass on the stored education string: cut skills tails and tidy trailing pipes."""
    if not joined:
        return joined
    s = _normalize_resume_inline_noise(joined)
    s = _truncate_education_at_skills_tail(s)
    # Glued "…| … | Technical Skills …" or "…2026 Technical Skills …" (any position)
    m = re.search(r"(?i)(?:\s*\|\s*)+\s*technical\s+skills\b|\btechnical\s+skills\s*(?:\||\s*●|\s*·)", s)
    if m:
        s = s[: m.start()].strip(" |—–-/")
    else:
        m2 = re.search(r"\btechnical\s+skills\b", s, re.I)
        if m2 and m2.start() > 12:
            tail = s[m2.start() :]
            if re.search(r"\b(javascript|typescript|python|react|programming|nestjs|tailwind)\b", tail, re.I):
                s = s[: m2.start()].strip(" |—–-/")
    s = re.sub(r"(\s*\|)+\s*$", "", s).strip(" |—–-/")
    return s


def extract_education(text: str) -> Dict:
    t_struct = preprocess_resume_text_for_structure(text)
    lines = [l.strip() for l in t_struct.splitlines() if l.strip()]
    section_lines = _lines_after_heading(
        lines,
        RE_EDU_HEADER,
        frozenset({"education", "academic", "qualifications"}),
    )
    edu_lines = [l for l in lines if RE_EDU_LINE.search(l)]
    merged: list[str] = []
    seen: set[str] = set()
    for l in section_lines + edu_lines:
        s = re.sub(r"\s+", " ", l).strip()
        s = _truncate_education_at_skills_tail(s)
        if not s or s in seen or len(s) > 480:
            continue
        seen.add(s)
        merged.append(s)
    merged = _merge_adjacent_education_lines(merged)
    merged = _refine_education_lines(merged)
    found = set()

    t = t_struct.lower()
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

    joined = " | ".join(merged[:12]) if merged else ""
    joined = _finalize_education_joined(joined)
    return {
        "highest_degree": highest,
        "education_lines": joined,
    }

# ---------- CERTIFICATIONS ----------
RE_CERT = re.compile(r"\b(certification|certified|certificate)\b", re.IGNORECASE)
RE_CERT_LINE = re.compile(r"^(.*\b(certification|certified|certificate)\b.*)$", re.IGNORECASE)

def extract_certifications(text: str) -> str:
    t_struct = preprocess_resume_text_for_structure(text)
    lines = [l.strip() for l in t_struct.splitlines() if l.strip()]
    section_lines = _lines_after_heading(
        lines,
        RE_CERT_HEADER,
        frozenset({"certifications", "certification"}),
    )
    cert_lines = [
        l
        for l in lines
        if RE_CERT_LINE.search(l)
        or RE_CERT_VENDOR_LINE.search(l)
        or _standalone_cert_candidate(l)
    ]
    merged: list[str] = []
    seen: set[str] = set()
    for l in section_lines + cert_lines:
        s = re.sub(r"\s+", " ", l).strip()
        if not s or s in seen or len(s) > 400:
            continue
        seen.add(s)
        merged.append(s)
    merged = _refine_certification_lines(merged)
    return " | ".join(merged[:14]) if merged else ""

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
# "years" or singular "year" (many CVs write "1 year experience").
RE_YEARS_PHRASE = re.compile(
    r"\b(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs|yr)\b(?:\s+of)?",
    re.IGNORECASE,
)
RE_YEARS_PHRASE_LEADING = re.compile(
    r"\b(?:over|more than|at least)\s+(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs|yr)\b",
    re.IGNORECASE,
)
# "X year(s) … experience" anywhere in the résumé (summary/profile when no Work Experience heading).
RE_YEARS_BEFORE_EXPERIENCE = re.compile(
    r"\b(\d{1,2}(?:\.\d)?)\s*\+?\s*years?\s+(?:of\s+)?(?:professional\s+|work\s+|relevant\s+)?experience\b",
    re.IGNORECASE,
)
RE_YEARS_AFTER_EXPERIENCE = re.compile(
    r"\b(?:with|having|including|plus|over|more than|at least)\s+(\d{1,2}(?:\.\d)?)\s*\+?\s*years?\b(?:\s+of)?\s+(?:professional\s+|work\s+|relevant\s+)?experience\b",
    re.IGNORECASE,
)
RE_EXPERIENCE_SPAN_YEARS = re.compile(
    r"\b(\d{1,2}(?:\.\d)?)\s*\+?\s*years?\s+(?:of\s+)?(?:hands[\s-]?on|industry|field|commercial|professional)\b",
    re.IGNORECASE,
)
# "Name has 2.5 years of experience in …" (common narrative under EXPERIENCE without date ranges).
RE_YEARS_HAS_EXPERIENCE = re.compile(
    r"\bhas\s+(\d{1,2}(?:\.\d)?)\s*\+?\s*years?\s+(?:of\s+)?(?:professional\s+|work\s+|relevant\s+)?experience\b",
    re.IGNORECASE,
)
# Explicit tenure phrases: do not apply education-window skip (otherwise EDUCATION below pulls in "University"
# and we drop valid "2.5 years of experience …" lines that lack engineer/developer tokens).
_PHRASE_PATTERNS_SKIP_EDU_GUARD: tuple[re.Pattern[str], ...] = (
    RE_YEARS_BEFORE_EXPERIENCE,
    RE_YEARS_AFTER_EXPERIENCE,
    RE_EXPERIENCE_SPAN_YEARS,
    RE_YEARS_HAS_EXPERIENCE,
)

RE_EDU_STRONG_NEAR_PHRASE = re.compile(
    r"\b(university|college|institute|school|academy|bachelor|master|ph\.?d|doctorate|"
    r"gpa|graduat(?:e|ion)|degree|diploma|coursework|thesis|dissertation)\b",
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
    r"executive|officer|head\s+of|partner|principal|owner|"
    r"operations|operational|support|reporting|vendor|procurement|logistics|administration|administrative|"
    r"\bops\b|sop|stakeholder|process)\b",
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
    r"(?<!\n)[\s\u00a0]+(?=(?:education|educational background|academic background|qualifications)\b)",
    re.IGNORECASE,
)
_BREAK_CERT = re.compile(
    r"(?<!\n)[\s\u00a0]+(?=(?:certifications?|professional certifications?|licenses?|credentials?)\b)",
    re.IGNORECASE,
)

RE_EDU_HEADER = re.compile(
    r"^\s*(?:[\u2022\u2023\u25CF\u25CB●○·*•\-]|\d{1,2}[.)]\s*)?\s*"
    r"(education|educational background|academic background|academic qualifications|qualifications)\b\s*:?\s*$",
    re.IGNORECASE,
)
RE_CERT_HEADER = re.compile(
    r"^\s*(?:[\u2022\u2023\u25CF\u25CB●○·*•\-]|\d{1,2}[.)]\s*)?\s*"
    r"(certifications?|professional certifications?|licenses?|credentials?)\b\s*:?\s*$",
    re.IGNORECASE,
)
# Lines that look like a named credential without the word "certificate"
RE_CERT_VENDOR_LINE = re.compile(
    r"\b(aws|azure|gcp|google cloud)\b.{0,80}\b(associate|professional|specialty|practitioner|foundations|expert|developer)\b",
    re.IGNORECASE,
)
RE_STANDALONE_NAMED_CERT = re.compile(
    r"\b("
    r"PMP|CAPM|PRINCE2|PSM\s*(?:I{1,3}|\d)|PSPO|CSM|CSPO|"
    r"CISSP|CISA|CISM|SSCP|CRISC|CEH|"
    r"CCNA|CCNP|CCIE|"
    r"CKA|CKS|CKAD|"
    r"RHCSA|RHCE|LFCS|"
    r"ITIL\s*(?:v?\d|Foundation|Practitioner)?|"
    r"CompTIA\s+(?:Security|Network|A)\+|"
    r"AWS\s+Certified|Google\s+Professional|Microsoft\s+Certified"
    r")\b",
    re.IGNORECASE,
)


def _standalone_cert_candidate(line: str) -> bool:
    if len(line) > 160 or len(line) < 2:
        return False
    if not RE_STANDALONE_NAMED_CERT.search(line):
        return False
    if _RE_CERT_LEAK.search(line) and len(line) > 50:
        return False
    if re.search(
        r"\b(engineer|developer|manager|director|analyst|scientist|architect|consultant)\b",
        line,
        re.I,
    ) and len(line) > 55:
        return False
    if re.search(r"\b(certified|certification|credential|exam|badge|license)\b", line, re.I):
        return True
    return len(line) <= 52


def preprocess_resume_text_for_structure(text: str) -> str:
    """Newlines + breaks before major sections (experience, education, certifications)."""
    t = _preprocess_resume_text_for_years(text)
    return _BREAK_CERT.sub("\n", t)


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


def _collect_explicit_year_phrases(text: str, *, radius: int = 120) -> list[float]:
    """
    Self-reported tenure phrases anywhere in the résumé (summary, profile, role bullets).
    Skips matches whose local context looks education-only (no job-title cues), to avoid
    counting "4 years at university" style lines.
    """
    low = (text or "").lower()
    scores: list[float] = []
    patterns = (
        RE_YEARS_PHRASE,
        RE_YEARS_PHRASE_LEADING,
        *_PHRASE_PATTERNS_SKIP_EDU_GUARD,
    )
    skip_edu = frozenset(_PHRASE_PATTERNS_SKIP_EDU_GUARD)
    seen: set[tuple[int, int]] = set()
    for pat in patterns:
        for m in pat.finditer(low):
            key = (m.start(), m.end())
            if key in seen:
                continue
            seen.add(key)
            if pat not in skip_edu:
                # Tighter window so a valid phrase in EXPERIENCE is not vetoed by EDUCATION further down.
                lo = max(0, m.start() - 70)
                hi = min(len(low), m.end() + 35)
                win = low[lo:hi]
                tail = low[m.end() : min(len(low), m.end() + 28)]
                if RE_EDU_STRONG_NEAR_PHRASE.search(win) and not RE_WORK_HINT.search(win):
                    if "experience" not in tail:
                        continue
            try:
                y = float(m.group(1))
            except (TypeError, ValueError, IndexError):
                continue
            if 0 < y <= 40:
                scores.append(y)
    return scores


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

    # 1) Explicit "X year(s) …" phrases anywhere (summary/profile/body), then max (cap 40).
    years_phr = _collect_explicit_year_phrases(text)
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

    # If there is no explicit Experience heading, still try lines that combine date ranges with
    # employment-ish cues (many résumés omit the section title but list roles with dates).
    if not exp_lines and not saw_exp_header:
        workish_lines: list[str] = []
        for ln in lines:
            if not ln or len(ln) < 8:
                continue
            if not _line_has_range(ln):
                continue
            if RE_EDU_HINT.search(ln) and not RE_WORK_HINT.search(ln):
                continue
            if not RE_WORK_HINT.search(ln):
                continue
            workish_lines.append(ln)
        if workish_lines:
            t_fb = "\n".join(workish_lines).lower()
            total_fb = _sum_ranges_in_text(t_fb, current_year)
            if total_fb > 0:
                return round(min(total_fb, 40.0), 1)
        total_lr = _sum_ranges_last_resort(text, current_year, require_work_hint=True)
        if total_lr > 0:
            return round(min(total_lr, 40.0), 1)
        years_fb = _collect_explicit_year_phrases(text)
        if years_fb:
            return round(min(max(years_fb), 40.0), 1)
        return 0.0

    t = "\n".join(exp_lines).lower()
    total = _sum_ranges_in_text(t, current_year)

    if total <= 0:
        # If we had an experience header but couldn't parse ranges from the section text,
        # try last-resort matching within the whole text but require work hint.
        total = _sum_ranges_last_resort(text, current_year, require_work_hint=True)

    if total <= 0:
        years_fb = _collect_explicit_year_phrases(text)
        if years_fb:
            return round(min(max(years_fb), 40.0), 1)

    return round(min(total, 40.0), 1)
