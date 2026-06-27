# OpenAgent Benchmark Catalog - 15 Tasks

Purpose: provide interview-ready tasks across easy, medium, and hard code-difficulty levels. These tasks are meant for `New Evaluation`: paste source, let the backend judge difficulty, confirm draft, then run DeepSeek / NewAPI 5.4 / NewAPI 5.5 in parallel.

## Easy

| ID | Name | What It Tests | Expected Difficulty |
|---|---|---|---|
| E1 | Duration parser | String parsing, empty input, invalid unit | easy |
| E2 | Percent clamp | Numeric boundaries, None handling | easy |
| E3 | Slug normalize | Text normalization, repeated separators | easy |
| E4 | Retryable status | Simple HTTP status classification | easy |
| E5 | Pagination bounds | Off-by-one page slicing | easy |

## Medium

| ID | Name | What It Tests | Expected Difficulty |
|---|---|---|---|
| M1 | Config merge | Nested dict merge without mutating defaults | medium |
| M2 | Role policy evaluator | Class state, branch rules, deny reasons | medium |
| M3 | Artifact search filters | Multiple filters, pagination, missing fields | medium |
| M4 | Usage cost rollup | Aggregation by provider/model, zero-cost rows | medium |
| M5 | Idempotency key validator | Repeated request semantics, conflict detection | medium |

## Hard

| ID | Name | What It Tests | Expected Difficulty |
|---|---|---|---|
| H1 | Async retry client | async/await, HTTP 429, timeout, retry budget | hard |
| H2 | Worker queue claim | pending/running state, duplicate enqueue, cancellation | hard |
| H3 | Artifact path resolver | IO/path boundary, traversal defense, missing file feedback | hard |
| H4 | Multi-file evaluation routing | Router/service/storage split, cross-file edits | hard |
| H5 | Cost dashboard reconciliation | DB aggregation, provider labels, frontend display consistency | hard |

## Demo Strategy

Use this sequence tomorrow:

1. Start with E1 to show the happy path and `easy` difficulty.
2. Use M1 or M3 to show `medium`, branch reasoning, and better tests.
3. Use H1 or H3 to show `hard`, risk factors, and why the system recommends longer budget / stricter QualityGate.
4. Run one selected task across DeepSeek / NewAPI 5.4 / NewAPI 5.5.
5. Open History -> View Matrix -> Evidence to show patch, scorecard, trace, cost.

Note: running all 15 tasks across all real models can trigger provider budget or 429 limits. For interview reliability, keep 15 tasks as the benchmark catalog and run 1-3 selected tasks live.

## Files

- `benchmark_templates/templates.json`: five copy-paste demo templates with source code.
- `benchmark_templates/benchmark_catalog_15.json`: compact catalog for all 15 benchmark ideas.
- `scripts/check_benchmark_templates.ps1`: calls `POST /evaluation-drafts` and checks backend difficulty output for the five demo templates.

Latest template difficulty check:

```text
template_easy_duration_parser     -> easy
template_easy_pagination_bounds   -> easy
template_medium_config_merge      -> medium
template_medium_artifact_search   -> medium
template_hard_async_retry_client  -> hard
```
