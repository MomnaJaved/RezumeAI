#!/usr/bin/env python3
"""
Compute and store SBERT embeddings for candidates in the API database.

This enables semantic shortlist (vector search) in:
  POST /api/v1/jobs/{job_id}/rank-database-candidates?prefilter=sbert&prefilter_k=...

Usage (repo root):
  PYTHONPATH=backend:. python training/scripts/compute_candidate_embeddings_db.py

Notes:
  - Uses candidate text built from DB: title + skills + raw_text (same as ranking).
  - Stores raw float32 bytes into candidates.embedding_sbert.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy.orm import Session  # noqa: E402

from api.database import SessionLocal  # noqa: E402
from api.models import Candidate  # noqa: E402
from api.services import ml_ranking  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Compute SBERT embeddings for DB candidates")
    ap.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
    ap.add_argument("--limit", type=int, default=0, help="0 = all candidates")
    ap.add_argument("--only-missing", action="store_true", help="Only compute if embedding_sbert is NULL")
    args = ap.parse_args()

    from api.services.sbert_shortlist import embed_text  # noqa: E402

    db: Session = SessionLocal()
    try:
        q = db.query(Candidate).order_by(Candidate.created_at.desc())
        if args.limit and args.limit > 0:
            q = q.limit(int(args.limit))
        cands = list(q.all())
        if not cands:
            print("No candidates in DB.")
            return

        updated = 0
        skipped = 0
        for c in cands:
            if args.only_missing and getattr(c, "embedding_sbert", None):
                skipped += 1
                continue
            text = (ml_ranking.build_cand_text_from_db(c) or "").strip()
            if not text:
                skipped += 1
                continue
            v = embed_text(text, model_name=args.model).astype(np.float32, copy=False)
            c.embedding_sbert = v.tobytes()
            updated += 1
            if updated % 50 == 0:
                db.commit()
                print("Committed", updated)

        db.commit()
        print("Done. updated=", updated, "skipped=", skipped, "total=", len(cands))
    finally:
        db.close()


if __name__ == "__main__":
    main()

