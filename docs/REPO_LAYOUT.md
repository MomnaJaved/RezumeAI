# Repository layout

| Path | Purpose |
|------|---------|
| **`backend/api/`** | FastAPI app: REST + uploads + DB models (`PYTHONPATH` must include `backend/`). |
| **`frontend/`** | Vite + React UI (jobs, upload, ranking previews). |
| **`training/scripts/`** | Data prep, baselines, SBERT, training, eval, DB sync helpers. |
| **`training/config/`** | YAML for `train_match_ranker`, `train_role_classifier`. |
| **`src/`** | Shared Python library: parsing, PII, skill mining, inference models. |
| **`artifacts/`** | Trained weights (gitignored by default). |
| **`outputs/`** | Generated CSVs, rankings, embeddings (often gitignored). |
| **`docs/`** | Design and runbooks. |

## Run commands (from repo root)

```bash
# API
export PYTHONPATH="${PWD}/backend:${PYTHONPATH}"
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
# or: ./run_api.sh --reload

# Training example
python training/scripts/build_pairs_and_splits.py
python training/scripts/train_match_ranker.py --config training/config/train_match.yaml

# Sync CSV → DB
python training/scripts/sync_enriched_to_postgres.py
```

The **`src/`** package is imported as `from src....`; the **`api`** package lives under **`backend/`**, so `PYTHONPATH` must include the `backend` directory (not the repo root alone).
