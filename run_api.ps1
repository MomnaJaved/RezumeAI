# Start FastAPI from repository root (Windows). Loads backend/ on PYTHONPATH.
# Usage: .\run_api.ps1
# Optional: .\run_api.ps1 --port 8001
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:PYTHONPATH = (Join-Path $PWD "backend")
$py = Join-Path $PWD ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Error "Missing $py. From repo root: python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt (see docs/HOW_TO_RUN.md)"
}
& $py -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000 @args
