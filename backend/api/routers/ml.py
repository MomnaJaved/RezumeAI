from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.database import get_db
from api.models import Candidate, Job
from api.schemas import (
    ClassifyRoleRequest,
    ClassifyRoleResponse,
    MatchScoreRequest,
    MatchScoreResponse,
    RankCandidatesRequest,
    RankCandidatesResponse,
    RankedCandidateOut,
    RankingExplanationOut,
)
from api.services.ranking_explain import build_ranking_explanation
from api.services.ranking_run import rank_for_external_job_id
from src.inference.service import classify_role, match_score

router = APIRouter(prefix="/ml", tags=["ml"])


@router.post("/classify_role", response_model=ClassifyRoleResponse)
def classify_role_endpoint(req: ClassifyRoleRequest):
    out = classify_role(req.resume_text, return_probs=True)
    return ClassifyRoleResponse(label=out["label"], probs=out.get("probs", {}))


@router.post("/match_score", response_model=MatchScoreResponse)
def match_score_endpoint(req: MatchScoreRequest):
    score = match_score(req.resume_text, req.jd_text)
    return MatchScoreResponse(score=score)


@router.post("/rank_candidates_for_job", response_model=RankCandidatesResponse)
def rank_candidates_endpoint(
    req: RankCandidatesRequest,
    db: Session = Depends(get_db),
):
    job_row = db.query(Job).filter(Job.external_id == str(req.job_id)).first()
    job_id, rows = rank_for_external_job_id(db, req.job_id, req.top_k)
    candidates_out: list[RankedCandidateOut] = []
    for r in rows:
        expl = None
        if job_row:
            cand = db.query(Candidate).filter(Candidate.external_id == r["candidate_id"]).first()
            if cand:
                expl = RankingExplanationOut(
                    **build_ranking_explanation(job_row, cand, r["cross_encoder_score"])
                )
        candidates_out.append(
            RankedCandidateOut(
                candidate_id=r["candidate_id"],
                cross_encoder_score=r["cross_encoder_score"],
                sbert_similarity=r["sbert_similarity"],
                candidate_name=r.get("candidate_name") or "",
                candidate_title=r.get("candidate_title") or "",
                candidate_role=r.get("candidate_role") or "",
                years_experience=r.get("years_experience"),
                highest_degree=r.get("highest_degree") or "",
                skills_summary=r.get("skills_summary") or "",
                explanation=expl,
            )
        )
    return RankCandidatesResponse(job_id=job_id, candidates=candidates_out)
