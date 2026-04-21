@echo off
REM Run FastAPI from repo root (same as run_api.sh) — Windows, no bash required.
cd /d "%~dp0"
set PYTHONPATH=%CD%\backend;%PYTHONPATH%
".venv\Scripts\python.exe" -m uvicorn api.main:app --host 0.0.0.0 --port 8000 %*
