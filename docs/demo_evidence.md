# Demo Evidence

This document lists evidence to capture for the interview. The required evidence is the stable `scripted baseline` chain. Real DeepSeek evidence is optional and should not be claimed unless it was generated on the current machine.

## P0 Evidence

| Priority | Evidence | Why it matters |
|---:|---|---|
| P0 | `Evaluation` page after refresh | Shows quantitative dashboard and profile/task comparison. |
| P0 | `Run Control` after `scripted baseline` reaches `pass` | Shows the platform can start and observe a run. |
| P0 | `GET /evaluation/summary` | Shows aggregation is produced by the backend, not static UI text. |
| P0 | `/runs/{id}/scorecard` | Shows score, status, patch size, changed files, tests, and failure type. |
| P0 | `/runs/{id}/patch`, `/test-result`, `/trace` | Shows inspectable code diff, test evidence, and execution trace. |

## Optional Evidence

| Evidence | When to capture |
|---|---|
| Real DeepSeek run | Only after `ALLOW_REAL_LLM_CALLS=true`, `DEEPSEEK_API_KEY` exists, and the 1.0 CNY budget gate is understood. |
| Retry closure | Only after a failed/timeout run exists and retry has been pre-tested. |
| Custom task | Only after the main baseline path is already stable. |

## Screenshot Checklist

1. Console: `Evaluation` dashboard with totals and task-level table.
2. Console: `Run Control` with `scripted baseline` selected.
3. API: `GET /evaluation/summary`.
4. API: `GET /runs/{id}/scorecard`.
5. Artifact: patch/test-result/trace.
6. Guardrail proof: API-mode still requires request opt-in, a local provider key, and the budget gate even though the backend LLM gate defaults to `ALLOW_REAL_LLM_CALLS=true`.

## Latest Verification Commands

```text
Backend: python -m pytest -q
Frontend: cmd /c npm test -- --run
Frontend build: cmd /c npm run build
Harness smoke: scripts\smoke_retry_429.cmd
```

## Artifact Contract

| Endpoint | Purpose | Response Type |
|---|---|---|
| `GET /runs/{run_id}/report` | Human-readable run report | HTML |
| `GET /runs/{run_id}/patch` | Code diff | text/plain |
| `GET /runs/{run_id}/scorecard` | Machine-readable score | JSON |
| `GET /runs/{run_id}/test-result` | Test evidence | JSON |
| `GET /runs/{run_id}/trace` | Tool/action timeline | JSONL text |

## Interview Summary

The project is positioned as a coding-agent evaluation control plane. It makes agent runs observable through state, artifacts, scores, failure types, and cost metrics, while real LLM calls remain governed by request opt-in, local provider keys, budget checks, idempotency, rate limiting, and timeout handling.
