from __future__ import annotations

import re
from collections import Counter
from typing import List, Set

from src.parsing.skill_taxonomy import (
    CANON as TAX_CANON,
    PHRASES as TAX_PHRASES,
    DOMAIN_KEYWORDS,
)

# --------- REMOVE URLS / DOMAINS ----------
RE_URL = re.compile(r"(https?://\S+|www\.\S+)", re.IGNORECASE)
RE_DOMAIN = re.compile(r"\b[a-z0-9\-]+\.(com|net|org|io|edu|pk|ai|co|ltd)\b", re.IGNORECASE)

BRAND_BLACKLIST = {
    "deeplearning.ai", "coursera", "udemy", "edx", "kaggle",
    "linkedin.com", "github.com", "gmail.com", "yahoo.com", "hotmail.com",
    "gmail.co", "pvt.ltd"
}

# --------- SECTION HEADERS (HIGH PRECISION) ----------
SECTION_HEADERS = [
    "skills","technical skills","core skills","technologies","tools","tech stack",
    "programming","languages","frameworks","libraries","databases",
    "devops","cloud","ci/cd","certifications",
    "testing","qa",
    "backend","frontend",
    "hr", "human resources", "recruitment", "talent acquisition",
    "certifications", "professional summary",
    "design", "ui/ux", "ux", "ui",
    "tools", "design tools",
    "creative skills", "software",
    "data science", "machine learning", "ml", "deep learning",
    "research", "analytics", "data engineering",
    "marketing", "digital marketing", "sales", "business development",
    "business", "business & marketing", "sales & marketing",
    "tools", "platforms",
    "finance", "accounting", "financial", "financial skills",
    "accounts", "tax", "audit",
    "qa", "sqa", "testing", "test automation", "quality assurance",
    "product", "product management", "product owner",
    "business analysis", "business analyst",
    "requirements", "responsibilities",
    "operations", "business operations", "ops", "operational",
    "process", "compliance", "procurement", "vendor",

]

RE_SECTION_LINE = re.compile(
    r"^\s*(" + "|".join([re.escape(h) for h in SECTION_HEADERS]) + r")\s*:\s*(.+)$",
    re.IGNORECASE,
)

# Split skill lists
RE_SPLIT = re.compile(r"[,\u2022\|\;/]+|\s{2,}")

# Lines that look like a compact skills list (space-separated)
RE_SKILLS_HEAVY_LINE = re.compile(
    r"""^(?=.*\b(
        python|java|javascript|typescript|sql|html|css|php|node|react|docker|aws|azure|gcp|kubernetes|c\+\+|c#|\.net|
        hr|human resources|recruitment|talent|onboarding|payroll|workday|hris|ats|employee|
        figma|sketch|photoshop|illustrator|indesign|after effects|premiere|adobe|ui/ux|wireframing|prototyping|branding|typography|
        pandas|numpy|scikit|sklearn|tensorflow|pytorch|spark|airflow|kafka|bigquery|etl|data science|machine learning|ml|
        seo|marketing|sales|business development|lead generation|crm|salesforce|hubspot|zoho|pipedrive|
        google analytics|google ads|meta ads|mailchimp|linkedin|
        finance|accounting|audit|tax|ifrs|gaap|fp&a|budgeting|forecasting|quickbooks|xero|tally|sap|netsuite|ledger|reconciliation|
        qa|testing|selenium|cypress|playwright|appium|postman|soapui|jira|testrail|zephyr|jmeter|k6|browserstack|
        product|roadmap|user stories|backlog|scrum|agile|kanban|requirements|stakeholder|prd|mvp|
        operations|ops|process|sop|compliance|vendor|procurement|inventory|logistics|service delivery|dashboard|reporting
    )\b).{8,}$""",
    re.IGNORECASE | re.VERBOSE
)

# Tokenize space-separated skills
RE_SPACE_SKILL_TOKENS = re.compile(r"[A-Za-z][A-Za-z0-9\+\#\.]{1,}(?:\.[A-Za-z0-9]+)?")

# --------- PHRASES (multi-word skills) ----------
# Use taxonomy phrases + a small local set for software signals you already rely on
LOCAL_PHRASES = [
    "github actions",
    "power bi",
    "hugging face",
    "ms excel",
    "microsoft excel",
    "visual basic for excel",
    "linux shell",
    "natural language processing",
]

PHRASES = sorted(set([p.lower() for p in (TAX_PHRASES + LOCAL_PHRASES)]))
RE_PHRASES = re.compile(r"\b(" + "|".join([re.escape(p) for p in PHRASES]) + r")\b", re.IGNORECASE)

# --------- TECH TOKENS ----------
RE_TECH = re.compile(
    r"""
    (?:
        [a-z]{2,}\.[a-z0-9\.]{1,}                 # node.js, next.js, express.js
        |
        c\+\+|c#|f#|\.net
        |
        (?:s3|ec2|eks|ecs|ecr|lambda|route53)     # AWS services
        |
        [a-z]{3,}(?:\-[a-z0-9]{2,})+              # hyphenated tool-like tokens
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

CORE_TOOLS = {
    # ---------- Software Developers ----------
    # Languages
    "python","java","javascript","typescript","go","c++","c#",".net","php","ruby","swift","kotlin","scala","rust",
    "bash","powershell",

    # Web fundamentals
    "html","html5","css","css3","sass","scss","tailwind css","bootstrap",

    # Frontend
    "react","next.js","vue.js","nuxt.js","angular","svelte","react native",
    "material-ui","styled components","redux","redux toolkit","redux saga",

    # Backend
    "node.js","express.js","nest.js","django","flask","fastapi","spring","laravel","rails","asp.net",

    # APIs & protocols
    "rest api","graphql api","grpc","websockets","openapi","oauth2","jwt",

    # Databases
    "sql","mysql","postgresql","mongodb","redis","mssql","sqlite","cassandra","dynamodb","neo4j",

    # DevOps / Cloud
    "docker","docker compose","kubernetes","terraform","ansible",
    "jenkins","github actions","gitlab ci","ci/cd",
    "aws","azure","gcp",
    "ec2","s3","lambda","ecs","eks","ecr","rds","cloudfront","route53",

    # Observability
    "prometheus","grafana","elk","opensearch",

    # Testing
    "pytest","junit","jest","mocha","chai",
    "selenium","cypress","playwright","postman",
    "unit tests","integration tests","e2e tests","api testing",
    "test driven development","tdd","bdd",

    # ---------- HR ----------
    # HR tools / systems
    "ats","hris","workday","bamboohr","zoho recruit","lever","greenhouse",
    "successfactors","oracle hcm","adp","gusto",

    # HR functional skills (phrases are detected; these help when they appear as tokens)
    "recruitment","onboarding","offboarding","payroll","hr analytics","employee relations",
    "employee engagement","performance management","compensation and benefits",
    "training and development","learning and development",

    # ---------- Designers ----------
    # Design tools / skills
    "figma","sketch","invision","zeplin","framer","protopie",
    "adobe photoshop","adobe illustrator","adobe indesign","adobe after effects","adobe premiere","adobe xd",
    "canva","coreldraw","blender",
    "ui/ux","ui","ux","wireframing","prototyping","design systems",
    "graphic design","visual design","branding","typography","logo design",
    "motion graphics","video editing","photo editing",

    # ---------- Data Scintists ----------
    # Data science / engineering tools + concepts
    "machine learning","deep learning","feature engineering","exploratory data analysis",
    "statistical analysis","data preprocessing","data cleaning","model evaluation",
    "hyperparameter tuning","time series","ab testing",
    "numpy","pandas","scikit-learn","tensorflow","pytorch",
    "spark","hadoop","airflow","kafka",
    "etl pipeline","data pipeline","data warehousing",
    "bigquery",
    
    # ---------- Marketing / Sales / BD tools + skills ----------
    "seo","digital marketing","google analytics","google ads","meta ads",
    "email marketing","content marketing","social media marketing","social media management",
    "keyword research","link building","guest posting",
    "conversion rate optimization","cro","marketing automation",

    "business development","sales development","lead generation","prospecting",
    "cold calling","cold emailing","sales pipeline","account management",
    "customer success","deal negotiation","proposal writing","sales forecasting",
    "market research","competitive analysis",

    "crm","salesforce","hubspot","zoho crm","pipedrive",
    "mailchimp","sendgrid","google tag manager","google search console",
    "linkedin sales navigator","meta business suite",

    # ---------- Finance ----------
    # Finance / Accounting
    "accounting","financial reporting","budgeting","forecasting","financial modeling",
    "variance analysis","cost accounting","management accounting",
    "accounts payable","accounts receivable","general ledger","bank reconciliation",
    "taxation","vat","gst","ifrs","gaap","audit","risk management",

    # Finance tools / ERP
    "quickbooks","xero","tally","sap","sap fico","oracle financials","netsuite","erp",

    # ---------- QA ----------
    # QA / Testing
    "qa","manual testing","automation testing","test planning","test cases",
    "regression testing","smoke testing","sanity testing","functional testing",
    "api testing","ui testing","e2e testing","performance testing","load testing","stress testing",
    "uat","security testing",

    "selenium","cypress","playwright","appium",
    "postman","soapui",
    "jira","testrail","zephyr",
    "jmeter","k6","browserstack","lambdatest",

    
    # ---------- Product / PM / PO / BA ----------
    "product management","product owner","business analysis",
    "requirements gathering","requirements analysis",
    "stakeholder management","user stories","acceptance criteria",
    "backlog grooming","sprint planning",
    "scrum","agile methodology","kanban",
    "product roadmap","roadmap planning","product strategy","prioritization",
    "market research","competitive analysis","customer research","user research",
    "product requirements document","prd","minimum viable product","mvp",
    "go to market","gtm","release planning","feature planning",
    "product analytics","event tracking","funnel analysis",

    
    # ---------- Operations / Ops----------
    "operations management","business operations","operations planning",
    "service delivery","customer operations",
    "process optimization","workflow optimization","sops",
    "compliance","risk management","quality management","quality control","internal controls",
    "vendor management","procurement","inventory management","logistics management",
    "resource planning","capacity planning",
    "project coordination","reporting","dashboarding",
    "ms excel","power bi",
    "continuous improvement","cost reduction",

}

# Allow very short tokens ONLY in section lists
SHORT_OK_IN_SECTIONS = {"r", "c", "go", "vba", "s3", "ec2"}

CANON = {
    "react.js": "react",
    "nodejs": "node.js",
    "postgres": "postgresql",
    "microsoft excel": "ms excel",
    "visual basic for excel": "vba",
    "amazon web services": "aws",
    "fastai": "fast.ai",
    "github-actions": "github actions",
    "github action": "github actions",
    "githubactions": "github actions",
    "c#.net": "c#",
    "c#net": "c#",
    "end-to-end": "",
    "end to end": "",
    "data-driven": "",
}

STOP = {
    "and","or","the","a","an","to","of","in","for","with","on","at","from","by","as",
    "is","are","was","were","be","been","being","this","that","these","those",
}

BLOCKLIST = {
    "resume","cv","curriculum","vitae","page","pages","section","reference","references",
    "email","phone","address","contact","present","work","worked","using","use","team",
    "professional","projects","project","experience","education","summary","profile",
    "university","college","school","institute",
    "management","development","business","system","software","solutions","tools","design",
    "skills","objective",

}

SOFT_NOISE_SUBSTR = [
    "results-driven","detail-oriented","user-friendly","hands-on","high-",
    "well-","real-time","real-world","fast-paced","self-motivated",
]

# Substrings that sometimes appear inside pasted profile blobs (ads / LinkedIn chrome)
# but should never be emitted as a skill token/phrase.
INLINE_JUNK_SUBSTR = [
    "don't want to see this",
    "do not want to see this",
    "your feedback will help us improve",
    "it's annoying or not interesting",
    "it is annoying or not interesting",
    "i've seen the same ad too often",
    "i have seen the same ad too often",
    "same ad too often",
    "please let us know",
    "tell us why",
    "not relevant",
    "report this ad",
    "and many more",
]

# Curly / typographic quotes → ASCII so substring checks match pasted LinkedIn / iOS text.
_UNICODE_TO_ASCII = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u2032": "'",
        "\u00b4": "'",
        "\u201c": '"',
        "\u201d": '"',
    }
)


def _ascii_quotes(s: str) -> str:
    return (s or "").translate(_UNICODE_TO_ASCII)


def _linkedin_ui_blob_heuristic(text: str) -> bool:
    """True when paste looks like LinkedIn profile + footer + ad feedback (not a normal CV)."""
    t = _ascii_quotes(text).lower()
    needles = (
        "don't want to see this",
        "your feedback will help",
        "same ad too often",
        "talent solutions",
        "community guidelines",
        "visit our help center",
        "manage your account",
        "ad choices",
        "marketing solutions",
    )
    return sum(1 for n in needles if n in t) >= 2


# Standalone lines common in LinkedIn “skills” / profile chrome; dropped only when _linkedin_ui_blob_heuristic.
_LINKEDIN_STANDALONE_CHIP_LINES = frozenset(
    {
        "web design",
        "mobile interface design",
        "user interface design",
        "user experience design (ued)",
        "user experience design",
        "adobe photoshop",
        "adobe illustrator",
        "figma (software)",
        "figma",
        "adobe xd",
    }
)

RE_TWO_WORD_HUMAN_NAME_LINE = re.compile(r"^[A-Z][a-z]{1,22}\s+[A-Z][a-z]{1,22}$")
RE_SHOUTCASE_BRAND_LINE = re.compile(r"^[A-Z0-9][A-Z0-9!\.]{1,18}$")
RE_YEARS_MARKETING_LINE = re.compile(
    r"(?:\d+\+?\s*(?:yrs?|years)\b.*\b(?:design|designing|dashboard|cro|clicks|customers)\b)"
    r"|(?:\bturning\s+clicks\s+into\b)"
    r"|(?:\bhigh[-\s]?conversion\b)",
    re.IGNORECASE,
)

# Lines that are typically LinkedIn (or similar) nav, footers, settings — not résumé skills.
# Matched on stripped line, lowercased, trailing .!? removed.
_SOCIAL_CHROME_LINE_NORMALIZE = re.compile(r"[\s\.!?]+$")


def _norm_chrome_line(line: str) -> str:
    s = _ascii_quotes(line.strip()).lower()
    s = _SOCIAL_CHROME_LINE_NORMALIZE.sub("", s)
    return s


def _linkedin_standalone_chip_line(raw: str) -> bool:
    """LinkedIn skill chips / endorsements (one per line) when paste is mostly UI noise."""
    s = _ascii_quotes(raw.strip()).lower()
    s = re.sub(r"\s+", " ", s).rstrip(".!?")
    if s in _LINKEDIN_STANDALONE_CHIP_LINES:
        return True
    s = re.sub(r"\s*\(software\)\s*$", "", s, flags=re.IGNORECASE).strip()
    if s in _LINKEDIN_STANDALONE_CHIP_LINES:
        return True
    s = re.sub(r"\s*\(ued\)\s*$", "", s, flags=re.IGNORECASE).strip()
    return s in _LINKEDIN_STANDALONE_CHIP_LINES


_SOCIAL_CHROME_EXACT_LINES = frozenset(
    {
        "about",
        "accessibility",
        "talent solutions",
        "community guidelines",
        "careers",
        "marketing solutions",
        "ad choices",
        "advertising",
        "sales solutions",
        "mobile",
        "small business",
        "safety center",
        "visit our help center",
        "go to your settings",
        "manage your account and privacy",
        "manage your account",
        "questions?",
        "help center",
        "privacy policy",
        "user agreement",
        "cookie policy",
        "ad preferences",
        "select language",
        "sign out",
        "join now",
        "sign in",
    }
)

# Drop a line if it contains any of these (case-insensitive). Kept narrow to avoid résumé prose.
_SOCIAL_CHROME_LINE_CONTAINS = (
    "linkedin.com/",
    "© linkedin",
    "(linkedin)",
    "linkedin corporation",
    "linkedin talent solutions",
    "linkedin learning",
    "get the linkedin app",
    "people also viewed",
    "people you may know",
    "you might like",
    "promoted",
    "sponsored",
)


def sanitize_text_for_skill_extraction(text: str) -> str:
    """
    Remove lines dominated by social-network chrome, footers, and ad-feedback UI.

    Taxonomy phrase matching (extract_general) runs over the whole document; without this,
    items like standalone footer links ('Accessibility', 'Careers') still match legitimate
    multi-word skills. Stripping obvious non-resume lines first cuts those false positives.
    """
    if not (text or "").strip():
        return text
    ui_blob = _linkedin_ui_blob_heuristic(text)
    kept: List[str] = []
    for line in text.splitlines():
        raw = line.rstrip()
        if not raw.strip():
            kept.append(raw)
            continue
        n = _norm_chrome_line(raw)
        if n in _SOCIAL_CHROME_EXACT_LINES:
            continue
        low = _ascii_quotes(raw).lower()
        # LinkedIn experience cards often include a standalone "· On-site" / "On-site"
        # line. Do NOT drop long résumé lines that merely contain "(On-site)" as part
        # of an experience entry — some OCR/PDF extraction collapses the entire
        # document into one line, and dropping it would erase all skill signals.
        if re.search(r"(?:^|\s)·\s*on-?site\b|^on-?site\b", low) or (
            "on-site" in low and len(raw) <= 120
        ):
            continue
        if any(s in low for s in _SOCIAL_CHROME_LINE_CONTAINS):
            continue
        # Do not drop whole skill section lines; comma-split + is_noise removes embedded ad fragments.
        if any(j in low for j in INLINE_JUNK_SUBSTR) and not RE_SECTION_LINE.match(raw.strip()):
            continue
        if "clients include" in low:
            continue
        if ui_blob and "boom!" in low:
            continue
        if ui_blob and RE_YEARS_MARKETING_LINE.search(raw):
            continue
        if ui_blob and _linkedin_standalone_chip_line(raw):
            continue
        if ui_blob and RE_TWO_WORD_HUMAN_NAME_LINE.match(raw.strip()) and not RE_SECTION_LINE.match(raw.strip()):
            continue
        if ui_blob and RE_SHOUTCASE_BRAND_LINE.match(raw.strip()) and not RE_SECTION_LINE.match(raw.strip()):
            continue
        kept.append(raw)
    return "\n".join(kept)


def normalize(s: str) -> str:
    s = s.strip().lower()
    s = RE_URL.sub(" ", s)
    s = re.sub(r"\s+", " ", s)
    s = s.strip(" \t\n\r.,;:()[]{}<>|/\\\"'")

    # Apply local canon first
    if s in CANON:
        s = CANON[s]

    # Apply taxonomy canon too
    if s in TAX_CANON:
        s = TAX_CANON[s]

    return s.strip()


def looks_like_ocr_junk(s: str) -> bool:
    return bool(re.fullmatch(r"o[a-z]{5,}", s)) or bool(re.search(r"\d{3,}", s))


def is_noise(s: str) -> bool:
    if not s:
        return True
    if s in STOP:
        return True
    if s in BLOCKLIST:
        return True
    if s in BRAND_BLACKLIST:
        return True
    if RE_DOMAIN.search(s):
        return True
    if looks_like_ocr_junk(s):
        return True
    if any(x in s for x in SOFT_NOISE_SUBSTR):
        return True
    sn = _ascii_quotes(s.lower())
    if any(j in sn for j in INLINE_JUNK_SUBSTR):
        return True
    if s.endswith("-") or s.startswith("-"):
        return True
    return False


def extract_from_section_lines(text: str) -> List[str]:
    out: List[str] = []
    for line in text.splitlines():
        m = RE_SECTION_LINE.match(line.strip())
        if not m:
            continue
        items = m.group(2)
        items = items.replace("(", ", ").replace(")", " ")
        for part in RE_SPLIT.split(items):
            p = normalize(part)
            if not p or is_noise(p):
                continue
            if len(p) <= 2 and p not in SHORT_OK_IN_SECTIONS:
                continue
            out.append(p)
    return out


def extract_from_skills_heavy_lines(text: str) -> List[str]:
    out: List[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or len(line) < 10:
            continue
        if RE_SKILLS_HEAVY_LINE.match(line):
            toks = [normalize(t) for t in RE_SPACE_SKILL_TOKENS.findall(line)]
            known = [t for t in toks if t and not is_noise(t) and (t in CORE_TOOLS or any(ch in t for ch in [".", "+", "#"]))]

            # Require line to be truly skills-heavy to avoid accidental extraction
            if len(known) < 6:
                continue

            out.extend(known)
    return out


def extract_general(text: str) -> List[str]:
    t = _ascii_quotes(text).lower()
    t = RE_URL.sub(" ", t)

    phrases = [normalize(x) for x in RE_PHRASES.findall(t)]
    tokens = [normalize(x) for x in RE_TECH.findall(t)]

    raw = phrases + tokens
    out: List[str] = []
    for x in raw:
        if not x or is_noise(x):
            continue

        # strong signal tokens
        if any(ch in x for ch in [".", "+", "#"]):
            if x in CORE_TOOLS or x in {"s3","ec2","eks","ecs","ecr","lambda","route53"} or "." in x:
                out.append(x)
            continue

        # tool gate
        if x in CORE_TOOLS:
            out.append(x)
            continue

    return out


def extract_skill_candidates(text: str) -> List[str]:
    text = sanitize_text_for_skill_extraction(text)
    sec = extract_from_section_lines(text)
    heavy = extract_from_skills_heavy_lines(text)
    gen = extract_general(text)

    seen = set()
    final: List[str] = []
    for x in sec + heavy + gen:
        if x and x not in seen:
            seen.add(x)
            final.append(x)
    return final


def build_global_vocab(all_texts: List[str], min_freq: int = 12, top_k: int = 4000) -> Counter:
    c = Counter()
    for t in all_texts:
        c.update(set(extract_skill_candidates(t)))
    c = Counter({k: v for k, v in c.items() if v >= min_freq})
    if len(c) > top_k:
        c = Counter(dict(c.most_common(top_k)))
    return c


def skills_for_resume(text: str, vocab: Set[str], max_skills: int = 80) -> List[str]:
    found = set(extract_skill_candidates(text))
    final = sorted(found & vocab)
    return final[:max_skills]


def infer_domains(skills: List[str]) -> List[str]:
    sset = set(skills)
    domains = []
    for d, keys in DOMAIN_KEYWORDS.items():
        if sset & keys:
            domains.append(d)
    return sorted(domains)
