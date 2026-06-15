# Backend Design

OpenAgent Platform Backend is the control plane for OpenAgent Harness. It accepts task definitions, creates run records, schedules background execution, tracks state transitions, stores cost usage, and exposes run artifacts through API endpoints.

## Boundaries

The Harness owns code editing, tool execution, tests, scoring, and reports. The Platform owns API resources, state, idempotency, worker orchestration, rate limiting, artifact access, and cost aggregation.

## State Machine

```text
pending -> running -> pass
pending -> running -> fail
pending -> running -> timeout
pending/running -> cancelled
```

The local demo can use FastAPI BackgroundTasks through `AUTO_START_RUNS=true`. For a more production-like split, set `AUTO_START_RUNS=false` and run `python -m app.worker`; the API writes pending rows and the worker consumes them. `timeout_seconds` is forwarded to the Harness subprocess so one run cannot hang forever.

## Persistence

The default database is SQLite for local demos. SQLAlchemy keeps the model compatible with PostgreSQL for later deployment.

`POST /runs/{run_id}/cancel` supports cancelling a pending run in the local worker model. A production worker should extend this with process-level cancellation for already running subprocesses.
