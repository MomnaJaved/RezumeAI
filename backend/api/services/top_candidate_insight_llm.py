"""OpenAI-compatible Chat Completions for top-candidate narrative (optional)."""
from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from api.config import Settings

_log = logging.getLogger("rezume.api")

_SYSTEM = """You are an AI recruiting analyst. Write exactly ONE concise professional paragraph (executive summary style).
Rules:
- Use ONLY facts present in the JSON and the draft paragraph. Do NOT invent employers, projects, skills, or years not in the data.
- Analytical, decision-focused, recruiter-friendly tone. No bullet lists unless absolutely necessary (prefer none).
- Explain why the #1 candidate leads versus peers when peer data exists; otherwise summarize why #1 leads the ranked set.
- End with a clear statement on why #1 has the strongest expected impact for the role.
"""


def generate_top_candidate_insight_llm(
    settings: "Settings",
    *,
    facts: dict,
    template_fallback: str,
) -> str | None:
    key = (getattr(settings, "openai_api_key", None) or "").strip()
    if not key:
        return None
    base = (getattr(settings, "openai_api_base", None) or "https://api.openai.com/v1").rstrip("/")
    model = (getattr(settings, "openai_model", None) or "gpt-4o-mini").strip()
    timeout = max(5, int(getattr(settings, "openai_insight_timeout_seconds", None) or 45))
    url = f"{base}/chat/completions"
    user = (
        "Ground-truth JSON (structured signals from our ranker; do not contradict):\n"
        f"{json.dumps(facts, ensure_ascii=False, indent=2)[:12000]}\n\n"
        "Internal draft (may rephrase but do not add uncited claims):\n"
        f"{template_fallback[:6000]}"
    )
    payload = {
        "model": model,
        "temperature": 0.35,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user},
        ],
    }
    try:
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
            timeout=timeout,
        )
        if not r.ok:
            _log.warning("OpenAI insight HTTP %s: %s", r.status_code, r.text[:500])
            return None
        data = r.json()
        choice = (data.get("choices") or [{}])[0]
        msg = (choice.get("message") or {}).get("content") or ""
        text = str(msg).strip()
        if not text:
            return None
        # Strip common markdown bold / bullets the model might still emit.
        text = re.sub(r"\s+", " ", text)
        text = text.replace("**", "").strip()
        if len(text) > 2800:
            text = text[:2797] + "…"
        return text
    except Exception as e:
        _log.warning("OpenAI insight call failed: %s", e)
        return None
