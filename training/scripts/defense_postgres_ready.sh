#!/usr/bin/env bash
# Start Postgres (Docker) and wait until it accepts connections.
# From repo root:
#   bash training/scripts/defense_postgres_ready.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed or not in PATH." >&2
  exit 1
fi

echo "Starting Postgres (docker compose)..."
docker compose up -d postgres

echo "Waiting for Postgres to accept connections..."
for i in $(seq 1 45); do
  if docker compose exec -T postgres pg_isready -U rezume -d rezumeai >/dev/null 2>&1; then
    echo "Postgres is ready."
    echo ""
    echo "Set in your .env:"
    echo "  DATABASE_URL=postgresql+psycopg2://rezume:rezume@localhost:5432/rezumeai"
    echo ""
    echo "Then:"
    echo "  python training/scripts/sync_enriched_to_postgres.py"
    echo "  PYTHONPATH=backend uvicorn api.main:app --host 0.0.0.0 --port 8000"
    exit 0
  fi
  sleep 1
done

echo "Timed out waiting for Postgres. Is Docker Desktop running?" >&2
exit 1
