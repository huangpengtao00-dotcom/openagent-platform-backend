# OpenAgent Platform Backend

[![CI](https://github.com/huangpengtao00-dotcom/openagent-platform-backend/actions/workflows/ci.yml/badge.svg)](https://github.com/huangpengtao00-dotcom/openagent-platform-backend/actions/workflows/ci.yml)

FastAPI backend for service-wrapping OpenAgent Harness. The Harness executes coding-agent tasks; this Platform layer manages tasks, async runs, state, artifacts, idempotency, rate limiting, cache policy, and cost metrics.

## Scope

```text
OpenAgent Harness  = coding-agent execution, patch, tests, trace, report
Platform Backend   = API control plane, worker, state, artifacts, cost governance
```

The backend never stores API keys and never reimplements the agent loop. It calls the Harness CLI through subprocess:

```bash
python -m openagent_harness.cli run <task.json> --mode local --model scripted --runs ./artifacts/harness_runs
```

Related repository:

- OpenAgent Harness: https://github.com/huangpengtao00-dotcom/openagent-harness

## Run Locally

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e .[dev]
copy .env.example .env
pytest -q
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000/docs
```

## API Smoke

```powershell
$task = @{
  name = "retry-429-real"
  description = "Fix HTTP 429 retry logic"
  harness_task_path = "../OpenAgent-Harness-v1-final/benchmarks_realistic/retry-429-real/task.json"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/tasks -ContentType "application/json" -Body $task

$run = @{
  task_id = 1
  mode = "local"
  model = "scripted"
  allow_llm_calls = $false
  timeout_seconds = 120
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/runs -Headers @{"Idempotency-Key"="demo-001"} -ContentType "application/json" -Body $run
Invoke-RestMethod http://127.0.0.1:8000/runs/1
```

Artifact endpoints:

```text
GET /runs/{run_id}/report
GET /runs/{run_id}/patch
GET /runs/{run_id}/scorecard
GET /runs/{run_id}/test-result
GET /runs/{run_id}/trace
GET /metrics/cost
POST /runs/{run_id}/cancel
```

`POST /runs/{run_id}/cancel` is intended for pending local-worker runs. In production, running-process cancellation should be handled by the external worker layer.

## Real DeepSeek Mode

Real calls require both:

1. local environment contains `DEEPSEEK_API_KEY`
2. Platform env sets `ALLOW_REAL_LLM_CALLS=true`
3. request body sets `"mode": "api"` and `"allow_llm_calls": true`

This double opt-in prevents accidental spending. Do not commit `.env`.

For manual demos, keep total real API smoke spending under `DEMO_COST_BUDGET_CNY`. A single `deepseek-v4-flash` realistic task is expected to be tiny, but check `/metrics/cost` after every real run.

## Worker Mode

For local demos, `AUTO_START_RUNS=true` lets FastAPI schedule runs with `BackgroundTasks`. For a more production-like split, set:

```env
AUTO_START_RUNS=false
```

Then start the API and worker separately:

```powershell
uvicorn app.main:app --reload
python -m app.worker
```

In this mode, `POST /runs` only writes a pending run. The worker polls pending runs and executes Harness subprocesses.

## Verification

```powershell
pytest -q
```

The tests cover health, idempotent run creation, artifact serving, path sandboxing, rate limiting, cache jitter, cost parsing, and metrics aggregation.

## Cache Backend

With `ENABLE_REDIS=false`, cache and rate limiting use in-memory fallbacks for local demos. With `ENABLE_REDIS=true`, rate limiting and cache reads/writes use Redis; if Redis is unavailable, the service falls back to memory so local startup still works.

## Interview Materials

- `docs/architecture_diagram.md`
- `docs/demo_walkthrough.md`
- `docs/interview_playbook_cn.md`
