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


def create_task(client):
    res = client.post("/tasks", json={"name": "retry", "harness_task_path": "task.json"})
    assert res.status_code == 200
    return res.json()["task_id"]


def mark_run_status(run_id: int, status: str) -> None:
    from app.db import get_db
    from app.main import app
    from app.models import Run

    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        run = db.get(Run, run_id)
        assert run is not None
        run.status = status
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
