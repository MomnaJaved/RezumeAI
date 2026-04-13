# Rezume AI

AI-based resume screening and candidate ranking (parsing, JD matching, SBERT + cross-encoder ranking, role classification).

**Screening (hiring-style):** Prefer **`POST /api/v1/jobs/{id}/rank-database-candidates`** (and **Save DB ranking** in the UI). It scores everyone in the database with the **cross-encoder**, so good candidates are not excluded by the offline SBERT shortlist. The cross-encoder is trained on your pair-level match signal, not on SBERT cosine—use its **rank order** as the main automated prior, then add human review. True hiring quality still needs **human relevance labels** to retrain or calibrate beyond silver (`weak_score`) targets.

## Repository layout

| Folder | Role |
|--------|------|
| **`backend/api/`** | FastAPI REST API, PostgreSQL/SQLite, resume uploads |
| **`frontend/`** | React UI |
| **`training/scripts/`** | Pipelines, training, evaluation, DB sync |
| **`training/config/`** | Training YAML configs |
| **`src/`** | Shared library (parsing, inference, skills) |

Details: **[docs/REPO_LAYOUT.md](docs/REPO_LAYOUT.md)**

## Pipeline (offline)

1. Ingest job descriptions + resumes  
2. Parse resumes → `candidates.csv` + skills  
3. Enrich candidates → `candidates_enriched.csv`  
4. Build pairs + **leak-free splits** (by `candidate_id`)  
5. **Baseline**: TF-IDF + cosine  
6. **Role classifier** + **Match ranker** (cross-encoder)  
7. **API**: `backend/api` + optional **`frontend/`**

## How to run

See **[docs/HOW_TO_RUN.md](docs/HOW_TO_RUN.md)** (paths use `training/scripts/` and `training/config/`).

**API (from repo root):**

```bash
source .venv/bin/activate
export PYTHONPATH="${PWD}/backend:${PYTHONPATH}"
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

Or: **`./run_api.sh`** (uses `.venv` if present).

**Frontend:**

```bash
cd frontend && npm install && npm run dev
```

## Evaluation (FYP metrics)

```bash
pip install -r requirements-train.txt
export PYTHONPATH="${PWD}:${PYTHONPATH}"
python training/evaluation/evaluate_ranker.py --mock
python training/evaluation/evaluate_classifier.py --mock
```

Full detail: **[docs/EVALUATION.md](docs/EVALUATION.md)**  
Outputs land in **`outputs/evaluation/`** (JSON + CSV).

## Tests

```bash
pip install -r requirements-dev.txt
export PYTHONPATH="${PWD}/backend:${PWD}:${PYTHONPATH}"
pytest tests/ -v
pytest tests/ --cov=api --cov=src --cov-report=term-missing
```

See **[docs/TESTING.md](docs/TESTING.md)**.

## Main API endpoints (prefix `/api/v1` unless legacy)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness |
| GET | `/meta/models` | Model version labels + artifact presence |
| GET | `/meta/stats` | Candidate/job counts |
| POST | `/auth/register`, `/auth/login` | JWT (optional `REQUIRE_AUTH` for uploads) |
| POST | `/uploads/resume` | Parse + store candidate |
| POST | `/jobs/.../rank-database-candidates` | Cross-encoder on DB pool |
| POST | `/jobs/.../rank-and-save` | SBERT shortlist + cross-encoder + save |
| GET | `/jobs/.../rankings` | Saved rankings (with explanation when stored) |
| POST | `/feedback/ranking-selection` | Log human select/shortlist/reject for retraining |

Legacy unprefixed routes: `/classify_role`, `/match_score`, `/rank_candidates_for_job`.

## Docs

- [Repository layout](docs/REPO_LAYOUT.md)  
- [Backend API & database](docs/BACKEND_AND_DATABASE.md)  
- [How to run pipelines](docs/HOW_TO_RUN.md)  
- [Data contract](docs/DATA_CONTRACT.md)  
- [Repo audit & design](docs/REPO_AUDIT.md)  
- [Models and supervision](docs/MODELS_AND_SUPERVISION.md)  
- [Evaluation](docs/EVALUATION.md)  
- [Testing](docs/TESTING.md)  
- [Deployment](docs/DEPLOYMENT.md)  
- [Bias & fairness](docs/BIAS_AND_FAIRNESS.md)  
