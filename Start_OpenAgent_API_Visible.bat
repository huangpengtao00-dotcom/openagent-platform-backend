@echo off
setlocal
title OpenAgent API - keep open
cd /d "%~dp0"
if not exist "artifacts\demo_logs" mkdir "artifacts\demo_logs"
if not exist "artifacts\interview_demo_runs" mkdir "artifacts\interview_demo_runs"
set "DATABASE_URL=sqlite:///./artifacts/interview_demo.db"
set "HARNESS_ROOT=%~dp0..\02_OpenAgent_Harness"
set "HARNESS_PYTHON=python"
set "HARNESS_PYTHONPATH=src"
set "HARNESS_RUNS_ROOT=artifacts\interview_demo_runs"
set "HARNESS_EXECUTOR=local"
set "ALLOW_REAL_LLM_CALLS=true"
set "REAL_API_BUDGET_LIMIT_CNY=1.0"
set "AUTO_START_RUNS=true"
set "ENABLE_REDIS=false"
set "QUEUE_BACKEND=db"
set "RUN_QUEUE_BACKEND=db"
echo [OpenAgent API] http://127.0.0.1:8000
echo [OpenAgent API] Local mode: HARNESS_EXECUTOR=local, QUEUE_BACKEND=db, ENABLE_REDIS=false
echo Keep this window open during the demo.
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
endlocal
