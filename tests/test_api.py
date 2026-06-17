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


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


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


def test_cost_metrics(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.harness_client", FakeHarnessClient(tmp_path / "harness_runs" / "fake-run"))
    task_id = create_task(client)
    client.post("/runs", json={"task_id": task_id}, headers={"Idempotency-Key": "cost"})
    metrics = client.get("/metrics/cost").json()
    assert metrics["total_runs"] == 1
    assert metrics["total_tokens"] == 15
    assert metrics["estimated_cost_usd"] == 0.001


def test_api_run_requires_server_side_real_call_switch(client):
    task_id = create_task(client)
    res = client.post(
        "/runs",
        json={"task_id": task_id, "mode": "api", "model": "deepseek-v4-flash", "allow_llm_calls": True},
    )
    assert res.status_code == 400
    assert "disabled" in res.json()["detail"]


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
