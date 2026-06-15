# Demo Walkthrough

This walkthrough uses local mode first. It does not spend API credits.

## 1. Start API

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
copy .env.example .env
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000/docs
```

## 2. Create A Task

```powershell
$task = @{
  name = "retry-429-real"
  description = "Fix HTTP 429 retry logic"
  harness_task_path = "../OpenAgent-Harness-v1-final/benchmarks_realistic/retry-429-real/task.json"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/tasks -ContentType "application/json" -Body $task
```

## 3. Start A Local Run

```powershell
$run = @{
  task_id = 1
  mode = "local"
  model = "scripted"
  allow_llm_calls = $false
  timeout_seconds = 120
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/runs `
  -Headers @{"Idempotency-Key"="demo-001"} `
  -ContentType "application/json" `
  -Body $run
```

## 4. Inspect Results

```powershell
Invoke-RestMethod http://127.0.0.1:8000/runs/1
Invoke-RestMethod http://127.0.0.1:8000/runs/1/scorecard
Invoke-RestMethod http://127.0.0.1:8000/metrics/cost
```

Browser endpoints:

```text
http://127.0.0.1:8000/runs/1/report
http://127.0.0.1:8000/runs/1/patch
```

## 5. Standalone Worker Mode

Set:

```env
AUTO_START_RUNS=false
```

Run two terminals:

```powershell
uvicorn app.main:app --reload
python -m app.worker
```

This shows the production-style split: API writes pending runs; worker consumes and executes them.

## 6. Real DeepSeek Smoke

Only run this manually with a small budget.

Requirements:

```env
ALLOW_REAL_LLM_CALLS=true
DEEPSEEK_API_KEY=...
```

Request body:

```json
{
  "task_id": 1,
  "mode": "api",
  "model": "deepseek-v4-flash",
  "allow_llm_calls": true,
  "timeout_seconds": 180
}
```

After every real run:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/metrics/cost
```
