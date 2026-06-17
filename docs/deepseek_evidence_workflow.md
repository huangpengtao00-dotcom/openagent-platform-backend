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
$env:DEEPSEEK_API_KEY="sk-..."
.\scripts\run_deepseek_evidence.ps1 -Live -ConfirmSpend
```

The script writes JSON evidence under `evidence/deepseek-YYYYMMDD-HHMMSS/`, which is ignored by git.

## Screenshots To Capture

Capture these five screenshots for the interview evidence pack:

1. Terminal output from `scripts/run_deepseek_evidence.ps1`.
2. `03-run-created.json`, showing `mode=api`, `model=deepseek-v4-flash`, and `allow_llm_calls=true`.
3. `04-run-latest.json`, showing final run status and artifact links.
4. Browser page: `/runs/{run_id}/report`.
5. Browser/API response: `/metrics/cost`, showing tokens and estimated USD.

## Interview Answer

The project uses a double opt-in for real model calls: the server must set `ALLOW_REAL_LLM_CALLS=true`, and the request must set `allow_llm_calls=true`. This prevents accidental spending during local demos and scheduled maintenance.
