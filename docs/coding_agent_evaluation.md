# Coding Agent Evaluation

This project can be presented as a small, interview-scale evaluation control plane for coding agents. It is not a large public benchmark service; its strength is that one task submission produces inspectable status, tests, patch, trace, report, token usage, cost, and timing evidence.

## What Gets Quantified

| Metric | Source | Interview value |
|---|---|---|
| Pass/fail | `Run.status`, `scorecard.json` | Basic task success comparison. |
| Test result | `test_result.json` | Shows the answer is verified by code, not manually judged. |
| Patch quality | `patch.diff` | Lets reviewers inspect whether the agent overfit or changed too much. |
| Trace quality | `trace.jsonl` | Shows action sequence and debugging path. |
| Report quality | `report.html` | Human-readable explanation of what happened. |
| Tokens | `Run.usage` | Measures model consumption. |
| Estimated cost | `Run.usage.estimated_cost_usd`, `/metrics/cost` | Measures budget impact by model. |
| Runtime | `started_at`, `finished_at`, `timeout_seconds` | Supports latency and timeout comparison. |
| Safety behavior | rejected real call when server switch is off | Shows real model spending is controlled. |

## Current Agent Profiles

| Profile | Mode | Model | Calls a model | Purpose |
|---|---|---|---|---|
| `Safe scripted retry-429` | `local` | `scripted` | No | Zero-cost baseline for stable demos and CI. |
| `Real DeepSeek retry-429` | `api` | `deepseek-v4-flash` | Yes | Low-cost real model proof on a compact bugfix task. |
| `Real DeepSeek config-loader` | `api` | `deepseek-v4-flash` | Yes | Second realistic example so the demo is not hard-coded to one task. |

## Latest Real Evaluation Evidence

Verified locally on 2026-06-17:

| Run | Profile | Status | Harness run id | Tokens | Estimated cost |
|---:|---|---|---|---:|---:|
| 2 | `Real DeepSeek retry-429` | `pass` | `deepseek-real-retry-429-32b3023d` | 4159 | `$0.00064274` |

`/metrics/cost` after two local real smoke runs:

| Model | Runs | Tokens | Estimated cost |
|---|---:|---:|---:|
| `deepseek-v4-flash` | 2 | 8502 | `$0.001337` |

## How To Compare Multiple Agents

Run the same task suite for each agent profile, then aggregate:

| Agent/model | Tasks | Passed | Pass rate | Avg tokens | Avg cost | Avg runtime | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| `scripted` | 1 | 1 | 100% | 0 | `$0` | fast | Baseline path, no model spend. |
| `deepseek-v4-flash` | 1 | 1 | 100% | 4159 | `$0.00064274` | ~7s | Real API run from Console. |

The next scalable step is to add more rows, not more architecture: run the same tasks against additional provider/model profiles and compare pass rate, cost, tokens, runtime, and patch quality.

## Screenshot Evidence To Prepare

1. Console profile selector showing all available profiles.
2. Console run page after a real API run, including status, mode, model, harness id, and usage.
3. `GET /runs/{id}` JSON with usage and artifact links.
4. `GET /runs/{id}/report` or `/scorecard`.
5. `/metrics/cost` showing model-level token and cost totals.

## Interview Answer

The platform separates task definition, agent execution, and evidence collection. A benchmark task can be run through different agent profiles, and every run records status, tests, patch, trace, report, tokens, cost, and timestamps. That makes it possible to compare coding agents by pass rate, cost, token usage, runtime, and inspectable patch quality while keeping real API spending behind a double opt-in.
