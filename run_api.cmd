@echo off
REM Start API without PowerShell scripts (avoids ExecutionPolicy errors on .\run_api.ps1).
REM From PowerShell in this folder use:  .\run_api.cmd --reload   (not bare run_api.cmd)
cd /d "%~dp0"
if defined PYTHONPATH (
  set "PYTHONPATH=%~dp0backend;%PYTHONPATH%"
) else (
  set "PYTHONPATH=%~dp0backend"
)
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=%~dp0backend\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo No Python venv found. Create one at .venv or backend\.venv then:
  echo   pip install -r backend\requirements.txt
  exit /b 1
)
echo Open in browser: http://127.0.0.1:8000/health   ^(not 0.0.0.0 - that is invalid in Chrome^)
"%PY%" -m uvicorn api.main:app --host 0.0.0.0 --port 8000 %*
