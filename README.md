# Rezume AI

AI-based resume screening and candidate ranking system (resume parsing, JD matching, ranking, role classification).

## Pipeline

1. Ingest job descriptions + resumes
2. Parse resumes → structured `candidates.csv` + `skills_vocab.csv`
3. Enrich candidates (title, skills, education) → `candidates_enriched.csv`
4. Build (resume, JD, weak_score) pairs and **train/val/test splits without leakage** (by `candidate_id`)
5. **Baseline**: TF-IDF + cosine similarity match score
6. **Role classifier**: Fine-tune RoBERTa for frontend / backend / fullstack
7. **Match ranker**: Fine-tune cross-encoder (RoBERTa) for resume–JD score
8. **Inference**: NestJS-callable FastAPI server (`/classify_role`, `/match_score`)

## How to Run

See **[docs/HOW_TO_RUN.md](docs/HOW_TO_RUN.md)** for exact commands:

- Create venv + install deps (`requirements.txt` + `requirements-train.txt`)
- Prepare data (parse resumes, enrich candidates)
- Build pairs and splits: `scripts/build_pairs_and_splits.py`
- Run TF-IDF baseline: `scripts/05_tfidf_baseline.py`
- Train role classifier: `scripts/prepare_role_data.py` then `scripts/train_role_classifier.py`
- Train match ranker: `scripts/train_match_ranker.py`
- Evaluate: `scripts/evaluate_role_classifier.py`, `scripts/evaluate_rankings.py`
- Start inference server: `python api/inference_server.py`

## Docs

- [Data contract](docs/DATA_CONTRACT.md) — JSON/CSV schema for resumes, JDs, pairs, splits, **human labels**
- [Repo audit & design](docs/REPO_AUDIT.md) — what exists, what was fixed, design choices
- [Models and supervision](docs/MODELS_AND_SUPERVISION.md) — why two models (role + match), BERT/RoBERTa, weak vs **human-label (production)** training
