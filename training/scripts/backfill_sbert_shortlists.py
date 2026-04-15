"""
Backfill SBERT stage-1 shortlist cache in DB.

Usage (from repo root):
  PYTHONPATH=backend:. python training/scripts/backfill_sbert_shortlists.py

Notes:
- This computes SBERT embeddings for candidates missing `embedding_sbert`
- Then computes cosine similarities and stores Top-K per job in `job_candidate_sbert_scores`
- SBERT scores are used ONLY for shortlisting; never shown in UI.
"""

from __future__ import annotations

import os

from api.database import SessionLocal
from api.services.sbert_cache import refresh_sbert_for_all_jobs


def main() -> None:
    top_k = int(os.environ.get("REZUME_SBERT_TOPK", "200") or "200")
    only_active = (os.environ.get("REZUME_SBERT_ONLY_ACTIVE", "0") or "0").strip() == "1"
    db = SessionLocal()
    try:
        n = refresh_sbert_for_all_jobs(db, top_k=top_k, only_active=only_active)
        print(f"ok: refreshed sbert shortlist rows ~= {n}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

