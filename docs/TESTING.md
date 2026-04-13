# Testing (Rezume AI)

## Install

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt
```

`requirements-dev.txt` pulls in training/API dependencies plus **pytest**, **pytest-cov**, **httpx**, **bcrypt**, **python-jose**, and **slowapi** used by the API.

## Run tests

From repository root:

```bash
export PYTHONPATH="${PWD}/backend:${PWD}:${PYTHONPATH}"
pytest tests/ -v
```

**Coverage** (API + shared `src`):

```bash
pytest tests/ --cov=api --cov=src --cov-report=term-missing --cov-report=html
```

Open `htmlcov/index.html` in a browser.

## What is covered

| Area | Tests |
|------|--------|
| Weak supervision scores | `tests/test_weak_score.py` |
| PII helpers | `tests/test_pii.py` |
| Resume parse (TXT) | `tests/test_resume_ingest.py` |
| Health + meta | `tests/test_api_health_and_meta.py` |
| Upload validation | `tests/test_api_upload.py` |
| Job create + upload flow | `tests/test_integration_flow.py` |

**Test database:** `conftest.py` uses an isolated SQLite file per test via `dependency_overrides` and sets `REZUME_TESTING=1` so the app lifespan skips binding to your dev DB.

**Model warmups** are skipped with `SKIP_MODEL_WARMUP=true` (set in `conftest`).

## CI suggestion

```yaml
- run: pip install -r requirements-dev.txt
- run: PYTHONPATH=backend:. pytest tests/ --cov=api --cov=src --cov-fail-under=0
```

Raise `--cov-fail-under` as coverage grows.
