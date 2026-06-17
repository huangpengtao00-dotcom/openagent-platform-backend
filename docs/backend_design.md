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

Running-process cancellation has two layers. In same-process demo mode, an in-process registry keyed by Platform `run_id` lets the API terminate the active Harness subprocess. In API/worker split mode, the API marks the row cancelled and the worker polls the database while the subprocess is running, then terminates its own Harness process. `execute_run` re-checks cancelled state before writing final status so late subprocess results cannot overwrite cancellation.

## Persistence

The default database is SQLite for local demos. SQLAlchemy keeps the model compatible with PostgreSQL for later deployment. Alembic owns the operational migration path; `alembic upgrade head` creates the baseline schema.

In a multi-machine production worker pool, the same cancellation concept should be moved from an in-memory registry to queue/worker control, such as Celery revoke, Redis Stream worker ownership, or a durable run lease table.
