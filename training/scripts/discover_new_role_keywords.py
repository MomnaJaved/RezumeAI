from __future__ import annotations

import re
from collections import Counter
import pandas as pd

CAND_PATH = "outputs/parsing/candidates_enriched.csv"
OUT_PATH = "outputs/reports/unknown_title_phrase_candidates.csv"

# basic cleaning
RE_MULTI_SPACE = re.compile(r"\s+")
RE_NON_WORD = re.compile(r"[^a-z0-9\s\-\+\.\/]", re.IGNORECASE)

STOPWORDS = {
    "and","or","the","a","an","to","of","in","for","with","on","at","from","by","as",
    "is","are","was","were","be","been","being","this","that","these","those",
    "experience","education","skills","projects","project","profile","summary","contact",
    "lahore","pakistan","karachi","islamabad","university","college","school",
    "cid","said","know","eyes","dad","head","then","but","what","you","she","his"
}


# phrases that are usually noise in resumes
NOISE_SUBSTR = [
    "gmail", "linkedin", "github", "phone", "address", "road", "colony", "thank you"
]

def clean_text(t: str) -> str:
    t = (t or "").lower()
    t = RE_NON_WORD.sub(" ", t)
    t = RE_MULTI_SPACE.sub(" ", t).strip()
    return t

def extract_ngrams(text: str, n: int) -> list[str]:
    words = [w for w in text.split() if w not in STOPWORDS and len(w) > 2]
    out = []

    for i in range(len(words) - n + 1):
        ng = " ".join(words[i:i+n])

        # reject if contains any noise substrings
        if any(x in ng for x in NOISE_SUBSTR):
            continue

        # reject if contains digits
        if any(char.isdigit() for char in ng):
            continue

        # reject narrative-ish phrases
        if any(w in ng.split() for w in {"said","know","eyes","dad","head","then","but","she","his"}):
            continue

        # reject repeated same word: "cid cid"
        parts = ng.split()
        if len(set(parts)) == 1:
            continue

        out.append(ng)

    return out

def main():
    df = pd.read_csv(CAND_PATH).fillna("")
    # focus only unknown titles
    u = df[df["title"].astype(str).str.lower().str.strip() == "unknown"].copy()
    print("Unknown candidates:", len(u))

    c2 = Counter()
    c3 = Counter()

    for raw in u["raw_text"].astype(str).tolist():
        top = "\n".join(raw.splitlines()[:120])  # focus on header area
        top = clean_text(top)
        c2.update(extract_ngrams(top, 2))
        c3.update(extract_ngrams(top, 3))

    rows = []
    for phrase, freq in c3.most_common(400):
        rows.append({"phrase": phrase, "n": 3, "freq": freq})
    for phrase, freq in c2.most_common(600):
        rows.append({"phrase": phrase, "n": 2, "freq": freq})

    out = pd.DataFrame(rows).drop_duplicates(subset=["phrase"]).sort_values(["freq","n"], ascending=False)
    out.to_csv(OUT_PATH, index=False)
    print("✅ Written:", OUT_PATH)
    print(out.head(25).to_string(index=False))

if __name__ == "__main__":
    main()
