# OpenAgent Platform Backend

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
  harness_task_path = "C:/Users/hpt/Desktop/备份/OpenAgent-Harness-v1-final/benchmarks_realistic/retry-429-real/task.json"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/tasks -ContentType "application/json" -Body $task

$run = @{
  task_id = 1
  mode = "local"
  model = "scripted"
  allow_llm_calls = $false
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
```

## Real DeepSeek Mode

Real calls require both:

1. local environment contains `DEEPSEEK_API_KEY`
2. Platform env sets `ALLOW_REAL_LLM_CALLS=true`
3. request body sets `"mode": "api"` and `"allow_llm_calls": true`

This double opt-in prevents accidental spending. Do not commit `.env`.

## Verification

```powershell
pytest -q
```

The tests cover health, idempotent run creation, artifact serving, path sandboxing, rate limiting, cache jitter, cost parsing, and metrics aggregation.

