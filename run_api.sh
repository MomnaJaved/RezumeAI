#!/usr/bin/env bash
# Run FastAPI from repository root (loads .env here, adds backend/ to PYTHONPATH).
set -euo pipefail
cd "$(dirname "$0")"
# conda-forge / Homebrew CLI (tesseract, etc.) — minimal PATH from IDEs misses these.
export PATH="/opt/miniconda3/bin:/opt/anaconda3/bin:/opt/homebrew/bin:/usr/local/bin:${PATH:-}"
export PYTHONPATH="${PWD}/backend:${PYTHONPATH:-}"
exec .venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 "$@"
