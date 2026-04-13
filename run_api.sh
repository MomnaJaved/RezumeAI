#!/usr/bin/env bash
# Run FastAPI from repository root (loads .env here, adds backend/ to PYTHONPATH).
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="${PWD}/backend:${PYTHONPATH:-}"
exec .venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 "$@"
