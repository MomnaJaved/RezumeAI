# Deployment notes (Rezume AI)

## Environment

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL or SQLite (default: `rezume_dev.db` at repo root) |
| `CORS_ORIGINS` | Comma-separated browser origins |
| `JWT_SECRET` | **Change in production** — signing key for JWT |
| `JWT_EXPIRE_MINUTES` | Access token lifetime (default 60) |
| `REQUIRE_AUTH` | `true` to require `Authorization: Bearer <token>` on uploads |
| `MODEL_VERSION_*` | Optional labels: `MODEL_VERSION_TFIDF`, `MODEL_VERSION_SBERT`, `MODEL_VERSION_CROSSENCODER`, `MODEL_VERSION_ROLE` |
| `SKIP_MODEL_WARMUP` | `true` to skip loading transformers at startup (tests / cold containers) |

## Backend

```bash
export PYTHONPATH="${PWD}/backend:${PWD}:${PYTHONPATH}"
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Or `./run_api.sh`.

- Logs: `logs/app.log` (created automatically).
- **Rate limits:** uploads are limited (SlowAPI); tune in `backend/api/routers/uploads.py`.
- **Auth:** `POST /api/v1/auth/register` and `POST /api/v1/auth/login` issue JWTs. Set `REQUIRE_AUTH=true` to enforce on resume upload.

## Frontend

```bash
cd frontend && npm ci && npm run build
```

Serve `frontend/dist` with any static host; configure `VITE_API_BASE` at build time if the API is on another origin, or use the Vite dev proxy for local work.

## Docker (optional)

```dockerfile
# Example only — adjust paths and secrets
FROM python:3.11-slim
WORKDIR /app
COPY requirements-train.txt requirements.txt ./
RUN pip install --no-cache-dir -r requirements-train.txt
COPY backend api pyproject.toml* ./
COPY src ./src
ENV PYTHONPATH=/app/backend:/app
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Mount `artifacts/`, `.env`, and persistent volume for `DATABASE_URL` if SQLite.

## Production checklist

- [ ] Strong `JWT_SECRET`, HTTPS only
- [ ] PostgreSQL with backups
- [ ] Restrict `CORS_ORIGINS`
- [ ] Monitor `logs/app.log` and disk usage
- [ ] Re-run `training/evaluation/` after retraining and attach metrics to release notes
