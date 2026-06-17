# Platform Evidence Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the Platform backend evidence chain for interviews by adding real process-level cancellation, Alembic migration workflow, one-command Docker Compose demo, and a safe manual DeepSeek evidence workflow.

**Architecture:** Keep Harness as the execution plane and Platform as the control plane. Platform will track cancellable Harness subprocesses by run id, preserve cancelled state after races, use Alembic for schema history, and document demos without committing secrets or real run artifacts.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, pytest, Docker Compose, Redis, Python subprocess.

---

### Task 1: Process-Level Cancellation

**Files:**
- Create: `app/process_manager.py`
- Modify: `app/harness_client.py`
- Modify: `app/services.py`
- Modify: `app/main.py`
- Test: `tests/test_worker.py`

- [ ] Write failing tests proving cancellation calls the process registry and cancelled runs are not overwritten by late Harness results.
- [ ] Implement a small `ProcessRegistry` that maps `run_id` to `subprocess.Popen` and terminates registered processes.
- [ ] Pass `run_id` through `execute_run` into `HarnessClient.run_task`.
- [ ] Make `cancel_run` call the registry, then mark the row cancelled.
- [ ] Make `execute_run` return early if a run is already cancelled and re-check before writing final pass/fail.
- [ ] Run `pytest tests/test_worker.py -q`.

### Task 2: Alembic Migration Workflow

**Files:**
- Modify: `pyproject.toml`
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/versions/0001_initial_schema.py`
- Modify: `app/db.py`
- Test: `tests/test_migrations.py`

- [ ] Add Alembic as a runtime dependency.
- [ ] Add a baseline migration for `tasks`, `runs`, and `usage`.
- [ ] Keep `init_db()` useful for tests/local boot while documenting Alembic as the production schema path.
- [ ] Add a smoke test that upgrades a temporary SQLite database to head and inspects expected tables/columns.
- [ ] Run `pytest tests/test_migrations.py -q`.

### Task 3: Docker Compose One-Command Demo

**Files:**
- Modify: `docker-compose.yml`
- Modify: `Dockerfile`
- Modify: `.env.example`
- Create: `docs/one_command_demo.md`
- Modify: `README.md`

- [ ] Add separate `api` and `worker` services, Redis, shared artifacts volume, and a harness bind mount.
- [ ] Set `AUTO_START_RUNS=false` for Compose so worker architecture is visible.
- [ ] Document the one-command path with `docker compose up --build`.
- [ ] Keep real LLM calls disabled by default.

### Task 4: DeepSeek Evidence Workflow

**Files:**
- Create: `scripts/run_deepseek_evidence.ps1`
- Create: `docs/deepseek_evidence_workflow.md`
- Modify: `.gitignore`
- Modify: `README.md`

- [ ] Add a manual PowerShell script that refuses to run without `DEEPSEEK_API_KEY`.
- [ ] Keep artifacts under ignored evidence/run directories.
- [ ] Document expected screenshots: API docs, run response, report page, `/metrics/cost`, terminal command.
- [ ] Do not execute a live API call unless the key is present and the user explicitly wants spending in this turn.

### Task 5: Full Verification

- [ ] Run `pytest -q`.
- [ ] Run Alembic migration smoke test.
- [ ] Check `git status --short`.
- [ ] Summarize remaining risks and exact interview answers.
