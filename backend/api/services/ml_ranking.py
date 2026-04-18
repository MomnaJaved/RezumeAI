"""
Load enriched CSVs + SBERT rankings for ML endpoints (fallback when DB has no text).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from api.paths import repo_root

ROOT = repo_root()

_jobs_df: pd.DataFrame | None = None
_cands_df: pd.DataFrame | None = None
_sbert_df: pd.DataFrame | None = None


def load_dataframes() -> None:
    global _jobs_df, _cands_df, _sbert_df

    jobs_path = ROOT / "data" / "processed" / "jobs_enriched.csv"
    cands_path = ROOT / "outputs" / "parsing" / "candidates_enriched.csv"
    sbert_path = ROOT / "outputs" / "rankings" / "sbert_rankings.csv"

    if _jobs_df is None:
        if not jobs_path.exists():
            raise FileNotFoundError(f"Missing {jobs_path}")
        _jobs_df = pd.read_csv(jobs_path).fillna("")

    if _cands_df is None:
        if not cands_path.exists():
            raise FileNotFoundError(f"Missing {cands_path}")
        _cands_df = pd.read_csv(cands_path).fillna("")

    if _sbert_df is None:
        if not sbert_path.exists():
            raise FileNotFoundError(
                f"Missing {sbert_path}. Run compute_sbert_embeddings.py and sbert_retrieval_ranker.py"
            )
        _sbert_df = pd.read_csv(sbert_path)


def get_jobs_df() -> pd.DataFrame:
    load_dataframes()
    assert _jobs_df is not None
    return _jobs_df


def get_cands_df() -> pd.DataFrame:
    load_dataframes()
    assert _cands_df is not None
    return _cands_df


def get_sbert_df() -> pd.DataFrame:
    load_dataframes()
    assert _sbert_df is not None
    return _sbert_df


def build_job_text_from_row(job_row: pd.Series) -> str:
    return " ".join(
        [
            str(job_row.get("job_title", "")),
            str(job_row.get("job_description_raw", "")),
            str(job_row.get("job_skills", "")),
        ]
    ).strip()


def build_cand_text_from_row(cand_row: pd.Series) -> str:
    return " ".join(
        [
            str(cand_row.get("title", "")),
            str(cand_row.get("skills", "")),
            str(cand_row.get("raw_text", "")),
        ]
    ).strip()


def build_job_text_from_db(job) -> str:
    return " ".join([job.title or "", job.description or "", job.skills or ""]).strip()


def build_cand_text_from_db(cand) -> str:
    from api.services.candidate_title_db import resolved_display_title

    t = resolved_display_title(cand)
    return " ".join([t, cand.skills or "", cand.raw_text or ""]).strip()
