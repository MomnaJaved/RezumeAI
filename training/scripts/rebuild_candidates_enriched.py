from __future__ import annotations

import sys
from pathlib import Path
import re

import pandas as pd
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.parsing.skill_mining import build_global_vocab, skills_for_resume
from src.parsing.feature_extractors import (
    extract_education,
    extract_certifications,
    estimate_years_experience,
)

CAND_PATH = "outputs/parsing/candidates.csv"
OUT_PATH = "outputs/parsing/candidates_enriched.csv"
VOCAB_PATH = "outputs/parsing/skills_vocab.csv"

# ----------------------------
# Cleaning utilities
# ----------------------------
BULLET_CHARS = r"[\u2022\u2023\u25E6\u2043\u2219\u00B7\u25CF\u25AA\u25AB\u25A0\u25A1\uF0B7\uF0A7\uF0D8\uF0FC\uFEFF]"
RE_BULLETS = re.compile(BULLET_CHARS)
RE_JUNK_PIPES = re.compile(r"[|]+")
RE_CTRL = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")  # control chars (keeps \n as we normalize)
RE_MULTI_SPACE = re.compile(r"[ \t]+")


def _basic_symbol_cleanup(s: str) -> str:
    """Remove bullets/pipes/control chars but do NOT collapse newlines."""
    if not isinstance(s, str):
        return ""

    # normalize newlines
    s = s.replace("\r\n", "\n").replace("\r", "\n")

    # remove control chars except newline
    s = RE_CTRL.sub(" ", s)

    # remove bullet glyphs
    s = RE_BULLETS.sub(" ", s)
    s = s.replace("•", " ").replace("", " ").replace("·", " ")

    # remove pipes
    s = RE_JUNK_PIPES.sub(" ", s)

    # remove dash bullets at start of lines
    s = re.sub(r"(?m)^\s*[-–—]+\s*", "", s)

    # tidy spaces but keep newlines
    s = RE_MULTI_SPACE.sub(" ", s)

    # trim each line
    s = "\n".join([ln.strip() for ln in s.splitlines()])

    # remove repeated blank lines
    s = re.sub(r"\n{3,}", "\n\n", s).strip()

    return s


def clean_text_keep_lines(s: str) -> str:
    """Clean text for extractors while preserving line structure."""
    return _basic_symbol_cleanup(s)


def clean_text_flat(s: str) -> str:
    """Clean text for CSV display: collapse to a single neat line."""
    s = _basic_symbol_cleanup(s)
    s = re.sub(r"\s*\n\s*", " ", s)  # collapse newlines now
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s


# ----------------------------
# Strict field cleanup (title/education/certs)
# ----------------------------
RE_TITLE_CUTOFF = re.compile(
    r"\b(with|having|possessing|strong understanding|strong knowledge|good understanding|"
    r"experienced in|experience in|proficient in|expert in|skilled in|"
    r"responsible for|specializing in|specialised in|specialized in|"
    r"focused on|focus on|working on)\b",
    re.IGNORECASE,
)
RE_TITLE_GARBAGE = re.compile(r"(objective|summary|profile|curriculum vitae|resume|cv)$", re.IGNORECASE)


def clean_title_strict(title: str) -> str:
    """
    Make title strict:
      'Software Quality Assurance Engineer with a strong understanding of ...'
        -> 'software quality assurance engineer'
    """
    t = clean_text_flat(title).lower()
    if not t:
        return ""

    m = RE_TITLE_CUTOFF.search(t)
    if m:
        t = t[: m.start()].strip(" ,;-:")

    t = RE_TITLE_GARBAGE.sub("", t).strip(" ,;-:")

    # keep reasonable length
    if len(t) > 80:
        t = t[:80].rsplit(" ", 1)[0]

    return t


RE_EDU_STOP = re.compile(
    r"\b(project|thesis|final year project|fyp|capstone|e-portal|portal|developed|designed|built|"
    r"platform|communication|purpose|for the purpose|responsible|worked on)\b",
    re.IGNORECASE,
)


def clean_education_strict(edu_lines: str) -> str:
    """
    Keep only institution/campus line. Remove project/story text.
    Example:
      'Comsats University Islamabad, Sahiwal Campus E-Portal for Alumni...'
        -> 'Comsats University Islamabad, Sahiwal Campus'
    """
    if not isinstance(edu_lines, str) or not edu_lines.strip():
        return ""

    lines = clean_text_keep_lines(edu_lines).splitlines()
    first = lines[0].strip() if lines else ""
    first = clean_text_flat(first)
    if not first:
        return ""

    m = RE_EDU_STOP.search(first)
    if m:
        first = first[: m.start()].strip(" ,;-:")

    # cut at obvious sentence continuation
    first = re.split(r"\.\s+|:\s+", first)[0].strip(" ,;-:")

    return first


CERT_CANON = {
    "aws certified developer - associate": "aws certified developer associate",
    "aws certified developer associate": "aws certified developer associate",
    "aws developer associate": "aws certified developer associate",
    "aws certification": "aws certification",

    "aws certified solutions architect - associate": "aws certified solutions architect associate",
    "aws certified solutions architect associate": "aws certified solutions architect associate",
    "aws solutions architect associate": "aws certified solutions architect associate",

    "aws certified cloud practitioner": "aws certified cloud practitioner",

    # not a cert name by itself
    "devops engineer": "",
}

RE_CERT_SPLIT = re.compile(r"[,\u2022\|\;/]+|\s{2,}")
RE_CERT_NOISE = re.compile(
    r"\b(developed|designed|built|implemented|worked on|project|interface|bootstrap|ajax|json|jquery|html|css|php|"
    r"experience|years|overall|strong understanding|responsible)\b",
    re.IGNORECASE,
)


def clean_certifications_strict(cert_text: str) -> str:
    """
    Keep only cert names; remove project/stack sentences.
    Example:
      'Certified AWS Developer Associate ... Developed UI ... AWS Certified Developer - Associate'
        -> 'aws certified developer associate'
    """
    if not isinstance(cert_text, str) or not cert_text.strip():
        return ""

    raw = clean_text_keep_lines(cert_text).replace("\n", ", ")
    parts = [clean_text_flat(p).lower() for p in RE_CERT_SPLIT.split(raw)]

    cleaned = []
    for p in parts:
        if not p:
            continue

        # drop project/stack lines unless clearly cert-like
        if RE_CERT_NOISE.search(p) and ("certified" not in p and "certification" not in p and "certificate" not in p):
            continue

        p2 = CERT_CANON.get(p, p)
        if not p2:
            continue

        # keep only cert-like phrases
        if ("certified" in p2) or ("certification" in p2) or ("certificate" in p2) or p2.startswith("aws "):
            cleaned.append(p2)

    # unique preserve order
    seen = set()
    final = []
    for x in cleaned:
        if x not in seen:
            seen.add(x)
            final.append(x)

    return ", ".join(final)


# ----------------------------
# Title extraction (base) + strict cleanup applied later
# ----------------------------
TITLE_HINTS = [
    # Engineering
    "software quality assurance engineer", "qa engineer", "sqa engineer", "test engineer",
    "software engineer", "software developer", "backend developer", "frontend developer", "full stack developer",
    "mobile developer", "android developer", "ios developer",
    "data scientist", "data analyst", "data engineer", "machine learning engineer",
    "devops engineer", "cloud engineer",

    # Product
    "product manager", "product owner", "business analyst",

    # Design
    "ui/ux designer", "ux designer", "ui designer", "graphic designer", "product designer",

    # Business / Marketing / Sales
    "digital marketing", "marketing manager", "seo specialist", "business development", "sales executive",
    "sales manager", "account executive",

    # HR / Finance / Ops
    "hr officer", "hr manager", "recruiter", "talent acquisition",
    "accountant", "financial analyst",
    "operations manager", "operations executive",
]

RE_TITLE_LINE_NOISE = re.compile(r"(email|phone|address|linkedin|github|portfolio|www\.|http)", re.IGNORECASE)


def extract_title_from_text(raw_text_with_lines: str) -> str:
    if not isinstance(raw_text_with_lines, str) or not raw_text_with_lines.strip():
        return ""

    t = clean_text_keep_lines(raw_text_with_lines)
    top = "\n".join(t.splitlines()[:35])
    top_lc = clean_text_flat(top).lower()

    for hint in TITLE_HINTS:
        if hint in top_lc:
            return hint

    role_words = [
        "quality assurance", "qa", "sqa",
        "engineer", "developer", "designer", "analyst", "manager", "specialist", "consultant",
        "officer", "executive", "lead", "intern", "associate", "architect", "accountant",
    ]

    for line in top.splitlines()[:25]:
        l = clean_text_flat(line)
        if not l or len(l) < 6 or len(l) > 90:
            continue
        if RE_TITLE_LINE_NOISE.search(l):
            continue
        lc = l.lower()
        if lc in {"experience", "education", "skills", "projects", "profile", "summary", "certifications"}:
            continue
        if any(w in lc for w in role_words):
            return lc

    return ""


# ----------------------------
# Main
# ----------------------------
def main():
    df = pd.read_csv(CAND_PATH)
    df["raw_text"] = df["raw_text"].fillna("").astype(str)

    raw_orig = df["raw_text"].tolist()

    # Keep line structure for extractors
    texts_for_extractors = [clean_text_keep_lines(t) for t in raw_orig]

    # Flat version for CSV raw_text
    texts_for_csv = [clean_text_flat(t) for t in raw_orig]

    print("Building vocab...")
    vocab_counter = build_global_vocab(texts_for_extractors, min_freq=12, top_k=4000)
    vocab = set(vocab_counter.keys())

    print("Extracting title + skills + education + certifications + experience...")

    titles = []
    skills_col = []
    highest_deg = []
    edu_lines = []
    certs = []
    years = []

    for t_lines in tqdm(texts_for_extractors):
        # Title: extract then strict-clean
        titles.append(clean_title_strict(extract_title_from_text(t_lines)))

        # Skills
        skills_col.append(", ".join(skills_for_resume(t_lines, vocab)))

        # Education
        edu = extract_education(t_lines)
        highest_deg.append(clean_text_flat(edu.get("highest_degree", "")))
        edu_lines.append(clean_education_strict(edu.get("education_lines", "")))

        # Certifications
        certs.append(clean_certifications_strict(extract_certifications(t_lines)))

        # Experience estimate
        years.append(estimate_years_experience(t_lines, current_year=2026))

    df["raw_text"] = texts_for_csv
    df["title"] = titles
    df["skills"] = [clean_text_flat(x).replace(" ,", ",").replace(", ", ", ").strip() for x in skills_col]
    df["highest_degree"] = highest_deg
    df["education_lines"] = edu_lines
    df["certifications"] = certs
    df["years_experience_est"] = years

    # Clean other optional columns if they exist
    for col in ["summary", "experience_text"]:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).apply(clean_text_flat)

    df.to_csv(OUT_PATH, index=False)

    vocab_df = pd.DataFrame([{"skill": k, "doc_freq": v} for k, v in vocab_counter.most_common()])
    vocab_df.to_csv(VOCAB_PATH, index=False)

    print("✅ Written:")
    print(" -", OUT_PATH)
    print(" -", VOCAB_PATH)
    print("Top 25 skills:", ", ".join(vocab_df.head(25)["skill"].tolist()))


if __name__ == "__main__":
    main()
