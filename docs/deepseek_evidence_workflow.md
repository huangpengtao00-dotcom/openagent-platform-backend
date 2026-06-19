# DeepSeek Evidence Workflow

Use this only for a manual, low-cost proof run. The automation and default Docker demo must not spend real model credits.

## Preconditions

- Platform API is running.
- Worker is running if `AUTO_START_RUNS=false`.
- `ALLOW_REAL_LLM_CALLS=true` is set in the Platform process.
- `DEEPSEEK_API_KEY` is set locally, not committed.
- Demo budget is confirmed.

## Run

```powershell
$env:DEEPSEEK_API_KEY="<your_deepseek_api_key>"
.\scripts\run_deepseek_evidence.ps1 -Live -ConfirmSpend
```

The script writes JSON evidence under `evidence/deepseek-YYYYMMDD-HHMMSS/`, which is ignored by git.

## Screenshots To Capture

Capture these screenshots first; they are the highest-value interview evidence:

1. Console run page after selecting `Real DeepSeek retry-429`, showing `mode=api`, `model=deepseek-v4-flash`, `allow_llm_calls=true`, final `pass`, harness id, and usage.
2. `GET /runs/{run_id}` JSON, showing final status, timestamps, token usage, estimated USD, and artifact links.
3. Browser page: `/runs/{run_id}/report` or API response from `/runs/{run_id}/scorecard`.
4. Browser/API response: `/metrics/cost`, showing model-level runs, tokens, and estimated USD.
5. Console profile selector, showing the safe scripted baseline and real API profiles.
6. Optional terminal output from `scripts/run_deepseek_evidence.ps1`.

Latest verified local example from 2026-06-17:

| Field | Value |
|---|---|
| Run | `2` |
| Status | `pass` |
| Model | `deepseek-v4-flash` |
| Harness run id | `deepseek-real-retry-429-32b3023d` |
| Tokens | `4159` |
| Estimated cost | `$0.00064274` |

## Interview Answer

Real model calls are enabled by the backend default gate `ALLOW_REAL_LLM_CALLS=true`, but they still require API-mode request opt-in, a local provider key, and the budget gate. This keeps the interview demo honest without reverting to a hidden disabled-by-default path.
