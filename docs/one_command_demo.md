# One-Command Demo

This demo runs the Platform as a real control plane split:

- `api`: FastAPI HTTP API, idempotency, rate limit, artifact and cost endpoints.
- `worker`: independent pending-run consumer that calls the Harness subprocess.
- `redis`: cache and rate-limit backend.
- `data/`: local SQLite database, ignored by git.
- `artifacts/`: Harness run outputs, ignored by git.

## 1. Prepare local env

```powershell
copy .env.example .env
```

Set `HOST_HARNESS_ROOT` in `.env` to your local Harness checkout. Example:

```env
HOST_HARNESS_ROOT=C:/Users/hpt/Desktop/备份/OpenAgent-Harness-v1-final
ALLOW_REAL_LLM_CALLS=false
AUTO_START_RUNS=false
```

Keep `ALLOW_REAL_LLM_CALLS=false` for normal demos. Do not put `.env` in git.

## 2. Start everything

```powershell
docker compose up --build
```

Open:

```text
http://127.0.0.1:8000/docs
```

## 3. Interview explanation

In this mode, `POST /runs` only creates a pending row. The separate worker process consumes it and calls the Harness CLI. This demonstrates the production-shaped architecture better than FastAPI `BackgroundTasks`.

Real DeepSeek calls are still disabled unless you deliberately set `ALLOW_REAL_LLM_CALLS=true` and submit a request with `allow_llm_calls=true`.
