# Demo Walkthrough

This walkthrough is optimized for interviews. Start with visible evidence, then use API JSON to prove the numbers behind the UI. Use scripted mode for repeatable demos; use real DeepSeek mode only when a small budget has been explicitly confirmed.

## 1. Start The Live Demo

Terminal 1:

```powershell
copy .env.example .env
uvicorn app.main:app --reload
```

Terminal 2:

```powershell
cd frontend
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

## 2. Capture The P0 Evidence

Capture these screenshots before explaining architecture:

1. **Profile selector**: show `Safe scripted retry-429`, `Real DeepSeek retry-429`, and `Real DeepSeek config-loader`.
2. **Real run page**: show final `pass`, `mode=api`, `model=deepseek-v4-flash`, harness id, and usage.
3. **Run JSON**: open `http://127.0.0.1:8000/runs/{run_id}` and show status, timestamps, tokens, cost, and artifact links.
4. **Artifact**: open `http://127.0.0.1:8000/runs/{run_id}/report` or `/scorecard`.
5. **Cost metrics**: open `http://127.0.0.1:8000/metrics/cost`.

Latest verified local example:

| Field | Value |
|---|---|
| Run | `2` |
| Status | `pass` |
| Model | `deepseek-v4-flash` |
| Harness run id | `deepseek-real-retry-429-32b3023d` |
| Tokens | `4159` |
| Estimated cost | `$0.00064274` |

## 3. Safe Scripted Demo Path

Use this when you do not want to spend API credits:

1. In the Console, open **运行**.
2. Select `Safe scripted retry-429`.
3. Click **启动所选评测**.
4. Refresh until the run reaches `pass`.
5. Open **产物** and **成本** to show the same Platform artifact and cost flow without model spend.

Interview point:

```text
Scripted mode exercises the same Platform -> Harness lifecycle but does not call a model. It is the stable demo and CI path.
```

## 4. Real DeepSeek Demo Path

Only use this when the budget is confirmed and the backend process has:

```env
ALLOW_REAL_LLM_CALLS=true
DEEPSEEK_API_KEY=...
```

Then:

1. In the Console, select `Real DeepSeek retry-429`.
2. Click **启动所选评测**.
3. Refresh the run.
4. Capture the run page and `/metrics/cost`.

Interview point:

```text
Real API mode requires both the server switch and request-level allow_llm_calls=true. This prevents accidental spend during normal demos and automation.
```

## 5. API Commands For Backup

Create a task:

```powershell
$task = @{
  name = "retry-429-real"
  description = "Fix HTTP 429 retry logic"
  harness_task_path = "benchmarks_realistic/retry-429-real/task.json"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/tasks -ContentType "application/json" -Body $task
```

Create a safe local run:

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

Inspect results:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/runs/1
Invoke-RestMethod http://127.0.0.1:8000/runs/1/scorecard
Invoke-RestMethod http://127.0.0.1:8000/metrics/cost
```

## 6. Standalone Worker Mode

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
