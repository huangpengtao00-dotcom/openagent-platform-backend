from __future__ import annotations

import json
from pathlib import Path

from app.main import harness_client


class FakeHarnessClient:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.calls = 0

    def run_task(self, task_spec_path: str, mode: str, model: str, runs_root: str, allow_llm_calls: bool, **kwargs):
        from app.harness_client import HarnessRunResult

        self.calls += 1
        self.run_dir.mkdir(parents=True, exist_ok=True)
        repo = self.run_dir / "repo"
        repo.mkdir(exist_ok=True)
        (repo / "app.py").write_text("def ok():\n    return True\n", encoding="utf-8")
        (repo / "test_app.py").write_text("from app import ok\n\ndef test_ok():\n    assert ok()\n", encoding="utf-8")
        (repo / ".env").write_text("DEEPSEEK_API_KEY=do-not-show\n", encoding="utf-8")
        (repo / "api_token.txt").write_text("do-not-show\n", encoding="utf-8")
        (repo / "large.py").write_text("x = 1\n" * 20_000, encoding="utf-8")
        (self.run_dir / "report.html").write_text("<h1>ok</h1>", encoding="utf-8")
        (self.run_dir / "patch.diff").write_text("diff --git a/app.py b/app.py\n", encoding="utf-8")
        (self.run_dir / "scorecard.json").write_text(json.dumps({"status": "pass", "score": 100}), encoding="utf-8")
        (self.run_dir / "test_result.json").write_text(json.dumps({"tests_passed": True}), encoding="utf-8")
        (self.run_dir / "api_agent_run.json").write_text(
            json.dumps({"strategy": {"tier": "simple", "max_steps": 4, "prompt_char_budget": 16000}, "steps": []}),
            encoding="utf-8",
        )
        (self.run_dir / "trace.jsonl").write_text(
            json.dumps({"observation": {"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "estimated_cost_usd": 0.001}}}) + "\n",
            encoding="utf-8",
        )
        return HarnessRunResult("fake-run", self.run_dir, "pass", None, {
            "model": model,
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
            "estimated_cost_usd": 0.001,
        })


class CapturingHarnessClient(FakeHarnessClient):
    def __init__(self, run_dir: Path) -> None:
        super().__init__(run_dir)
        self.last_kwargs = {}

    def run_task(self, task_spec_path: str, mode: str, model: str, runs_root: str, allow_llm_calls: bool, **kwargs):
        self.last_kwargs = {
            "task_spec_path": task_spec_path,
            "mode": mode,
            "model": model,
            "runs_root": runs_root,
            "allow_llm_calls": allow_llm_calls,
            **kwargs,
        }
        return super().run_task(task_spec_path, mode, model, runs_root, allow_llm_calls, **kwargs)


class OneFailureHarnessClient(FakeHarnessClient):
    def run_task(self, task_spec_path: str, mode: str, model: str, runs_root: str, allow_llm_calls: bool, **kwargs):
        from app.harness_client import HarnessRunResult

        result = super().run_task(task_spec_path, mode, model, runs_root, allow_llm_calls, **kwargs)
        if self.calls == 2:
            return HarnessRunResult(result.harness_run_id, result.artifacts_dir, "fail", "TestFailed", result.usage)
        return result


def create_task(client):
    res = client.post("/tasks", json={"name": "retry", "harness_task_path": "task.json"})
    assert res.status_code == 200
    return res.json()["task_id"]


def mark_run_status(run_id: int, status: str, failure_type: str | None = None, error_message: str | None = None) -> None:
    from app.db import get_db
    from app.main import app
    from app.models import Run

    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        run = db.get(Run, run_id)
        assert run is not None
        run.status = status
        run.failure_type = failure_type
        run.error_message = error_message
        db.commit()
    finally:
        db_gen.close()


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_demo_status_reports_harness_root(client, tmp_path):
    body = client.get("/demo/status").json()

    assert body["status"] == "ok"
    assert body["harness_root"] == str(tmp_path / "harness")
    assert body["allow_real_llm_calls"] is False
    assert body["real_api_budget_limit_cny"] == 1.0
    assert body["queue_backend_active"] in {"db", "redis"}
    assert body["harness_executor"] == "local"
    assert body["redis_available"] is False


def test_create_task_rejects_path_outside_harness_root(client, tmp_path):
    outside = tmp_path / "outside" / "task.json"

    res = client.post("/tasks", json={"name": "escape", "harness_task_path": str(outside)})

    assert res.status_code == 400
    assert "allowed harness root" in res.json()["detail"]


def test_create_task_stores_relative_path_inside_harness_root(client, tmp_path):
    res = client.post("/tasks", json={"name": "retry", "harness_task_path": "benchmarks/retry/task.json"})

    assert res.status_code == 200
    body = res.json()
    assert body["harness_task_path"] == str((tmp_path / "harness" / "benchmarks" / "retry" / "task.json").resolve())


def test_post_run_rejects_unknown_mode(client):
    task_id = create_task(client)

    res = client.post("/runs", json={"task_id": task_id, "mode": "dry-run"})

    assert res.status_code == 422


def test_run_idempotency_and_artifacts(client, tmp_path, monkeypatch):
    fake = FakeHarnessClient(tmp_path / "harness_runs" / "fake-run")
    monkeypatch.setattr("app.main.harness_client", fake)
    task_id = create_task(client)
    body = {"task_id": task_id, "mode": "local", "model": "scripted", "allow_llm_calls": False}

    first = client.post("/runs", json=body, headers={"Idempotency-Key": "demo"}).json()
    second = client.post("/runs", json=body, headers={"Idempotency-Key": "demo"}).json()

    assert first["run_id"] == second["run_id"]
    assert fake.calls == 1
    assert client.get(f"/runs/{first['run_id']}").json()["status"] == "pass"
    assert client.get(f"/runs/{first['run_id']}/report").text == "<h1>ok</h1>"
    assert "diff --git" in client.get(f"/runs/{first['run_id']}/patch").text
    assert client.get(f"/runs/{first['run_id']}/scorecard").json()["score"] == 100
    assert client.get(f"/runs/{first['run_id']}/test-result").json()["tests_passed"] is True
    assert "usage" in client.get(f"/runs/{first['run_id']}/trace").text


def test_idempotency_key_rejects_different_run_request(client):
    first_task_id = create_task(client)
    second = client.post("/tasks", json={"name": "other", "harness_task_path": "other-task.json"})
    assert second.status_code == 200
    second_task_id = second.json()["task_id"]

    first = client.post("/runs", json={"task_id": first_task_id}, headers={"Idempotency-Key": "same-key"})
    conflict = client.post("/runs", json={"task_id": second_task_id}, headers={"Idempotency-Key": "same-key"})

    assert first.status_code == 200
    assert conflict.status_code == 409
    assert "different run request" in conflict.json()["detail"]


def test_run_catalog_lists_task_context_and_artifact_links(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.harness_client", FakeHarnessClient(tmp_path / "harness_runs" / "fake-run"))
    task_id = create_task(client)
    created = client.post("/runs", json={"task_id": task_id}, headers={"Idempotency-Key": "catalog"}).json()

    body = client.get("/runs").json()

    assert body[0]["run_id"] == created["run_id"]
    assert body[0]["task_name"] == "retry"
    assert body[0]["status"] == "pass"
    assert body[0]["harness_run_id"] == "fake-run"
    assert body[0]["artifacts"]["patch"] == f"/runs/{created['run_id']}/patch"


def test_demo_state_summarizes_created_ids(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.harness_client", FakeHarnessClient(tmp_path / "harness_runs" / "fake-run"))
    task_id = create_task(client)
    created = client.post("/runs", json={"task_id": task_id}, headers={"Idempotency-Key": "state"}).json()

    body = client.get("/demo/state").json()

    assert body["status"] == "ok"
    assert body["tasks"]["count"] == 1
    assert body["tasks"]["ids"] == [task_id]
    assert body["runs"]["count"] == 1
    assert body["runs"]["ids"] == [created["run_id"]]
    assert body["latest_runs"][0]["run_id"] == created["run_id"]
    assert body["latest_runs"][0]["task_id"] == task_id


def test_run_source_returns_isolated_repo_snapshot(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.harness_client", FakeHarnessClient(tmp_path / "harness_runs" / "fake-run"))
    task_id = create_task(client)
    created = client.post("/runs", json={"task_id": task_id}, headers={"Idempotency-Key": "source"}).json()

    body = client.get(f"/runs/{created['run_id']}/source").json()

    assert body["run_id"] == created["run_id"]
    assert body["harness_run_id"] == "fake-run"
    files = {item["path"]: item["content"] for item in body["files"]}
    assert files["app.py"].startswith("def ok")
    assert "assert ok()" in files["test_app.py"]
    assert ".env" not in files
    assert "api_token.txt" not in files
    assert "large.py" not in files


def test_cost_metrics(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.harness_client", FakeHarnessClient(tmp_path / "harness_runs" / "fake-run"))
    task_id = create_task(client)
    client.post("/runs", json={"task_id": task_id}, headers={"Idempotency-Key": "cost"})
    metrics = client.get("/metrics/cost").json()
    assert metrics["total_runs"] == 1
    assert metrics["total_tokens"] == 15
    assert metrics["estimated_cost_usd"] == 0.001


def test_cost_metrics_groups_by_platform_provider_label(client):
    from app.db import get_db
    from app.main import app
    from app.models import Run, Task, Usage

    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        task = Task(name="cost labels", description="", harness_task_path="benchmarks_realistic/retry-429-real/task.json")
        db.add(task)
        db.commit()
        db.refresh(task)
        run54 = Run(task_id=task.id, status="pass", mode="api", model="gpt-5.4", model_provider="newapi-5.4")
        run55 = Run(task_id=task.id, status="pass", mode="api", model="gpt-5.5", model_provider="newapi-5.5")
        db.add_all([run54, run55])
        db.commit()
        db.refresh(run54)
        db.refresh(run55)
        db.add_all(
            [
                Usage(run_id=run54.id, model="gpt-compatible", prompt_tokens=10, completion_tokens=5, total_tokens=15, estimated_cost_usd=0.01),
                Usage(run_id=run55.id, model="gpt-compatible", prompt_tokens=20, completion_tokens=10, total_tokens=30, estimated_cost_usd=0.02),
            ]
        )
        db.commit()
    finally:
        db_gen.close()

    metrics = client.get("/metrics/cost").json()
    by_model = {item["model"]: item for item in metrics["by_model"]}
    assert by_model["newapi-5.4"]["tokens"] == 15
    assert by_model["newapi-5.5"]["tokens"] == 30


def test_cost_metrics_rejects_invalid_date_filter(client):
    res = client.get("/metrics/cost?from=not-a-date")

    assert res.status_code == 400
    assert "ISO-8601" in res.json()["detail"]


def test_evaluation_summary_aggregates_scorecard_usage_and_profiles(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.harness_client", FakeHarnessClient(tmp_path / "harness_runs" / "fake-run"))
    task_id = create_task(client)
    client.post("/runs", json={"task_id": task_id}, headers={"Idempotency-Key": "eval-local"})

    body = client.get("/evaluation/summary").json()

    assert body["summary"]["total"] == 1
    assert body["summary"]["passed"] == 1
    assert body["summary"]["pass_rate"] == 1.0
    assert body["summary"]["avg_score"] == 100
    assert body["summary"]["total_patch_lines"] == 0
    assert body["summary"]["total_changed_files"] == 1
    assert body["summary"]["tests_passed"] == 1
    assert body["summary"]["failure_types"]["None"] == 1
    assert body["summary"]["tokens"] == 15
    assert body["profiles"][0]["profile"] == "scripted baseline"
    assert body["tasks"][0]["report_link"] == f"/runs/{body['tasks'][0]['run_id']}/report"


def test_openai_provider_options_are_persisted_and_passed_to_harness(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.settings.allow_real_llm_calls", True)
    fake = CapturingHarnessClient(tmp_path / "harness_runs" / "fake-run")
    monkeypatch.setattr("app.main.harness_client", fake)
    task_id = create_task(client)

    res = client.post(
        "/runs",
        json={
            "task_id": task_id,
            "mode": "api",
            "model": "gpt-5.5",
            "model_provider": "fighting",
            "base_url": "http://43.106.115.130:8080/v1",
            "wire_api": "responses",
            "reasoning_effort": "high",
            "disable_response_storage": True,
            "allow_llm_calls": True,
            "timeout_seconds": 180,
        },
        headers={"Idempotency-Key": "openai-fighting"},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["model_provider"] == "fighting"
    assert body["wire_api"] == "responses"
    assert body["disable_response_storage"] is True
    assert fake.last_kwargs["base_url"] == "http://43.106.115.130:8080/v1"
    assert fake.last_kwargs["wire_api"] == "responses"
    assert fake.last_kwargs["reasoning_effort"] == "high"
    assert fake.last_kwargs["disable_response_storage"] is True


def test_openai_provider_profile_gets_recommendations(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.settings.allow_real_llm_calls", True)
    monkeypatch.setattr("app.main.harness_client", FakeHarnessClient(tmp_path / "harness_runs" / "fake-run"))
    task_id = create_task(client)
    client.post("/runs", json={"task_id": task_id}, headers={"Idempotency-Key": "eval-baseline"})
    client.post(
        "/runs",
        json={
            "task_id": task_id,
            "mode": "api",
            "model": "gpt-5.5",
            "model_provider": "fighting",
            "base_url": "http://43.106.115.130:8080/v1",
            "wire_api": "responses",
            "reasoning_effort": "high",
            "disable_response_storage": True,
            "allow_llm_calls": True,
        },
        headers={"Idempotency-Key": "eval-openai"},
    )

    body = client.get("/evaluation/summary").json()

    profiles = {item["profile"] for item in body["profiles"]}
    assert "scripted baseline" in profiles
    assert "OpenAI Fighting API" in profiles
    assert {item["category"] for item in body["recommendations"]} == {"stable", "cheap", "fast", "balanced"}
    assert body["retry_comparisons"] == []


def test_newapi_provider_profiles_are_labeled_separately(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.settings.allow_real_llm_calls", True)
    monkeypatch.setattr("app.main.harness_client", FakeHarnessClient(tmp_path / "harness_runs" / "fake-run"))
    task_id = create_task(client)
    client.post(
        "/runs",
        json={
            "task_id": task_id,
            "mode": "api",
            "model": "gpt-5.4",
            "model_provider": "newapi-5.4",
            "base_url": "https://api.example.test/v1",
            "wire_api": "chat_completions",
            "allow_llm_calls": True,
        },
        headers={"Idempotency-Key": "eval-newapi-54"},
    )
    client.post(
        "/runs",
        json={
            "task_id": task_id,
            "mode": "api",
            "model": "gpt-5.5",
            "model_provider": "newapi-5.5",
            "base_url": "https://api.example.test/v1",
            "wire_api": "chat_completions",
            "allow_llm_calls": True,
        },
        headers={"Idempotency-Key": "eval-newapi-55"},
    )

    body = client.get("/evaluation/summary").json()

    profiles = {item["profile"] for item in body["profiles"]}
    assert "NewAPI 5.4" in profiles
    assert "NewAPI 5.5" in profiles
    assert "OpenAI Fighting API" not in profiles


def test_retry_comparison_keeps_provider_paths_separate(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.settings.allow_real_llm_calls", True)
    monkeypatch.setattr("app.main.harness_client", FakeHarnessClient(tmp_path / "harness_runs" / "fake-run"))
    task_id = create_task(client)
    first = client.post(
        "/runs",
        json={"task_id": task_id, "mode": "api", "model": "deepseek-v4-flash", "allow_llm_calls": True},
        headers={"Idempotency-Key": "provider-retry-first"},
    ).json()
    mark_run_status(first["run_id"], "fail")
    client.post(
        "/runs",
        json={
            "task_id": task_id,
            "mode": "api",
            "model": "gpt-5.5",
            "model_provider": "fighting",
            "base_url": "http://43.106.115.130:8080/v1",
            "wire_api": "responses",
            "allow_llm_calls": True,
        },
        headers={"Idempotency-Key": "provider-openai-separate"},
    )
    retried = client.post(f"/runs/{first['run_id']}/retry", json={"allow_llm_calls": True}).json()

    body = client.get("/evaluation/summary").json()

    assert retried["model"] == "deepseek-v4-flash"
    assert len(body["retry_comparisons"]) == 1
    assert body["retry_comparisons"][0]["first_attempt_status"] == "fail"
    assert body["retry_comparisons"][0]["retry_status"] == "pass"


def test_create_custom_task_writes_isolated_harness_task(client, tmp_path):
    res = client.post(
        "/custom-tasks",
        json={
            "name": "custom config merge",
            "goal": "Fix the config merge bug.",
            "source_filename": "config_loader.py",
            "source_code": "def load_config(value):\n    return value\n",
            "test_filename": "test_config_loader.py",
            "test_code": "from config_loader import load_config\n\ndef test_load_config():\n    assert load_config(1) == 1\n",
            "acceptance_command": "python -m pytest -q",
        },
    )

    assert res.status_code == 200
    body = res.json()
    task_path = Path(body["harness_task_path"])
    assert task_path == tmp_path / "harness" / "custom_tasks" / "custom-config-merge" / "task.json"
    assert task_path.exists()
    repo = task_path.parent / "repo"
    assert (repo / "config_loader.py").read_text(encoding="utf-8").startswith("def load_config")
    assert (repo / "test_config_loader.py").read_text(encoding="utf-8").startswith("from config_loader")
    task_spec = json.loads(task_path.read_text(encoding="utf-8"))
    assert task_spec["budget"]["acceptance_timeout_seconds"] == 30
    assert body["task_id"] > 0


def test_create_custom_task_rejects_unsafe_filenames(client):
    res = client.post(
        "/custom-tasks",
        json={
            "name": "escape",
            "goal": "No path escapes.",
            "source_filename": "../app.py",
            "source_code": "print('bad')\n",
            "test_filename": "test_app.py",
            "test_code": "def test_ok():\n    assert True\n",
        },
    )

    assert res.status_code == 400
    assert "filename" in res.json()["detail"]


def test_create_custom_task_rejects_same_source_and_test_filename(client):
    res = client.post(
        "/custom-tasks",
        json={
            "name": "same file",
            "goal": "Do not overwrite source with test code.",
            "source_filename": "app.py",
            "source_code": "def ok():\n    return True\n",
            "test_filename": "app.py",
            "test_code": "def test_ok():\n    assert True\n",
        },
    )

    assert res.status_code == 400
    assert "different" in res.json()["detail"]


def test_create_custom_task_rejects_non_pytest_acceptance_command(client):
    res = client.post(
        "/custom-tasks",
        json={
            "name": "unsafe command",
            "goal": "Do not execute arbitrary acceptance commands.",
            "source_filename": "app.py",
            "source_code": "def ok():\n    return True\n",
            "test_filename": "test_app.py",
            "test_code": "from app import ok\n\ndef test_ok():\n    assert ok()\n",
            "acceptance_command": "python -c \"print('unsafe')\"",
        },
    )

    assert res.status_code == 400
    assert "pytest command" in res.json()["detail"]


def test_create_evaluation_draft_from_pasted_source(client):
    res = client.post(
        "/evaluation-drafts",
        json={
            "source_filename": "config_loader.py",
            "source_code": "def load_config(user_config):\n    config = {}\n    config.update(user_config)\n    return config\n",
            "instruction": "focus on nested headers defaults",
        },
    )

    assert res.status_code == 200
    body = res.json()
    assert body["source_filename"] == "config_loader.py"
    assert body["test_filename"] == "test_config_loader.py"
    assert body["name"]
    assert "focus on nested headers defaults" in body["goal"]
    assert "from config_loader import load_config" in body["test_code"]
    assert body["acceptance_command"] == "python -m pytest -q"
    assert body["difficulty"]["difficulty_level"] in {"easy", "medium", "hard"}
    assert body["difficulty_level"] in {"easy", "medium", "hard"}
    assert body["difficulty_score"] >= 0
    assert body["suggested_strategy"]
    assert body["difficulty_reasons"]
    assert body["analysis_steps"]
    assert body["findings"]


def test_evaluation_draft_marks_worker_retry_code_as_hard(client):
    source = """
import json
import redis
import requests


class RetryWorker:
    def __init__(self, queue, budget):
        self.queue = queue
        self.budget = budget

    async def run(self, item):
        for attempt in range(3):
            try:
                response = requests.post(item["url"], timeout=3)
                if response.status_code == 429:
                    continue
                data = json.loads(response.text)
                if data.get("ok") and self.budget > 0:
                    return data
            except TimeoutError:
                raise
        return None
"""
    res = client.post(
        "/evaluation-drafts",
        json={
            "source_filename": "worker.py",
            "source_code": source,
            "instruction": "judge whether this needs a deeper agent loop",
        },
    )

    assert res.status_code == 200
    body = res.json()
    assert body["difficulty_level"] == "hard"
    assert body["suggested_strategy"]["quality_gate"] == "strict"
    assert any("HTTP" in reason or "worker" in reason for reason in body["difficulty_reasons"])


def test_create_evaluation_builds_multifile_task_and_model_runs(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.settings.auto_start_runs", False)
    payload = {
        "name": "policy evaluation",
        "goal": "Fix policy and audit behavior.",
        "files": [
            {"path": "app/policy.py", "content": "def allowed():\n    return False\n"},
            {"path": "app/audit.py", "content": "def redact(value):\n    return value\n"},
        ],
        "test_files": [
            {"path": "tests/test_policy.py", "content": "from app.policy import allowed\n\ndef test_allowed():\n    assert allowed()\n"},
        ],
        "model_profiles": [
            {"name": "baseline", "mode": "local", "model": "scripted", "allow_llm_calls": False, "timeout_seconds": 90},
            {
                "name": "gpt-5.5-newapi",
                "mode": "api",
                "model": "gpt-5.5",
                "model_provider": "newapi",
                "base_url": "https://api.example.test/v1",
                "wire_api": "chat_completions",
                "allow_llm_calls": False,
                "timeout_seconds": 180,
            },
        ],
        "acceptance_command": "python -m pytest -q",
        "context_summary_files": 16,
    }

    res = client.post("/evaluations", json=payload, headers={"X-User-ID": "alice"})

    assert res.status_code == 200
    body = res.json()
    assert body["evaluation_id"] > 0
    assert body["task"]["name"] == "policy evaluation"
    assert len(body["runs"]) == 2
    assert {run["model"] for run in body["runs"]} == {"scripted", "gpt-5.5"}
    assert all(run["status"] == "pending" for run in body["runs"])
    task_path = Path(body["task"]["harness_task_path"])
    spec = json.loads(task_path.read_text(encoding="utf-8"))
    assert spec["allowlist"] == ["app/policy.py", "app/audit.py"]
    assert spec["acceptance"] == ["python -m pytest -q"]
    assert spec["budget"]["context_summary_files"] == 16
    assert spec["budget"]["llm_timeout_seconds"] == 150
    assert (task_path.parent / "repo" / "app" / "policy.py").exists()
    assert (task_path.parent / "repo" / "tests" / "test_policy.py").exists()


def test_create_evaluation_idempotency_key_prevents_duplicate_runs(client, monkeypatch):
    monkeypatch.setattr("app.main.settings.auto_start_runs", False)
    enqueued: list[int] = []
    monkeypatch.setattr("app.main.run_queue.enqueue", lambda run_id: enqueued.append(run_id))
    payload = {
        "name": "idempotent evaluation",
        "goal": "Avoid duplicate evaluation runs.",
        "files": [{"path": "app.py", "content": "def ok():\n    return True\n"}],
        "test_files": [{"path": "test_app.py", "content": "from app import ok\n\ndef test_ok():\n    assert ok()\n"}],
        "model_profiles": [
            {"name": "baseline", "mode": "local", "model": "scripted", "allow_llm_calls": False},
            {"name": "newapi-5.5", "mode": "api", "model": "gpt-5.5", "allow_llm_calls": False},
        ],
    }
    headers = {"Idempotency-Key": "same-evaluation", "X-User-ID": "alice"}

    first = client.post("/evaluations", json=payload, headers=headers)
    second = client.post("/evaluations", json=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    first_body = first.json()
    second_body = second.json()
    assert second_body["evaluation_id"] == first_body["evaluation_id"]
    assert second_body["task"]["task_id"] == first_body["task"]["task_id"]
    assert [run["run_id"] for run in second_body["runs"]] == [run["run_id"] for run in first_body["runs"]]
    assert enqueued == [run["run_id"] for run in first_body["runs"]]


def test_evaluation_matrix_groups_task_and_model_results(client, monkeypatch):
    monkeypatch.setattr("app.main.settings.auto_start_runs", False)
    payload = {
        "name": "matrix evaluation",
        "goal": "Show task by model result matrix.",
        "files": [{"path": "app.py", "content": "def ok():\n    return True\n"}],
        "test_files": [{"path": "test_app.py", "content": "from app import ok\n\ndef test_ok():\n    assert ok()\n"}],
        "model_profiles": [
            {"name": "baseline", "mode": "local", "model": "scripted", "allow_llm_calls": False},
            {"name": "newapi-5.4", "mode": "api", "model": "gpt-5.4", "model_provider": "newapi-5.4", "allow_llm_calls": False},
        ],
    }

    created = client.post("/evaluations", json=payload).json()
    mark_run_status(created["runs"][0]["run_id"], "pass")
    mark_run_status(created["runs"][1]["run_id"], "fail", failure_type="ProviderTransient", error_message="provider 429")

    matrix = client.get(f"/evaluations/{created['evaluation_id']}/matrix").json()

    assert matrix["evaluation_id"] == created["evaluation_id"]
    assert matrix["name"] == "matrix evaluation"
    assert matrix["task_count"] == 1
    assert matrix["model_count"] == 2
    assert matrix["run_count"] == 2
    assert matrix["passed"] == 1
    assert matrix["failed"] == 1
    assert matrix["status"] == "partial"
    assert matrix["tasks"][0]["task_id"] == created["task"]["task_id"]
    assert {cell["model_provider"] or cell["model"] for cell in matrix["tasks"][0]["models"]} == {"baseline", "newapi-5.4"}
    assert any(cell["failure_type"] == "ProviderTransient" for cell in matrix["tasks"][0]["models"])


def test_evaluation_history_groups_runs_by_task(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.settings.auto_start_runs", False)
    payload = {
        "name": "history evaluation",
        "goal": "Check history grouping.",
        "files": [{"path": "app.py", "content": "def ok():\n    return True\n"}],
        "test_files": [{"path": "test_app.py", "content": "from app import ok\n\ndef test_ok():\n    assert ok()\n"}],
        "model_profiles": [
            {"name": "baseline", "mode": "local", "model": "scripted", "allow_llm_calls": False},
            {"name": "newapi-5.5", "mode": "api", "model": "gpt-5.5", "model_provider": "newapi-5.5", "allow_llm_calls": False},
        ],
    }
    created = client.post("/evaluations", json=payload).json()

    history = client.get("/evaluations/history").json()

    assert history[0]["evaluation_id"] == created["evaluation_id"]
    assert history[0]["task_id"] == created["task"]["task_id"]
    assert history[0]["name"] == "history evaluation"
    assert history[0]["run_count"] == 2
    assert history[0]["model_count"] == 2
    assert history[0]["status"] == "running"
    assert history[0]["latest_run_id"] in {run["run_id"] for run in created["runs"]}
    assert {run["model"] for run in history[0]["runs"]} == {"scripted", "gpt-5.5"}


def test_evaluation_history_includes_failure_feedback(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.settings.auto_start_runs", False)
    payload = {
        "name": "history failure feedback",
        "goal": "Show users why an evaluation failed.",
        "files": [{"path": "app.py", "content": "def ok():\n    return True\n"}],
        "test_files": [{"path": "test_app.py", "content": "from app import ok\n\ndef test_ok():\n    assert ok()\n"}],
        "model_profiles": [
            {"name": "newapi-5.5", "mode": "api", "model": "gpt-5.5", "model_provider": "newapi-5.5", "allow_llm_calls": False},
        ],
    }
    created = client.post("/evaluations", json=payload).json()
    run_id = created["runs"][0]["run_id"]
    from app.db import get_db
    from app.main import app
    from app.models import Run

    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        run = db.get(Run, run_id)
        assert run is not None
        run.status = "fail"
        run.failure_type = "ProviderTransient"
        run.error_message = "provider returned 429 Too Many Requests"
        db.commit()
    finally:
        db_gen.close()

    history = client.get("/evaluations/history").json()

    assert history[0]["latest_failure_type"] == "ProviderTransient"
    assert history[0]["latest_error_message"] == "provider returned 429 Too Many Requests"
    assert history[0]["failure_types"] == {"ProviderTransient": 1}
    assert history[0]["runs"][0]["failure_type"] == "ProviderTransient"
    assert history[0]["runs"][0]["error_message"] == "provider returned 429 Too Many Requests"


def test_get_agent_run_artifact_exposes_strategy(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.harness_client", FakeHarnessClient(tmp_path / "harness_runs" / "fake-run"))
    task_id = create_task(client)
    created = client.post(
        "/runs",
        json={"task_id": task_id, "mode": "local", "model": "scripted", "allow_llm_calls": False},
        headers={"Idempotency-Key": "agent-run-artifact"},
    ).json()

    artifact = client.get(f"/runs/{created['run_id']}/agent-run").json()

    assert artifact["strategy"]["tier"] == "simple"
    assert artifact["strategy"]["max_steps"] == 4
    assert artifact["steps"] == []


def test_delete_evaluation_removes_completed_task_runs_and_usage(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.harness_client", FakeHarnessClient(tmp_path / "harness_runs" / "fake-run"))
    payload = {
        "name": "delete me",
        "goal": "Delete completed evaluation.",
        "files": [{"path": "app.py", "content": "def ok():\n    return True\n"}],
        "test_files": [{"path": "test_app.py", "content": "from app import ok\n\ndef test_ok():\n    assert ok()\n"}],
        "model_profiles": [{"name": "baseline", "mode": "local", "model": "scripted"}],
    }
    created = client.post("/evaluations", json=payload).json()
    task_id = created["task"]["task_id"]
    run_id = created["runs"][0]["run_id"]

    deleted = client.delete(f"/evaluations/{task_id}").json()

    assert deleted["status"] == "deleted"
    assert deleted["deleted_runs"] == 1
    assert client.get(f"/runs/{run_id}").status_code == 404
    assert all(item["task_id"] != task_id for item in client.get("/evaluations/history").json())


def test_delete_evaluation_rejects_running_task(client, monkeypatch):
    monkeypatch.setattr("app.main.settings.auto_start_runs", False)
    payload = {
        "name": "do not delete running",
        "goal": "Pending runs should be cancelled first.",
        "files": [{"path": "app.py", "content": "def ok():\n    return True\n"}],
        "test_files": [{"path": "test_app.py", "content": "from app import ok\n\ndef test_ok():\n    assert ok()\n"}],
        "model_profiles": [{"name": "baseline", "mode": "local", "model": "scripted"}],
    }
    created = client.post("/evaluations", json=payload).json()

    res = client.delete(f"/evaluations/{created['task']['task_id']}")

    assert res.status_code == 400
    assert "pending or running" in res.json()["detail"]


def test_workspace_headers_isolate_runs_and_artifacts(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.harness_client", FakeHarnessClient(tmp_path / "harness_runs" / "fake-run"))
    headers_a = {"X-Tenant-ID": "team-a", "X-Workspace-ID": "alpha", "Idempotency-Key": "workspace-a"}
    headers_b = {"X-Tenant-ID": "team-a", "X-Workspace-ID": "beta"}
    task = client.post(
        "/tasks",
        json={"name": "isolated", "harness_task_path": "task.json"},
        headers={"X-Tenant-ID": "team-a", "X-Workspace-ID": "alpha"},
    ).json()

    created = client.post("/runs", json={"task_id": task["task_id"]}, headers=headers_a).json()

    assert created["workspace_id"] == task["workspace_id"]
    assert client.get("/runs", headers=headers_a).json()[0]["run_id"] == created["run_id"]
    assert client.get("/runs", headers=headers_b).json() == []
    assert client.get(f"/runs/{created['run_id']}", headers=headers_b).status_code == 404
    assert client.get(f"/runs/{created['run_id']}/patch", headers=headers_b).status_code == 404
    summary_b = client.get("/evaluation/summary", headers=headers_b).json()
    assert summary_b["summary"]["total"] == 0


def test_workspace_headers_prevent_running_task_from_other_workspace(client, monkeypatch):
    monkeypatch.setattr("app.main._schedule_run", lambda background_tasks, run_id: None)
    task = client.post(
        "/tasks",
        json={"name": "alpha task", "harness_task_path": "task.json"},
        headers={"X-Tenant-ID": "team-a", "X-Workspace-ID": "alpha"},
    ).json()

    res = client.post(
        "/runs",
        json={"task_id": task["task_id"]},
        headers={"X-Tenant-ID": "team-a", "X-Workspace-ID": "beta", "Idempotency-Key": "wrong-workspace"},
    )

    assert res.status_code == 404
    assert res.json()["detail"] == "task not found"


def test_idempotency_keys_are_scoped_by_workspace(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.harness_client", FakeHarnessClient(tmp_path / "harness_runs" / "fake-run"))
    task_a = client.post(
        "/tasks",
        json={"name": "alpha task", "harness_task_path": "task.json"},
        headers={"X-Tenant-ID": "team-a", "X-Workspace-ID": "alpha"},
    ).json()
    task_b = client.post(
        "/tasks",
        json={"name": "beta task", "harness_task_path": "task.json"},
        headers={"X-Tenant-ID": "team-a", "X-Workspace-ID": "beta"},
    ).json()
    headers_a = {"X-Tenant-ID": "team-a", "X-Workspace-ID": "alpha", "X-User-ID": "same-user", "Idempotency-Key": "same-key"}
    headers_b = {"X-Tenant-ID": "team-a", "X-Workspace-ID": "beta", "X-User-ID": "same-user", "Idempotency-Key": "same-key"}

    run_a = client.post("/runs", json={"task_id": task_a["task_id"]}, headers=headers_a).json()
    run_b = client.post("/runs", json={"task_id": task_b["task_id"]}, headers=headers_b).json()
    run_a_again = client.post("/runs", json={"task_id": task_a["task_id"]}, headers=headers_a).json()

    assert run_a["run_id"] != run_b["run_id"]
    assert run_a_again["run_id"] == run_a["run_id"]


def test_workspace_headers_prevent_retry_cancel_and_failure_context_access(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.harness_client", FakeHarnessClient(tmp_path / "harness_runs" / "fake-run"))
    headers_a = {"X-Tenant-ID": "team-a", "X-Workspace-ID": "alpha", "Idempotency-Key": "alpha-run"}
    headers_b = {"X-Tenant-ID": "team-a", "X-Workspace-ID": "beta"}
    task = client.post(
        "/tasks",
        json={"name": "alpha task", "harness_task_path": "task.json"},
        headers={"X-Tenant-ID": "team-a", "X-Workspace-ID": "alpha"},
    ).json()
    created = client.post("/runs", json={"task_id": task["task_id"]}, headers=headers_a).json()
    mark_run_status(created["run_id"], "fail")

    retry = client.post(f"/runs/{created['run_id']}/retry", json={}, headers=headers_b)
    cancel = client.post(f"/runs/{created['run_id']}/cancel", headers=headers_b)
    context = client.get(f"/runs/{created['run_id']}/failure-context", headers=headers_b)

    assert retry.status_code == 404
    assert cancel.status_code == 404
    assert context.status_code == 404


def test_evaluation_creation_uses_workspace_header(client, monkeypatch):
    monkeypatch.setattr("app.main.settings.auto_start_runs", False)
    res = client.post(
        "/evaluations",
        json={
            "name": "workspace evaluation",
            "goal": "Fix workspace task.",
            "files": [{"path": "app.py", "content": "def ok():\n    return False\n"}],
            "test_files": [{"path": "test_app.py", "content": "from app import ok\n\ndef test_ok():\n    assert ok()\n"}],
            "model_profiles": [{"name": "baseline", "mode": "local", "model": "scripted"}],
        },
        headers={"X-Tenant-ID": "team-b", "X-Workspace-ID": "experiments"},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["task"]["workspace_id"] is not None
    assert body["runs"][0]["workspace_id"] == body["task"]["workspace_id"]


def test_create_evaluation_rejects_duplicate_paths(client):
    res = client.post(
        "/evaluations",
        json={
            "name": "duplicate files",
            "goal": "Reject duplicate paths.",
            "files": [{"path": "app.py", "content": "x = 1\n"}],
            "test_files": [{"path": "app.py", "content": "def test_x():\n    assert True\n"}],
            "model_profiles": [{"name": "baseline", "mode": "local", "model": "scripted"}],
        },
    )

    assert res.status_code == 400
    assert "duplicate" in res.json()["detail"]


def test_create_evaluation_rejects_path_traversal(client):
    res = client.post(
        "/evaluations",
        json={
            "name": "escape",
            "goal": "No escapes.",
            "files": [{"path": "../app.py", "content": "x = 1\n"}],
            "test_files": [{"path": "test_app.py", "content": "def test_x():\n    assert True\n"}],
            "model_profiles": [{"name": "baseline", "mode": "local", "model": "scripted"}],
        },
    )

    assert res.status_code == 400
    assert "path" in res.json()["detail"]


def test_create_payload_rejects_unknown_fields(client):
    res = client.post("/tasks", json={"name": "retry", "harness_task_path": "task.json", "unexpected": True})

    assert res.status_code == 422


def test_api_run_requires_server_side_real_call_switch(client):
    task_id = create_task(client)
    res = client.post(
        "/runs",
        json={"task_id": task_id, "mode": "api", "model": "deepseek-v4-flash", "allow_llm_calls": True},
    )
    assert res.status_code == 400
    assert "disabled" in res.json()["detail"]


def test_retry_api_run_stops_when_real_call_budget_is_spent(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.settings.allow_real_llm_calls", True)
    monkeypatch.setattr("app.main.settings.real_api_budget_limit_cny", 0.1)
    monkeypatch.setattr("app.main.settings.usd_to_cny_rate", 100.0)
    monkeypatch.setattr("app.main.harness_client", FakeHarnessClient(tmp_path / "harness_runs" / "fake-run"))
    task_id = create_task(client)
    first = client.post(
        "/runs",
        json={"task_id": task_id, "mode": "api", "model": "deepseek-v4-flash", "allow_llm_calls": True},
        headers={"Idempotency-Key": "api-budget"},
    ).json()
    mark_run_status(first["run_id"], "fail")

    res = client.post(f"/runs/{first['run_id']}/retry", json={"allow_llm_calls": True})

    assert res.status_code == 400
    assert "0.1 CNY" in res.json()["detail"]


def test_retry_run_rejects_successful_source_run(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.settings.allow_real_llm_calls", True)
    monkeypatch.setattr("app.main.settings.real_api_budget_limit_cny", 1.0)
    monkeypatch.setattr("app.main.settings.usd_to_cny_rate", 7.25)
    fake = FakeHarnessClient(tmp_path / "harness_runs" / "fake-run")
    monkeypatch.setattr("app.main.harness_client", fake)
    task_id = create_task(client)
    first = client.post(
        "/runs",
        json={"task_id": task_id, "mode": "api", "model": "deepseek-v4-flash", "allow_llm_calls": True},
        headers={"Idempotency-Key": "api-retry-ok"},
    ).json()

    res = client.post(f"/runs/{first['run_id']}/retry", json={"allow_llm_calls": True})

    assert res.status_code == 400
    assert "failed" in res.json()["detail"]


def test_retry_api_run_allowed_below_real_call_budget_for_failed_source(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.settings.allow_real_llm_calls", True)
    monkeypatch.setattr("app.main.settings.real_api_budget_limit_cny", 1.0)
    monkeypatch.setattr("app.main.settings.usd_to_cny_rate", 7.25)
    fake = FakeHarnessClient(tmp_path / "harness_runs" / "fake-run")
    monkeypatch.setattr("app.main.harness_client", fake)
    task_id = create_task(client)
    first = client.post(
        "/runs",
        json={"task_id": task_id, "mode": "api", "model": "deepseek-v4-flash", "allow_llm_calls": True},
        headers={"Idempotency-Key": "api-retry-failed-ok"},
    ).json()
    mark_run_status(first["run_id"], "fail")

    res = client.post(f"/runs/{first['run_id']}/retry", json={"allow_llm_calls": True})

    assert res.status_code == 200
    retried = res.json()
    assert retried["run_id"] != first["run_id"]
    assert client.get(f"/runs/{retried['run_id']}").json()["status"] == "pass"


def test_failure_context_endpoint_summarizes_failed_run_artifacts(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.harness_client", FakeHarnessClient(tmp_path / "harness_runs" / "fake-run"))
    task_id = create_task(client)
    first = client.post("/runs", json={"task_id": task_id}, headers={"Idempotency-Key": "failure-context"}).json()
    mark_run_status(first["run_id"], "fail")

    body = client.get(f"/runs/{first['run_id']}/failure-context").json()

    assert body["source_run_id"] == first["run_id"]
    assert body["status"] == "fail"
    assert body["task"]["name"] == "retry"
    assert body["artifacts"]["scorecard"]["status"] == "pass"
    assert "diff --git" in body["artifacts"]["patch_excerpt"]
    assert "usage" in body["artifacts"]["trace_excerpt"]
    assert body["retry_guidance"]["mode"] == "human_confirmed_retry"


def test_completed_run_records_evaluation_memory(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.harness_client", FakeHarnessClient(tmp_path / "harness_runs" / "fake-run"))
    task_id = create_task(client)

    created = client.post("/runs", json={"task_id": task_id}, headers={"Idempotency-Key": "memory-record"}).json()

    body = client.get("/memory/evaluation").json()
    assert body["count"] == 1
    record = body["items"][0]
    assert record["run_id"] == created["run_id"]
    assert record["task_name"] == "retry"
    assert record["status"] == "pass"
    assert "diff --git" in record["patch_summary"]


def test_evaluation_memory_summary_counts_runs_and_retry_success(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.harness_client", OneFailureHarnessClient(tmp_path / "harness_runs" / "fake-run"))
    task_id = create_task(client)
    passed = client.post("/runs", json={"task_id": task_id}, headers={"Idempotency-Key": "memory-summary-pass"}).json()
    failed = client.post("/runs", json={"task_id": task_id}, headers={"Idempotency-Key": "memory-summary-fail"}).json()
    retried = client.post(f"/runs/{failed['run_id']}/retry", json={"use_failure_context": True}).json()

    body = client.get("/memory/evaluation/summary").json()

    assert body["total_records"] == 3
    assert body["passed_records"] == 2
    assert body["failed_records"] == 1
    assert body["retry_records"] == 1
    assert body["retry_successes"] == 1
    assert body["fail_to_pass_rate"] == 1.0
    assert body["failure_types"]["TestFailed"] == 1
    assert body["top_tasks"][0]["task_name"] == "retry"
    assert body["top_tasks"][0]["last_run_id"] == retried["run_id"]
    assert body["recent_items"][0]["run_id"] == retried["run_id"]
    assert passed["run_id"] != retried["run_id"]


def test_failure_context_includes_similar_evaluation_memory_hints(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.harness_client", FakeHarnessClient(tmp_path / "harness_runs" / "fake-run"))
    task_id = create_task(client)
    passed = client.post("/runs", json={"task_id": task_id}, headers={"Idempotency-Key": "memory-hint-pass"}).json()
    failed = client.post("/runs", json={"task_id": task_id}, headers={"Idempotency-Key": "memory-hint-fail"}).json()
    mark_run_status(failed["run_id"], "fail")

    body = client.get(f"/runs/{failed['run_id']}/failure-context").json()

    assert body["memory_hints"]
    assert body["memory_hints"][0]["run_id"] == passed["run_id"]
    assert body["memory_hints"][0]["score"] > 0


def test_evaluation_memory_is_scoped_by_workspace(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.harness_client", FakeHarnessClient(tmp_path / "harness_runs" / "fake-run"))
    task_a = client.post(
        "/tasks",
        json={"name": "alpha memory", "harness_task_path": "task.json"},
        headers={"X-Tenant-ID": "team-a", "X-Workspace-ID": "alpha"},
    ).json()
    task_b = client.post(
        "/tasks",
        json={"name": "beta memory", "harness_task_path": "task.json"},
        headers={"X-Tenant-ID": "team-a", "X-Workspace-ID": "beta"},
    ).json()
    headers_a = {"X-Tenant-ID": "team-a", "X-Workspace-ID": "alpha", "Idempotency-Key": "alpha-memory"}
    headers_b = {"X-Tenant-ID": "team-a", "X-Workspace-ID": "beta", "Idempotency-Key": "beta-memory"}

    run_a = client.post("/runs", json={"task_id": task_a["task_id"]}, headers=headers_a).json()
    run_b = client.post("/runs", json={"task_id": task_b["task_id"]}, headers=headers_b).json()

    memory_a = client.get("/memory/evaluation", headers=headers_a).json()
    memory_b = client.get("/memory/evaluation", headers=headers_b).json()
    summary_a = client.get("/memory/evaluation/summary", headers=headers_a).json()
    summary_b = client.get("/memory/evaluation/summary", headers=headers_b).json()

    assert [item["run_id"] for item in memory_a["items"]] == [run_a["run_id"]]
    assert [item["run_id"] for item in memory_b["items"]] == [run_b["run_id"]]
    assert summary_a["top_tasks"][0]["task_name"] == "alpha memory"
    assert summary_b["top_tasks"][0]["task_name"] == "beta memory"


def test_retry_with_failure_context_passes_context_path_to_harness(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.settings.allow_real_llm_calls", True)
    monkeypatch.setattr("app.main.settings.real_api_budget_limit_cny", 1.0)
    monkeypatch.setattr("app.main.settings.usd_to_cny_rate", 7.25)
    fake = CapturingHarnessClient(tmp_path / "harness_runs" / "fake-run")
    monkeypatch.setattr("app.main.harness_client", fake)
    task_id = create_task(client)
    first = client.post(
        "/runs",
        json={"task_id": task_id, "mode": "api", "model": "deepseek-v4-flash", "allow_llm_calls": True},
        headers={"Idempotency-Key": "api-retry-context"},
    ).json()
    mark_run_status(first["run_id"], "fail")

    res = client.post(
        f"/runs/{first['run_id']}/retry",
        json={"allow_llm_calls": True, "use_failure_context": True, "timeout_seconds": 180},
    )

    assert res.status_code == 200
    context_path = Path(fake.last_kwargs["failure_context_path"])
    assert context_path.exists()
    context = json.loads(context_path.read_text(encoding="utf-8"))
    assert context["source_run_id"] == first["run_id"]
    assert context["retry_guidance"]["mode"] == "human_confirmed_retry"
    assert res.json()["source_run_id"] == first["run_id"]
    assert res.json()["failure_context_path"] == str(context_path)


def test_cancel_pending_run(client, monkeypatch):
    task_id = create_task(client)
    monkeypatch.setattr("app.main._schedule_run", lambda background_tasks, run_id: None)
    created = client.post("/runs", json={"task_id": task_id}, headers={"Idempotency-Key": "cancel"}).json()

    res = client.post(f"/runs/{created['run_id']}/cancel")

    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"


def test_post_run_can_leave_work_for_external_worker(client, monkeypatch):
    task_id = create_task(client)
    called = {"value": False}
    monkeypatch.setattr("app.main._schedule_run", lambda background_tasks, run_id: called.update(value=True))
    monkeypatch.setattr("app.main.settings.auto_start_runs", False)

    res = client.post("/runs", json={"task_id": task_id}, headers={"Idempotency-Key": "external-worker"})

    assert res.status_code == 200
    assert res.json()["status"] == "pending"
    assert called["value"] is False


def test_auto_start_runs_false_enqueues_run_for_worker(client, monkeypatch):
    task_id = create_task(client)
    enqueued: list[int] = []
    monkeypatch.setattr("app.main.settings.auto_start_runs", False)
    monkeypatch.setattr("app.main.run_queue.enqueue", lambda run_id: enqueued.append(run_id))

    res = client.post("/runs", json={"task_id": task_id}, headers={"Idempotency-Key": "queue-worker"})

    assert res.status_code == 200
    assert enqueued == [res.json()["run_id"]]


def test_auto_start_runs_false_enqueues_evaluation_runs(client, monkeypatch):
    monkeypatch.setattr("app.main.settings.auto_start_runs", False)
    enqueued: list[int] = []
    monkeypatch.setattr("app.main.run_queue.enqueue", lambda run_id: enqueued.append(run_id))
    payload = {
        "name": "queued evaluation",
        "goal": "Compare models on a user-submitted task.",
        "files": [{"path": "app.py", "content": "def ok():\n    return False\n"}],
        "test_files": [{"path": "test_app.py", "content": "from app import ok\n\ndef test_ok():\n    assert ok()\n"}],
        "model_profiles": [
            {"name": "baseline", "mode": "local", "model": "scripted"},
            {"name": "gpt-5.5", "mode": "api", "model": "gpt-5.5", "allow_llm_calls": False},
        ],
    }

    res = client.post("/evaluations", json=payload)

    assert res.status_code == 200
    run_ids = [item["run_id"] for item in res.json()["runs"]]
    assert enqueued == run_ids
