# Backend API and PostgreSQL

This repository ships a **FastAPI** application that combines:

1. **ML inference** — role classification, cross-encoder match score, SBERT shortlist + rerank (see `src/inference/`).
2. **REST + persistence** — jobs and candidates in a database via SQLAlchemy (**SQLite file `rezume_dev.db` by default**, or **PostgreSQL** when you set `DATABASE_URL`); optional storage of ranking runs.

### Training data vs live uploads

- **Synced CSV candidates** (`scripts/sync_enriched_to_postgres.py`) are the **same corpus** used to build training pairs and offline SBERT rankings. They are **not** “live applicants” by themselves—just the dataset loaded into the DB for demos and evaluation.
- **New applicants**: use **`POST /api/v1/uploads/resume`** (multipart PDF, DOCX, TXT, or image). The API extracts text (OCR for images if [Tesseract](https://github.com/tesseract-ocr/tesseract) + `pytesseract` are installed), strips PII, mines skills, infers a **role** label, and **creates/updates** a `Candidate` row.
- **Ranking uploads + everyone in the DB** against a job: **`POST /api/v1/jobs/{job_id}/rank-database-candidates`** — cross-encoder scores **all** candidates in the database (up to `limit`), because **new uploads do not appear** in the offline `sbert_rankings.csv` shortlist. Use `persist=true` to save results like `rank-and-save`. The older **`rank-and-save`** endpoint still uses **SBERT CSV → shortlist → cross-encoder**, which only covers candidates present in that file.

A separate **NestJS** (or any) backend can still call the same ML endpoints over HTTP; the sections below describe both patterns.

### “Application startup failed” / database connection errors

On startup the app runs `create_all()` and **must connect to the database**. If you see `connection refused` on port **5432**, Postgres is not running but your `.env` still has `DATABASE_URL=postgresql+...`.

**Fix (pick one):**

1. **Use SQLite (simplest):** remove `DATABASE_URL` from `.env` (the app defaults to `rezume_dev.db` in the repo root), or set `DATABASE_URL=sqlite+pysqlite:///./rezume_dev.db`.
2. **Use Postgres:** start the server first: `docker compose up -d postgres`, then keep your `DATABASE_URL` pointing at `localhost:5432`.

## Architecture options

### A. Single FastAPI app (this repo)

- **Postgres** holds canonical `jobs`, `candidates`, and `job_candidate_rankings`.
- **CSV files** remain the source for offline training and for **SBERT shortlists** (`outputs/rankings/sbert_rankings.csv`) until you recompute shortlists from the DB or a vector index.
- Flow: sync CSV → Postgres → `POST .../rank-and-save` reads job/candidate text from DB when rows exist, uses SBERT CSV for candidate IDs per job, then writes scores back to Postgres.

### B. NestJS + this FastAPI service

- **NestJS** owns auth, users, tenants, and can use **its own** Postgres (or the same database with separate schemas).
- NestJS **HTTP client** calls this service, for example:
  - `POST http://ml:8000/classify_role`
  - `POST http://ml:8000/match_score`
  - `POST http://ml:8000/rank_candidates_for_job`
- Data flow: NestJS stores job/candidate documents; when ranking, it either pushes text into the ML service (stateless JSON) or ensures this service’s DB is synced (same as pattern A).

Connecting NestJS to Postgres is standard: use `@nestjs/typeorm` or `Prisma` with `DATABASE_URL` pointing at your instance. No code in this repo is required for that—only agreement on **IDs** (e.g. `external_id` = your `jobId` string).

## FYP defense / demo day (PostgreSQL)

Use **Postgres in Docker** so the panel sees a normal “server + database” setup. Do a **full dry run** the day before on the **same laptop** you will present with.

### Checklist

1. **Install and start Docker Desktop** (or Docker Engine on Linux). Confirm it is running before the session.
2. **`.env`** must point at Postgres (not SQLite):

   ```bash
   DATABASE_URL=postgresql+psycopg2://rezume:rezume@localhost:5432/rezumeai
   ```

3. **Start Postgres and wait until it is ready:**

   ```bash
   bash training/scripts/defense_postgres_ready.sh
   ```

   Or manually: `docker compose up -d postgres` and wait until `pg_isready` succeeds.

4. **Start the API** (creates tables on startup):

   ```bash
   PYTHONPATH=backend uvicorn api.main:app --host 0.0.0.0 --port 8000
   ```

5. **Load demo data** (needs your enriched CSVs on disk):

   ```bash
   python training/scripts/sync_enriched_to_postgres.py
   ```

6. **Verify in the browser:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) — try `GET /health` and `GET /api/v1/jobs`.

7. **Optional UI:** `cd frontend && npm run dev` — ensure the API is on port 8000 (Vite proxies to it).

### If Docker fails on the day

Keep **SQLite** as fallback: remove or comment out `DATABASE_URL` in `.env` so the app uses `rezume_dev.db`, and say you are showing the **same API** with embedded storage. Prefer fixing Docker; fallback avoids a blank demo.

---

## Run PostgreSQL locally

```bash
docker compose up -d postgres
```

Copy `.env.example` to `.env` and set `DATABASE_URL` to match `docker-compose.yml` (user `rezume`, password `rezume`, db `rezumeai`).

## Install API dependencies

```bash
pip install -r requirements-train.txt
```

## Create tables

Either start the API (tables are created on startup) or:

```bash
python training/scripts/init_db.py
```

## Load jobs and candidates from enriched CSVs

```bash
python training/scripts/sync_enriched_to_postgres.py
```

You still need `outputs/rankings/sbert_rankings.csv` from the SBERT pipeline for `rank_candidates_for_job` / `rank-and-save`.

## Run the API

From the repo root:

```bash
PYTHONPATH=backend uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

Open **Swagger**: http://127.0.0.1:8000/docs

## Endpoint map

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness |
| POST | `/classify_role` | Legacy — same as `/api/v1/ml/classify_role` |
| POST | `/match_score` | Legacy |
| POST | `/rank_candidates_for_job` | Legacy — rank without persisting |
| POST | `/api/v1/ml/classify_role` | Role label + probs |
| POST | `/api/v1/ml/match_score` | Single resume vs JD score |
| POST | `/api/v1/ml/rank_candidates_for_job` | SBERT shortlist + rerank |
| GET | `/api/v1/jobs` | List jobs in DB |
| POST | `/api/v1/jobs` | Create job |
| GET | `/api/v1/jobs/by-external/{id}` | By `job_id` e.g. J001 |
| GET | `/api/v1/candidates` | List candidates |
| POST | `/api/v1/candidates` | Create candidate |
| GET | `/api/v1/candidates/by-external/{id}` | By `candidate_id` |
| POST | `/api/v1/jobs/{external_id}/rank-and-save` | Rank and persist rows (snapshots **name, CV title, role, years experience, degree, skills summary** on each ranking row) |
| POST | `/api/v1/jobs/{external_id}/rank-database-candidates` | Cross-encoder rank **DB candidates** (uploads + sync); query `limit`, `top_return`, `persist` |
| POST | `/api/v1/uploads/resume` | Multipart **PDF / DOCX / TXT / image** → parse → create/update **Candidate** |
| GET | `/api/v1/jobs/{external_id}/rankings` | Read persisted rankings (same snapshot fields) |

## How SQLAlchemy connects to Postgres

1. `DATABASE_URL` is read in `api/config.py` (`pydantic-settings`).
2. `api/database.py` builds a SQLAlchemy `engine` and `SessionLocal`.
3. `get_db` yields a session per request (FastAPI dependency).
4. Routers use `Session` to query `api/models.py` (`Job`, `Candidate`, `JobCandidateRanking`).

To change database, only change `DATABASE_URL` (e.g. Neon, RDS, Supabase all provide a Postgres URL).

## Frontend

The `frontend/` app is a Vite + React UI that calls `/api/v1/*` and legacy ML routes. Set `VITE_API_BASE` if the API is not on `http://127.0.0.1:8000`.
