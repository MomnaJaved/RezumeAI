# Run FastAPI from repository root (same as run_api.sh: PYTHONPATH, .venv, port 8000).
#
# If you see "not digitally signed" / execution policy errors on .\run_api.ps1, use either:
#   .\run_api.cmd --reload
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\run_api.ps1 --reload
#
# Usage: .\run_api.ps1
#        .\run_api.ps1 --reload
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root
$backend = Join-Path $root "backend"
if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$backend;$env:PYTHONPATH"
} else {
    $env:PYTHONPATH = $backend
}
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    $py = Join-Path $root "backend\.venv\Scripts\python.exe"
}
if (-not (Test-Path $py)) {
    Write-Error "No venv at .venv or backend\.venv. Create one and: pip install -r backend\requirements.txt"
}
Write-Host "Open in browser: http://127.0.0.1:8000/health (not 0.0.0.0 - invalid in browsers)"
& $py -m uvicorn api.main:app --host 0.0.0.0 --port 8000 @args
