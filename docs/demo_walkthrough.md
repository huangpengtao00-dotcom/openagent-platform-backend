# Demo Walkthrough

This walkthrough is optimized for a stable interview demo. Start with `scripted baseline`; use real DeepSeek only after a successful preflight.

## 1. Start

From the bundle root, double-click:

```text
双击启动_OpenAgent_Demo.bat
```

Or from this backend directory:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_demo.ps1
```

By default this starts a clean interview demo database at `artifacts/interview_demo.db` and writes Harness outputs under `artifacts/interview_demo_runs`. Use `-KeepDemoData` only when you intentionally want to reuse an existing demo backend.

Open:

```text
http://127.0.0.1:5173
```

## 2. Required Console Path

1. Open `Evaluation`.
2. Click `Refresh dashboard`.
3. Open `Run Control`.
4. Select `scripted baseline`.
5. Click `Start evaluation`.
6. Click `Refresh` until status is `pass`.
7. Return to `Evaluation` and refresh again.
8. Open `Artifacts` and inspect scorecard, patch, test-result, trace, and report.

Interview point:

```text
Scripted mode exercises the same Platform -> Harness lifecycle but does not call a model. It is the stable demo and CI path.
```

## 3. API Backup

Create a task:

```powershell
$task = @{
  name = "retry-429-real"
  description = "Fix HTTP 429 retry logic"
  harness_task_path = "benchmarks_realistic/retry-429-real/task.json"
} | ConvertTo-Json

$createdTask = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/tasks -ContentType "application/json" -Body $task
```

Create a safe local run:

```powershell
$run = @{
  task_id = $createdTask.task_id
  mode = "local"
  model = "scripted"
  allow_llm_calls = $false
  timeout_seconds = 120
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/runs `
  -Headers @{"Idempotency-Key"="demo-scripted-baseline"} `
  -ContentType "application/json" `
  -Body $run
```

Inspect:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/evaluation/summary
Invoke-RestMethod http://127.0.0.1:8000/runs/1
Invoke-RestMethod http://127.0.0.1:8000/runs/1/scorecard
```

## 4. Real DeepSeek Optional Path

Only use this when:

```env
ALLOW_REAL_LLM_CALLS=true
DEEPSEEK_API_KEY=<your_deepseek_api_key>
REAL_API_BUDGET_LIMIT_CNY=1.0
```

Then select `DeepSeek API` in the console. If the backend rejects the request, explain that this is expected safety behavior when server opt-in, request opt-in, key, or budget is missing.

## 5. Worker Mode Optional Path

Set:

```env
AUTO_START_RUNS=false
```

Run two terminals:

```powershell
uvicorn app.main:app --reload
python -m app.worker
```

This shows the production-shaped split: API writes pending runs; worker consumes and executes them.
