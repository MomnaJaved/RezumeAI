"""
Optional xAI Grok pass: noisy LinkedIn scrape → factual candidate fields + clean text for matching.

Uses OpenAI-compatible Chat Completions (https://api.x.ai/v1/chat/completions).
Configure XAI_API_KEY (and optionally XAI_API_BASE, XAI_MODEL) in .env.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from api.config import Settings

_log = logging.getLogger("rezume.api")

_SYSTEM = """You are a recruiting data normalizer. You receive raw text scraped from a public LinkedIn profile (including UI noise, ads, endorsements, section headers).

Task:
1. Extract ONLY factual information about the human candidate (identity, headline, location, email if present, summary/about, work experience, education, skills, certifications, languages if clearly stated).
2. Remove LinkedIn UI strings (e.g. "Show all", "Try Premium", endorsement counts, tab labels), ads, and duplicate boilerplate.
3. Do NOT invent employers, degrees, dates, or skills not supported by the input.
4. If a field is unknown, use null or empty string.

Output: a single JSON object with EXACTLY these keys (all string unless noted):
{
  "candidate_name": string,
  "candidate_title": string,
  "candidate_location": string,
  "candidate_email": string,
  "candidate_skills": string,
  "certifications": string,
  "about_summary": string,
  "experience_block": string,
  "education_block": string,
  "candidate_text": string,
  "years_experience": number|null,
  "highest_degree": string
}

Rules for candidate_text:
- A clean multi-section plain-text profile suitable for job matching (not JSON inside).
- Start with a short header block: Name, Current Title, Location, Email (if any), Skills (comma-separated), then SUMMARY, EXPERIENCE, EDUCATION sections as applicable.
- Use only facts from the input. Maximize signal, minimize noise. Stay under 12000 characters if possible.
"""


def _extract_json_object(text: str) -> dict[str, Any]:
    t = (text or "").strip()
    if not t:
        raise ValueError("empty model response")
    if t.startswith("{"):
        try:
            return json.loads(t)
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{[\s\S]*\}\s*$", t)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    m2 = re.search(r"\{[\s\S]*\}", t)
    if m2:
        return json.loads(m2.group(0))
    raise ValueError("no JSON object in model response")


def refine_linkedin_scrape(settings: "Settings", *, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Returns normalized dict for API response (always includes refined_ok).
    """
    key = (getattr(settings, "xai_api_key", None) or "").strip()
    if not key:
        return {"refined_ok": False, "skipped_reason": "xai_api_key not configured"}

    base = (getattr(settings, "xai_api_base", None) or "https://api.x.ai/v1").rstrip("/")
    model = (getattr(settings, "xai_model", None) or "grok-2-latest").strip()
    timeout = max(10, int(getattr(settings, "xai_refine_timeout_seconds", None) or 90))

    raw = {
        "scraped_full_text": (payload.get("raw_full_text") or "")[:28000],
        "scraped_canonical": (payload.get("raw_canonical") or "")[:28000],
        "heuristic_name": payload.get("name"),
        "heuristic_title": payload.get("title"),
        "heuristic_location": payload.get("location"),
        "heuristic_email": payload.get("email"),
        "heuristic_skills": payload.get("skills"),
        "years_experience": payload.get("years_experience"),
        "highest_degree": payload.get("highest_degree"),
        "certifications": payload.get("certifications"),
        "profile_url": payload.get("profile_url"),
        "profile_json_excerpt": _json_excerpt(payload.get("profile_json"), 8000),
    }
    user = (
        "Heuristic extractor output (may be noisy; trust the scraped text blocks more):\n"
        f"{json.dumps(raw, ensure_ascii=False)[:32000]}\n\n"
        "Return ONLY the JSON object, no markdown fences, no commentary."
    )

    url = f"{base}/chat/completions"
    body: dict[str, Any] = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user},
        ],
    }
    # xAI supports json mode on recent models; ignore if rejected.
    body["response_format"] = {"type": "json_object"}

    def _post(b: dict[str, Any]) -> requests.Response:
        return requests.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=b,
            timeout=timeout,
        )

    try:
        r = _post(body)
        if r.status_code >= 400 and "response_format" in body:
            b2 = {k: v for k, v in body.items() if k != "response_format"}
            r = _post(b2)
    except requests.RequestException as e:
        _log.warning("Grok refine request failed: %s", e)
        return {"refined_ok": False, "skipped_reason": f"request failed: {e}"}

    if not r.ok:
        _log.warning("Grok refine HTTP %s: %s", r.status_code, (r.text or "")[:800])
        try:
            err = r.json()
            detail = err.get("error", {}).get("message") if isinstance(err.get("error"), dict) else err
        except Exception:
            detail = (r.text or "")[:500]
        return {"refined_ok": False, "skipped_reason": f"HTTP {r.status_code}: {detail}"}

    try:
        data = r.json()
        choice = (data.get("choices") or [{}])[0]
        msg = (choice.get("message") or {}).get("content") or ""
        parsed = _extract_json_object(str(msg))
    except Exception as e:
        _log.warning("Grok refine parse failed: %s", e)
        return {"refined_ok": False, "skipped_reason": f"parse error: {e}"}

    ct = str(parsed.get("candidate_text") or "").strip()
    if len(ct) < 40:
        return {"refined_ok": False, "skipped_reason": "model returned too little candidate_text"}

    out: dict[str, Any] = {
        "refined_ok": True,
        "candidate_text": ct[:28000],
        "candidate_name": (parsed.get("candidate_name") or "").strip() or None,
        "candidate_title": (parsed.get("candidate_title") or "").strip() or None,
        "candidate_location": (parsed.get("candidate_location") or "").strip() or None,
        "candidate_email": (parsed.get("candidate_email") or "").strip() or None,
        "candidate_skills": (parsed.get("candidate_skills") or "").strip() or None,
        "certifications": (parsed.get("certifications") or "").strip() or None,
        "about_summary": (parsed.get("about_summary") or "").strip() or None,
        "experience_block": (parsed.get("experience_block") or "").strip() or None,
        "education_block": (parsed.get("education_block") or "").strip() or None,
    }
    y = parsed.get("years_experience")
    if y is not None and y != "":
        try:
            yf = float(y)
            if 0 <= yf <= 80:
                out["years_experience"] = round(yf, 2)
        except (TypeError, ValueError):
            pass
    hd = (parsed.get("highest_degree") or "").strip()
    if hd:
        out["highest_degree"] = hd[:256]
    return out


def _json_excerpt(obj: Any, max_chars: int) -> str:
    if obj is None:
        return ""
    try:
        s = json.dumps(obj, ensure_ascii=False)[:max_chars]
        return s
    except Exception:
        return ""
