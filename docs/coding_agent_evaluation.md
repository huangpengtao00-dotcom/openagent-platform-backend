# Coding Agent Evaluation

This project is an interview-scale evaluation control plane for coding agents. The stable demo path is `scripted baseline`; real DeepSeek and retry runs are optional profiles behind explicit gates.

## What Gets Quantified

| Metric | Source | Interview value |
|---|---|---|
| Pass/fail | `Run.status`, `scorecard.json` | Basic task success comparison. |
| Score | `scorecard.json` | 0-100 quality signal beyond a boolean result. |
| Test result | `test_result.json` | Shows the answer is verified by code. |
| Patch size | `patch.diff`, `scorecard.json` | Shows whether the agent changed too much. |
| Changed files | `patch.diff`, `scorecard.json` | Helps detect broad or unsafe edits. |
| Trace | `trace.jsonl` | Shows execution sequence and debugging path. |
| Tokens/cost | `Run.usage`, `/metrics/cost` | Measures model consumption when real API is enabled. |
| Duration | `started_at`, `finished_at` | Supports latency and timeout comparison. |
| Failure type | Harness gate + Platform status | Makes failures diagnosable. |

## Current Profiles

| Profile | Mode | Model | Calls a model | Demo priority |
|---|---|---|---|---|
| `scripted baseline` | `local` | `scripted` | No | Required, stable, zero-cost. |
| `DeepSeek API` | `api` | `deepseek-v4-flash` | Yes | Optional after key + server opt-in + budget preflight. |
| `retry with context` | source run mode | source run model | Maybe | Optional after a failed/timeout run. |

## Evidence To Prepare

1. `Evaluation` page after `Refresh dashboard`.
2. `Run Control` after a `scripted baseline` run reaches `pass`.
3. `GET /evaluation/summary` JSON.
4. `GET /runs/{id}/scorecard`, `/patch`, `/test-result`, and `/trace`.
5. Optional: real DeepSeek evidence only if it was pre-run successfully.

## Interview Answer

The platform separates task definition, agent execution, and evidence collection. The same benchmark task can be run through different profiles, and every run records status, score, tests, patch, trace, report, tokens, cost, and timestamps. That makes coding-agent behavior reproducible and comparable while keeping real API spending behind explicit safety gates.
