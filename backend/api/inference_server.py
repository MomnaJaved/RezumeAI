"""
FastAPI inference server for NestJS integration.
Endpoints: POST /classify_role, POST /match_score.
Example: NestJS can call http://localhost:8000/classify_role with JSON body.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI
from pydantic import BaseModel

from src.inference.service import classify_role, match_score

app = FastAPI(title="Rezume AI Inference", version="1.0")


class ClassifyRoleRequest(BaseModel):
    resume_text: str


class ClassifyRoleResponse(BaseModel):
    label: str
    probs: dict[str, float]


class MatchScoreRequest(BaseModel):
    resume_text: str
    jd_text: str


class MatchScoreResponse(BaseModel):
    score: float


@app.post("/classify_role", response_model=ClassifyRoleResponse)
def api_classify_role(req: ClassifyRoleRequest):
    out = classify_role(req.resume_text, return_probs=True)
    return ClassifyRoleResponse(label=out["label"], probs=out.get("probs", {}))


@app.post("/match_score", response_model=MatchScoreResponse)
def api_match_score(req: MatchScoreRequest):
    score = match_score(req.resume_text, req.jd_text)
    return MatchScoreResponse(score=score)


@app.get("/health")
def health():
    return {"status": "ok"}


# Example request/response for NestJS:
#
# POST /classify_role
# Request:  { "resume_text": "Experienced developer with React and Node.js..." }
# Response: { "label": "fullstack", "probs": { "frontend": 0.1, "backend": 0.2, "fullstack": 0.7 } }
#
# POST /match_score
# Request:  { "resume_text": "...", "jd_text": "We are hiring a Backend Developer..." }
# Response: { "score": 0.82 }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
