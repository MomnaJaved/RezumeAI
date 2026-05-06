from __future__ import annotations

import re
from dataclasses import dataclass

from src.matching.weak_score import clean_skill_fragment


_SPLIT = re.compile(r"[,\n;/|]+")
_WORD = re.compile(r"[a-z0-9][a-z0-9+\-#.]*")
_STOP = {"and", "or", "with", "to", "in", "of", "the", "a", "an", "for", "on", "api", "apis"}


# Common aliases across the engineering / ML stacks. Each entry lists all
# acceptable surface forms for ONE underlying skill. Recruiters and
# candidates spell these a dozen different ways ("TensorFlow" vs "Tensor
# Flow" vs "TF"; "scikit-learn" vs "sklearn"; "RAG" vs "retrieval-augmented
# generation") and we must treat them as equivalent, otherwise the skills
# overlap filter rejects obviously-matching candidates purely on spelling.
_ALIAS_GROUPS: list[set[str]] = [
    {"tensorflow", "tensor flow", "tf"},
    {"pytorch", "torch"},
    {"scikit-learn", "scikit learn", "scikitlearn", "sklearn"},
    {"machine learning", "machinelearning", "ml"},
    {"deep learning", "deeplearning", "dl"},
    {"artificial intelligence", "artificialintelligence", "ai"},
    {"natural language processing", "nlp"},
    {"computer vision", "cv"},
    {"retrieval-augmented generation", "retrieval augmented generation", "retrievalaugmentedgeneration", "rag"},
    {"large language model", "large language models", "llm", "llms"},
    {"model context protocol", "model context protocols", "mcp"},
    {"javascript", "js"},
    {"typescript", "ts"},
    {"kubernetes", "k8s"},
    {"postgresql", "postgres"},
    {"amazon web services", "aws"},
    {"google cloud platform", "google cloud", "gcp"},
    {"microsoft azure", "azure"},
    {"continuous integration", "ci"},
    {"continuous deployment", "cd"},
    {"ci/cd", "cicd", "continuous integration continuous deployment"},
]


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _variants_for_phrase(phrase: str) -> set[str]:
    """
    All acceptable surface forms of a single skill phrase.

    Starts with the phrase itself plus its space-free / dash-normalised forms,
    then unions in any alias group the phrase participates in. Returning a
    set per phrase lets callers ask "did the candidate mention any flavour
    of THIS skill?" without conflating unrelated skills.
    """
    t = _norm(phrase)
    if not t:
        return set()
    base = {
        t,
        t.replace(" ", ""),
        t.replace("-", " "),
        t.replace("-", ""),
        t.replace("_", " "),
        t.replace("_", ""),
    }
    for group in _ALIAS_GROUPS:
        if base & group:
            base |= group
    return {x for x in base if x}


def skills_set(raw: str) -> set[str]:
    """
    Back-compat: flat bag of skill surface forms plus tokens. Retained so any
    external caller keeps working; the ratio calculation below no longer
    relies on it.
    """
    _, bag = skills_canonical_and_bag(raw)
    return bag


def skills_canonical_and_bag(raw: str) -> tuple[list[set[str]], set[str]]:
    """
    Parse a raw skills string into two views:

    * ``canonical``: one entry per distinct skill phrase in the input. Each
      entry is the full set of surface forms (original, compact, dash/space
      normalised, alias-expanded) that should be considered equivalent.
      Used as the *denominator* for overlap — i.e. "of the N distinct skills
      the job listed, how many did the candidate mention (in any spelling)?".
    * ``bag``: every variant across all phrases, unioned with token-level
      entries (so "feature engineering" also matches a candidate who just
      says "engineering"). Used as the *haystack* on the candidate side.
    """
    canonical: list[set[str]] = []
    bag: set[str] = set()
    for chunk in _SPLIT.split(raw or ""):
        cleaned = clean_skill_fragment(chunk)
        if not cleaned:
            continue
        t = _norm(cleaned)
        if not t or t in {"none", "n/a", "na", "null", "-", "—"}:
            continue
        t = " ".join(t.split())
        variants = _variants_for_phrase(t)
        if not variants:
            continue
        canonical.append(variants)
        bag |= variants
        for w in _WORD.findall(t):
            if w in _STOP or len(w) < 2:
                continue
            bag.add(w)
    return canonical, bag


def skills_overlap_ratio(job_skills: set[str], cand_skills: set[str]) -> float:
    """
    Legacy flat-set overlap. Kept for callers that haven't migrated to the
    canonical/bag pair. Prefer :func:`skills_overlap_ratio_canonical`.
    """
    if not job_skills:
        return 0.0
    inter = job_skills.intersection(cand_skills)
    return float(len(inter)) / float(max(1, len(job_skills)))


def skills_overlap_ratio_canonical(job_canonical: list[set[str]], cand_bag: set[str]) -> float:
    """
    Fraction of distinct job skills for which ANY alias/variant appears in the
    candidate's bag. This is the correct denominator semantically: the old
    flat-set ratio inflated the denominator with token-level entries (e.g.
    "artificial intelligence" contributed 3 bag entries), making short job
    skill lists fail the threshold even when the candidate matched 2–3 of
    them outright.
    """
    if not job_canonical:
        return 0.0
    matched = sum(1 for variants in job_canonical if variants & cand_bag)
    return float(matched) / float(len(job_canonical))


def _keywords(text: str) -> set[str]:
    t = _norm(text)
    return {m.group(0) for m in _WORD.finditer(t)}


@dataclass(frozen=True)
class RoleBucket:
    key: str


def role_bucket_for_job_title(job_title: str) -> RoleBucket:
    t = _norm(job_title)
    # Minimal ATS buckets (extend safely later). ML/AI is checked before the
    # generic backend/"engineer" buckets so an "AI and Machine Learning
    # Engineer" posting isn't miscategorised and then rejected by the stricter
    # backend allow-list.
    if any(k in t for k in ["machine learning", "deep learning", "artificial intelligence", " ai ", " ml ", "ai/ml", "ml/ai", "nlp", "data scientist", "computer vision"]) or t.startswith("ai ") or t.startswith("ml ") or t.endswith(" ai") or t.endswith(" ml"):
        return RoleBucket("ml")
    if any(k in t for k in ["ui", "ux", "designer", "product designer", "visual", "graphics", "graphic"]):
        return RoleBucket("design")
    if any(k in t for k in ["frontend", "front-end", "react", "web"]):
        return RoleBucket("frontend")
    if any(k in t for k in ["backend", "back-end", "api", "server"]):
        return RoleBucket("backend")
    if any(k in t for k in ["fullstack", "full-stack"]):
        return RoleBucket("fullstack")
    if any(k in t for k in ["devops", "sre", "site reliability", "kubernetes"]):
        return RoleBucket("devops")
    if any(k in t for k in ["qa", "quality", "tester", "testing"]):
        return RoleBucket("qa")
    if any(k in t for k in ["data", "analyst", "bi", "warehouse"]):
        return RoleBucket("data")
    if any(k in t for k in ["finance", "account", "accounting"]):
        return RoleBucket("finance")
    if any(k in t for k in ["hr", "recruit", "talent"]):
        return RoleBucket("hr")
    if any(k in t for k in ["operations", "ops", "admin"]):
        return RoleBucket("ops")
    return RoleBucket("other")


def candidate_matches_role(job_bucket: RoleBucket, candidate_title: str, candidate_role_label: str) -> bool:
    """
    Hard reject obviously irrelevant roles (backend vs UX, etc).
    Conservative: if job bucket is 'other', allow all.
    """
    if job_bucket.key == "other":
        return True
    hay = " ".join([_norm(candidate_title), _norm(candidate_role_label)])
    if not hay.strip():
        return True

    # Allow lists per bucket (very small heuristic set). ML candidates often
    # show up with generic titles ("Software Engineer", "Associate Engineer")
    # but ML skills in their resume — we're lenient on the title and let the
    # skills-overlap filter carry most of the rejection weight for this bucket.
    allow = {
        "design": ["ui", "ux", "designer", "product designer", "visual", "graphic", "graphics"],
        "frontend": ["frontend", "front-end", "react", "web", "ui"],
        "backend": ["backend", "back-end", "api", "server"],
        "fullstack": ["fullstack", "full-stack", "frontend", "backend"],
        "devops": ["devops", "sre", "kubernetes", "docker", "cloud"],
        "qa": ["qa", "tester", "testing", "quality"],
        "data": ["data", "analyst", "bi", "warehouse", "scientist", "ml", "ai"],
        "ml": ["ml", "ai", "machine", "deep", "data", "scientist", "research", "engineer", "developer", "software", "nlp", "vision"],
        "finance": ["finance", "account", "accounting"],
        "hr": ["hr", "recruit", "talent"],
        "ops": ["operations", "ops", "admin"],
    }.get(job_bucket.key, [])

    reject = {
        "design": ["backend", "devops", "qa", "account", "finance", "hr"],
        "frontend": ["devops", "qa", "account", "finance", "hr"],
        "backend": ["designer", "ux", "ui designer", "graphic", "qa"],
        "devops": ["designer", "ux", "ui", "frontend", "qa"],
        "ml": ["designer", "ux", "ui designer", "graphic", "account", "finance", "hr", "recruit"],
    }.get(job_bucket.key, [])

    if any(r in hay for r in reject):
        return False
    return any(a in hay for a in allow) if allow else True


def title_keyword_match(job_title: str, cand_title: str, cand_role_label: str = "") -> bool:
    """
    Light title keyword check. Helps disallow unrelated jobs after SBERT
    retrieval. The candidate side considers both the resume title AND the
    recruiter-facing role label, because many candidates have a generic
    resume title ("Associate Software Engineer") while their actual
    specialisation ("Backend", "ML Engineer", "Data Scientist") lives in
    the role label we extracted at ingestion time.
    """
    jt = _norm(job_title)
    if not jt or jt in ("home", "unknown", "job", "role"):
        return True
    jw = _keywords(job_title)
    cw = _keywords(cand_title) | _keywords(cand_role_label)
    if not jw or not cw:
        return True
    # Ignore very generic words
    stop = {"engineer", "developer", "specialist", "manager", "senior", "junior", "lead", "intern", "associate", "principal", "staff"}
    jw2 = {w for w in jw if w not in stop}
    cw2 = {w for w in cw if w not in stop}
    if not jw2 or not cw2:
        return True
    return len(jw2.intersection(cw2)) > 0


@dataclass(frozen=True)
class FilterDecision:
    passed: bool
    skills_overlap: float


def passes_filters(
    *,
    sbert_score: float,
    job_title: str,
    job_skills_raw: str,
    cand_title: str,
    cand_role_label: str,
    cand_skills_raw: str,
    sbert_threshold: float,
    skills_overlap_threshold: float,
) -> FilterDecision:
    if sbert_score < float(sbert_threshold):
        return FilterDecision(False, 0.0)

    # Canonical/bag overlap: one denominator entry per distinct job skill,
    # numerator counts how many of them the candidate mentioned in ANY
    # spelling (aliases included). This is the correct semantic ratio; the
    # old flat-set version over-counted the denominator with token-level
    # entries and treated "TensorFlow" and "Tensor Flow" as different skills.
    job_canonical, _ = skills_canonical_and_bag(job_skills_raw)
    _, cand_bag = skills_canonical_and_bag(cand_skills_raw)
    ov = skills_overlap_ratio_canonical(job_canonical, cand_bag) if job_canonical else 0.0
    if job_canonical and ov < float(skills_overlap_threshold):
        return FilterDecision(False, ov)

    bucket = role_bucket_for_job_title(job_title)
    if not candidate_matches_role(bucket, cand_title, cand_role_label):
        return FilterDecision(False, ov)

    # Title keyword check is only a sanity guard on top of the skills check.
    # Skip it when (a) the job bucket is "other" (we couldn't classify the
    # role, so we have no prior about what titles are relevant) or (b) the
    # skills overlap is strong (≥ 1.5× the required threshold), because at
    # that point the skills alone tell us the candidate is relevant even if
    # their resume title is generic. Without this relaxation, an
    # "AI and Machine Learning Engineer" job would reject any candidate
    # whose resume says "Software Engineer" even with perfect skills overlap.
    strong_skills = job_canonical and ov >= float(skills_overlap_threshold) * 1.5
    if bucket.key != "other" and not strong_skills:
        if not title_keyword_match(job_title, cand_title, cand_role_label):
            return FilterDecision(False, ov)

    return FilterDecision(True, ov)

