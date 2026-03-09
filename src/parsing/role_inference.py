from __future__ import annotations

import re

# If you already have a canonical map in your taxonomy, use it.
try:
    from src.parsing.skill_taxonomy import CANON as SKILL_CANON
except Exception:
    SKILL_CANON = {}

RE_MULTI_SPACE = re.compile(r"\s+")

def canon_skill(s: str) -> str:
    s = s.strip().lower()
    s = RE_MULTI_SPACE.sub(" ", s)
    # normalize common variants
    s = s.replace("react.js", "react")
    s = s.replace("nodejs", "node.js")
    s = s.replace("nest.js", "nestjs")
    s = s.replace("expressjs", "express.js")
    s = s.replace("js", "javascript") if s == "js" else s
    # apply taxonomy canon if available
    if s in SKILL_CANON:
        s = SKILL_CANON[s]
    return s

DEPT_RULES = {
    "engineering": {
        "javascript","typescript","react","node.js","express.js","nestjs",
        "html","css","mongodb","mysql","postgresql","rest apis","docker","git"
    },
    "data": {"python","pandas","numpy","scikit-learn","tensorflow","pytorch","sql","power bi"},
    "qa": {"selenium","cypress","playwright","jmeter","postman","test cases","automation"},
    "design": {"figma","wireframing","prototyping","typography","adobe illustrator","adobe photoshop"},
    "devops": {"aws","docker","kubernetes","terraform","jenkins","ci/cd"},
    "marketing": {"seo","google analytics","google ads","meta ads","content marketing"},
    "hr": {"recruitment","talent acquisition","hris","onboarding"},
    "finance": {"ifrs","gaap","audit","tax","budgeting"},
    "operations": {"inventory management","reporting","process optimization"}
}

ROLE_RULES = {

    # ENGINEERING
    "software engineer": {"software engineer", "software development"},
    "full stack developer": {"full stack", "web development", "html css", "react","node.js","javascript","mongodb","mysql","postgresql"},
    "mobile developer": {"react native", "mobile application"},
    "backend developer": {"node.js", "django", "flask", "express.js","nestjs","postgresql","mysql"},
    "frontend developer": {"react", "html", "css", "javascript"},
    "devops engineer": {"aws","docker","kubernetes","terraform"},
    "qa engineer": {"selenium","automation","postman"},
    "ui/ux designer": {"figma","prototyping","wireframing"},

    # DATA
    "data scientist": {"machine learning", "python", "pandas", "numpy","scikit-learn"},
    "data analyst": {"sql server", "power bi", "excel"},

    # MARKETING / BUSINESS
    "business development executive": {"business development", "lead generation"},
    "email marketing specialist": {"email marketing", "campaign"},
    "social media manager": {"social media", "digital marketing"},

    # OPERATIONS / ADMIN
    "data entry operator": {"data entry"},
    "customer service representative": {"customer service"},

}
def infer_title_from_skills(skills_csv: str) -> str:
    if not isinstance(skills_csv, str) or not skills_csv.strip():
        return "unknown"

    skills = {s.strip().lower() for s in skills_csv.split(",")}

    best_role = "unknown"
    best_score = 0

    for role, keys in ROLE_RULES.items():
        score = 0
        for k in keys:
            if any(k in s for s in skills):
                score += 1
        if score > best_score:
            best_score = score
            best_role = role

    if best_score >= 1:
        return best_role

    return "unknown"

# def infer_title_from_skills(skills_csv: str) -> str:
#     if not isinstance(skills_csv, str) or not skills_csv.strip():
#         return "unknown"

#     skills = {canon_skill(s) for s in skills_csv.split(",") if s.strip()}
#     skills.discard("")

#     # 1) department
#     dept, dept_score = "unknown", 0
#     for d, keys in DEPT_RULES.items():
#         sc = len(skills & keys)
#         if sc > dept_score:
#             dept, dept_score = d, sc

#     if dept_score == 0:
#         return "unknown"

#     # 2) role (lower threshold + better canon)
#     best_role, best_score = None, 0
#     for role, keys in ROLE_RULES.items():
#         sc = len(skills & keys)
#         if sc > best_score:
#             best_role, best_score = role, sc

#     # Key change: use >=1 for role if dept is engineering (titles vary a lot)
#     if best_role and (best_score >= 2 or (dept == "engineering" and best_score >= 1)):
#         return best_role

#     return f"{dept} professional"
