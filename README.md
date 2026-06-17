# OpenAgent Platform Backend

[![CI](https://github.com/huangpengtao00-dotcom/openagent-platform-backend/actions/workflows/ci.yml/badge.svg)](https://github.com/huangpengtao00-dotcom/openagent-platform-backend/actions/workflows/ci.yml)

FastAPI backend for service-wrapping OpenAgent Harness. The Harness executes coding-agent tasks; this Platform layer manages tasks, async runs, state, artifacts, idempotency, rate limiting, cache policy, and cost metrics.

## Demo Evidence

| Area | Current Evidence |
|---|---:|
| Automated tests | backend `31 passed`, frontend `13 passed` |
| Run states | `pending`, `running`, `pass`, `fail`, `timeout`, `cancelled` |
| Artifact endpoints | 5 run artifacts + cost metrics |
| Cost fields | prompt/completion/total tokens + estimated USD |
| Local safety | SQLite + in-memory cache/rate-limit fallback |
| Real-call guard | env + request double opt-in |
| Process cancel | run status + Harness subprocess termination |
| Evaluation UI | safe scripted profile + real DeepSeek profiles |

Highest-priority interview evidence:

1. Console screenshot after a real API run: status, mode, model, harness id, and usage.
2. `GET /runs/{id}` JSON for the same run: timestamps, tokens, cost, and artifact links.
3. `/runs/{id}/report` or `/scorecard` screenshot: inspectable agent output.
4. `/metrics/cost` screenshot or JSON: model-level run, token, and cost totals.

Reference Harness smoke:

| Task | Profile | Result | Tokens | Estimated Cost |
|---|---|---|---:|---:|
| HTTP 429 retry fix | `Real DeepSeek retry-429` | pass | 4159 | `$0.00064274` |

```mermaid
flowchart LR
    U["POST /runs"] --> I["Idempotency-Key"]
    I --> R["Rate limit"]
    R --> P["pending run"]
    P --> W["worker / BackgroundTasks"]
    W --> H["OpenAgent Harness"]
    H --> A["artifacts"]
    A --> S["status + usage"]
    S --> M["/metrics/cost"]
    A --> Q["report / patch / scorecard / trace"]
```

## Scope

```text
OpenAgent Harness  = coding-agent execution, patch, tests, trace, report
Platform Backend   = API control plane, worker, state, artifacts, cost governance
```

The backend never stores API keys and never reimplements the agent loop. It calls the Harness CLI through subprocess:

```bash
python -m openagent_harness.cli run <task.json> --mode local --model scripted --runs ./artifacts/harness_runs
```

`harness_task_path` is constrained to `HARNESS_ROOT`. Relative task paths are resolved under `HARNESS_ROOT`; absolute task paths must already be inside that directory. This prevents the API from being used to point the Harness at arbitrary local files.

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

## Platform Console

The optional frontend console lives in `frontend/`. It is a lightweight React/Vite UI for showing Platform evidence: architecture boundary, run state, cancellation, artifacts, and cost metrics. It does not store API keys or call LLM providers directly.

Static presentation mode:

```powershell
cd frontend
npm install
npm run build
```

Then open:

```text
frontend/dist/index.html
```

The built HTML uses relative assets, so it can be opened directly like a static zip demo. In this mode it shows built-in sample data and does not require the backend.

Live API mode:

```powershell
cd frontend
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

The Vite dev server proxies `/api/*` to `http://127.0.0.1:8000/*`, so start the FastAPI backend separately when using live API actions. Without the backend, the console still opens with demo data for presentation.

One-command local demo:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_demo.ps1
```

This starts the FastAPI backend and the Vite Console in separate terminals, opens `http://127.0.0.1:5173`, and keeps real model calls disabled with `ALLOW_REAL_LLM_CALLS=false`.

The live Console run page includes evaluation profiles:

- `Safe scripted retry-429`: zero-cost baseline.
- `Real DeepSeek retry-429`: low-cost real API smoke for a compact bugfix task.
- `Real DeepSeek config-loader`: second realistic task so the demo is not hard-coded to one example.

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

`POST /runs/{run_id}/cancel` marks pending/running runs as `cancelled`. In local BackgroundTasks mode, the API process registry can terminate the active Harness subprocess directly. In API/worker split mode, the worker polls the database while the subprocess is running and terminates its own Harness process as soon as it observes cancellation. In a multi-machine production deployment, the same idea should move to the queue/worker control layer.

## Database Migrations

Local tests can still create tables directly through SQLAlchemy metadata, but the operational schema path is Alembic:

```powershell
alembic upgrade head
```

The baseline migration creates `tasks`, `runs`, and `usage`, including the idempotency constraint and `timeout_seconds`.

## Real DeepSeek Mode

Real calls require both:

1. local environment contains `DEEPSEEK_API_KEY`
2. Platform env sets `ALLOW_REAL_LLM_CALLS=true`
3. request body sets `"mode": "api"` and `"allow_llm_calls": true`

This double opt-in prevents accidental spending. Do not commit `.env`.

For manual demos, keep total real API smoke spending under `DEMO_COST_BUDGET_CNY`. A single `deepseek-v4-flash` realistic task is expected to be tiny, but check `/metrics/cost` after every real run.

## Scripted Mode vs API Mode

Use scripted mode for stable demos, interviews, and CI:

```json
{
  "mode": "local",
  "model": "scripted",
  "allow_llm_calls": false
}
```

Scripted mode does not call a model provider. It exercises the same Platform control flow and Harness artifact flow, but keeps cost at zero and avoids API-key risk.

Use API mode only for explicit low-budget smoke tests:

```json
{
  "mode": "api",
  "model": "deepseek-v4-flash",
  "allow_llm_calls": true
}
```

API mode needs `ALLOW_REAL_LLM_CALLS=true` and a local provider key such as `DEEPSEEK_API_KEY`. Keep keys in local environment or `.env`; never send them through request bodies, never store them in the database, and never commit them. `RunCreate.mode` only accepts `"local"` or `"api"`.

## Release Bundles

Build two local handoff folders:

```powershell
.\scripts\build_clean_release.ps1
```

Output:

```text
C:\Users\hpt\Documents\实习项目\OpenAgent-Release-Bundles\openagent-platform-runnable
C:\Users\hpt\Documents\实习项目\OpenAgent-Release-Bundles\openagent-platform-interview-clean
```

Both bundles exclude `.env`, `.venv`, `node_modules`, `runs`, `artifacts`, local databases, `.git`, zip files, logs, and cache directories. The runnable bundle includes backend and Harness source for local setup; the interview-clean bundle is the safer folder to share or zip.

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

For a containerized API/worker/Redis split:

```powershell
copy .env.example .env
# Set HOST_HARNESS_ROOT to your local Harness checkout.
docker compose up --build
```

## Verification

```powershell
pytest -q
```

Expected result:

```text
31 passed
```

The tests cover health, idempotent run creation, artifact serving, path sandboxing, rate limiting, cache jitter, cost parsing, timeout classification, worker execution, and metrics aggregation.

## Cache Backend

With `ENABLE_REDIS=false`, cache and rate limiting use in-memory fallbacks for local demos. With `ENABLE_REDIS=true`, rate limiting and cache reads/writes use Redis; if Redis is unavailable, the service falls back to memory so local startup still works.

## Interview Materials

- `docs/architecture_diagram.md`
- `docs/coding_agent_evaluation.md`
- `docs/demo_evidence.md`
- `docs/demo_walkthrough.md`
- `docs/one_command_demo.md`
- `docs/deepseek_evidence_workflow.md`
- `docs/interview_playbook_cn.md`
