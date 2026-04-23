#!/usr/bin/env bash
# Run FastAPI from repository root (loads .env here, adds backend/ to PYTHONPATH).
# On Windows use: run_api.cmd   or   powershell -ExecutionPolicy Bypass -File .\run_api.ps1
# (Plain .\run_api.ps1 may be blocked by execution policy; run_api.cmd avoids that.)
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="${PWD}/backend:${PYTHONPATH:-}"
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
elif [ -x "backend/.venv/bin/python" ]; then
  PY="backend/.venv/bin/python"
else
  echo "No venv at .venv or backend/.venv. Create one and: pip install -r backend/requirements.txt" >&2
  exit 1
fi
echo "Open in browser: http://127.0.0.1:8000/health (not 0.0.0.0 - invalid in browsers)"
exec "$PY" -m uvicorn api.main:app --host 0.0.0.0 --port 8000 "$@"
