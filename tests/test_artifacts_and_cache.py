from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from app.artifacts import UnsafeArtifactPath, parse_usage_from_artifacts, resolve_artifact
from app.cache import MemoryCache, RedisCache, build_cache
from app.harness_client import HarnessClient


def test_parse_usage_from_trace(tmp_path: Path):
    (tmp_path / "trace.jsonl").write_text(
        json.dumps({"observation": {"usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5, "estimated_cost_usd": 0.0001}}}) + "\n",
        encoding="utf-8",
    )
    usage = parse_usage_from_artifacts(tmp_path, "deepseek-v4-flash")
    assert usage["total_tokens"] == 5
    assert usage["estimated_cost_usd"] == 0.0001


def test_artifact_path_cannot_escape_root(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "scorecard.json").write_text("{}", encoding="utf-8")
    with pytest.raises(UnsafeArtifactPath):
        resolve_artifact(root, outside, "scorecard.json")


def test_cache_ttl_jitter_and_negative_cache():
    cache = MemoryCache(default_ttl=10, negative_ttl=2, jitter=5)
    values = {cache.ttl_with_jitter(10) for _ in range(30)}
    assert min(values) >= 10
    assert max(values) <= 15
    assert len(values) > 1
    cache.set("missing", "__missing__", negative=True)
    assert cache.get("missing") == "__missing__"


def test_harness_client_passes_timeout_and_allow_flag(tmp_path: Path):
    captured = {}

    def fake_run(args, cwd, env, text, capture_output, timeout, check):
        captured["args"] = args
        captured["timeout"] = timeout
        run_dir = tmp_path / "runs" / "run-1"
        run_dir.mkdir(parents=True)
        (run_dir / "gate.json").write_text('{"status":"pass"}', encoding="utf-8")
        (run_dir / "scorecard.json").write_text('{"status":"pass"}', encoding="utf-8")
        (run_dir / "trace.jsonl").write_text("", encoding="utf-8")

        class Completed:
            returncode = 0
            stdout = f"run_id=run-1\nstatus=pass\nartifacts={run_dir}\n"
            stderr = ""

        return Completed()

    client = HarnessClient(tmp_path, "python", command_runner=fake_run)
    result = client.run_task("task.json", "api", "deepseek-v4-flash", str(tmp_path / "runs"), True, timeout_seconds=30)

    assert "--allow-llm-calls" in captured["args"]
    assert captured["timeout"] == 30
    assert result.status == "pass"


def test_harness_client_passes_openai_compatible_provider_options(tmp_path: Path):
    captured = {}

    def fake_run(args, cwd, env, text, capture_output, timeout, check):
        captured["args"] = args
        run_dir = tmp_path / "runs" / "run-1"
        run_dir.mkdir(parents=True)
        (run_dir / "gate.json").write_text('{"status":"pass"}', encoding="utf-8")
        (run_dir / "scorecard.json").write_text('{"status":"pass"}', encoding="utf-8")
        (run_dir / "trace.jsonl").write_text("", encoding="utf-8")

        class Completed:
            returncode = 0
            stdout = f"run_id=run-1\nstatus=pass\nartifacts={run_dir}\n"
            stderr = ""

        return Completed()

    client = HarnessClient(tmp_path, "python", command_runner=fake_run)
    client.run_task(
        "task.json",
        "api",
        "gpt-5.5",
        str(tmp_path / "runs"),
        True,
        base_url="http://43.106.115.130:8080/v1",
        wire_api="responses",
        reasoning_effort="high",
        disable_response_storage=True,
    )

    assert "--base-url" in captured["args"]
    assert "http://43.106.115.130:8080/v1" in captured["args"]
    assert captured["args"][captured["args"].index("--wire-api") + 1] == "responses"
    assert captured["args"][captured["args"].index("--reasoning-effort") + 1] == "high"
    assert "--disable-response-storage" in captured["args"]


def test_harness_client_resolves_run_dir_from_run_id_when_artifacts_missing(tmp_path: Path):
    def fake_run(args, cwd, env, text, capture_output, timeout, check):
        run_dir = tmp_path / "runs" / "run-1"
        run_dir.mkdir(parents=True)
        (run_dir / "gate.json").write_text('{"status":"pass"}', encoding="utf-8")
        (run_dir / "scorecard.json").write_text('{"status":"pass"}', encoding="utf-8")
        (run_dir / "trace.jsonl").write_text("", encoding="utf-8")

        class Completed:
            returncode = 0
            stdout = "run_id=run-1\nstatus=pass\n"
            stderr = ""

        return Completed()

    client = HarnessClient(tmp_path, "python", command_runner=fake_run)
    result = client.run_task("task.json", "local", "scripted", str(tmp_path / "runs"), False)

    assert result.harness_run_id == "run-1"
    assert result.artifacts_dir == (tmp_path / "runs" / "run-1").resolve()


def test_harness_client_rejects_stdout_without_run_identity(tmp_path: Path):
    def fake_run(args, cwd, env, text, capture_output, timeout, check):
        class Completed:
            returncode = 0
            stdout = "status=pass\n"
            stderr = ""

        return Completed()

    client = HarnessClient(tmp_path, "python", command_runner=fake_run)

    with pytest.raises(RuntimeError, match="artifacts or run_id"):
        client.run_task("task.json", "local", "scripted", str(tmp_path / "runs"), False)


def test_harness_client_rejects_artifacts_outside_runs_root(tmp_path: Path):
    outside = tmp_path / "outside-run"
    outside.mkdir()

    def fake_run(args, cwd, env, text, capture_output, timeout, check):
        class Completed:
            returncode = 0
            stdout = f"run_id=run-1\nstatus=pass\nartifacts={outside}\n"
            stderr = ""

        return Completed()

    client = HarnessClient(tmp_path, "python", command_runner=fake_run)

    with pytest.raises(RuntimeError, match="escaped runs root"):
        client.run_task("task.json", "local", "scripted", str(tmp_path / "runs"), False)


def test_harness_client_loads_harness_root_env_for_subprocess(tmp_path: Path):
    captured = {}
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=local-test-key\nOPENAGENT_BASE_URL=https://example.test\n", encoding="utf-8")

    def fake_run(args, cwd, env, text, capture_output, timeout, check):
        captured["env"] = env
        run_dir = tmp_path / "runs" / "run-1"
        run_dir.mkdir(parents=True)
        (run_dir / "gate.json").write_text('{"status":"pass"}', encoding="utf-8")
        (run_dir / "scorecard.json").write_text('{"status":"pass"}', encoding="utf-8")
        (run_dir / "trace.jsonl").write_text("", encoding="utf-8")

        class Completed:
            returncode = 0
            stdout = f"run_id=run-1\nstatus=pass\nartifacts={run_dir}\n"
            stderr = ""

        return Completed()

    client = HarnessClient(tmp_path, "python", command_runner=fake_run)
    client.run_task("task.json", "api", "deepseek-v4-flash", str(tmp_path / "runs"), True)

    assert captured["env"]["DEEPSEEK_API_KEY"] == "local-test-key"
    assert captured["env"]["OPENAGENT_BASE_URL"] == "https://example.test"


def test_harness_client_maps_newapi_profile_to_dedicated_key(tmp_path: Path):
    captured = {}
    (tmp_path / ".env").write_text(
        "NEWAPI_5_4_API_KEY=four-key\nNEWAPI_5_5_API_KEY=five-key\nNEWAPI_BASE_URL=https://api.example.test/v1\n",
        encoding="utf-8",
    )

    def fake_run(args, cwd, env, text, capture_output, timeout, check):
        captured["env"] = env
        run_dir = tmp_path / "runs" / "run-1"
        run_dir.mkdir(parents=True)
        (run_dir / "gate.json").write_text('{"status":"pass"}', encoding="utf-8")
        (run_dir / "scorecard.json").write_text('{"status":"pass"}', encoding="utf-8")
        (run_dir / "trace.jsonl").write_text("", encoding="utf-8")

        class Completed:
            returncode = 0
            stdout = f"run_id=run-1\nstatus=pass\nartifacts={run_dir}\n"
            stderr = ""

        return Completed()

    client = HarnessClient(tmp_path, "python", command_runner=fake_run)
    client.run_task(
        "task.json",
        "api",
        "gpt-5.5",
        str(tmp_path / "runs"),
        True,
        model_provider="newapi-5.5",
        base_url="https://api.example.test/v1",
        wire_api="chat_completions",
    )

    assert captured["env"]["OPENAGENT_API_KEY"] == "five-key"
    assert captured["env"]["OPENAI_API_KEY"] == "five-key"
    assert captured["env"]["OPENAGENT_BASE_URL"] == "https://api.example.test/v1"
    assert captured["env"]["OPENAGENT_WIRE_API"] == "chat_completions"


def test_harness_client_returns_failure_message_from_api_artifacts(tmp_path: Path):
    def fake_run(args, cwd, env, text, capture_output, timeout, check):
        run_dir = tmp_path / "runs" / "run-429"
        run_dir.mkdir(parents=True)
        (run_dir / "gate.json").write_text('{"status":"fail", "failure_type":"ProviderTransient"}', encoding="utf-8")
        (run_dir / "scorecard.json").write_text('{"status":"fail", "failure_type":"ProviderTransient"}', encoding="utf-8")
        (run_dir / "trace.jsonl").write_text("", encoding="utf-8")
        (run_dir / "api_agent_run.json").write_text(
            json.dumps({"summary": "exceeded retry limit, last status: 429 Too Many Requests"}),
            encoding="utf-8",
        )

        class Completed:
            returncode = 0
            stdout = f"run_id=run-429\nstatus=fail\nartifacts={run_dir}\n"
            stderr = ""

        return Completed()

    client = HarnessClient(tmp_path, "python", command_runner=fake_run)
    result = client.run_task("task.json", "api", "gpt-5.5", str(tmp_path / "runs"), True)

    assert result.failure_type == "ProviderTransient"
    assert result.error_message == "exceeded retry limit, last status: 429 Too Many Requests"


def test_harness_client_docker_executor_rewrites_task_paths_and_maps_artifacts(tmp_path: Path):
    harness_root = tmp_path / "harness"
    task_root = harness_root / "custom_tasks" / "policy"
    repo = task_root / "repo"
    repo.mkdir(parents=True)
    task_path = task_root / "task.json"
    task_path.write_text(
        json.dumps(
            {
                "id": "policy",
                "repo": str(repo),
                "goal": "Fix policy.",
                "allowlist": ["app.py"],
                "acceptance": ["python -m pytest -q"],
            }
        ),
        encoding="utf-8",
    )
    captured = {}

    def fake_run(args, cwd, env, text, capture_output, timeout, check):
        captured["args"] = args
        spec_arg = args[max(i for i, value in enumerate(args) if value == "run") + 1]
        assert spec_arg == "/runs/.docker_specs/run-42.json"
        generated_spec = json.loads((tmp_path / "runs" / ".docker_specs" / "run-42.json").read_text(encoding="utf-8"))
        assert generated_spec["repo"] == "/harness/custom_tasks/policy/repo"
        run_dir = tmp_path / "runs" / "run-1"
        run_dir.mkdir(parents=True)
        (run_dir / "gate.json").write_text('{"status":"pass"}', encoding="utf-8")
        (run_dir / "scorecard.json").write_text('{"status":"pass"}', encoding="utf-8")
        (run_dir / "trace.jsonl").write_text("", encoding="utf-8")

        class Completed:
            returncode = 0
            stdout = "run_id=run-1\nstatus=pass\nartifacts=/runs/run-1\n"
            stderr = ""

        return Completed()

    client = HarnessClient(
        harness_root,
        "python",
        executor="docker",
        docker_image="openagent-harness:test",
        command_runner=fake_run,
    )
    result = client.run_task(str(task_path), "local", "scripted", str(tmp_path / "runs"), False, run_id=42)

    assert captured["args"][:3] == ["docker", "run", "--rm"]
    assert "openagent-harness:test" in captured["args"]
    assert f"{harness_root.resolve()}:/harness:ro" in captured["args"]
    assert f"{(tmp_path / 'runs').resolve()}:/runs" in captured["args"]
    assert result.artifacts_dir == (tmp_path / "runs" / "run-1").resolve()


def test_harness_client_docker_executor_rewrites_failure_context_path(tmp_path: Path):
    harness_root = tmp_path / "harness"
    task_root = harness_root / "custom_tasks" / "retry"
    repo = task_root / "repo"
    repo.mkdir(parents=True)
    task_path = task_root / "task.json"
    task_path.write_text(
        json.dumps({"id": "retry", "repo": str(repo), "goal": "Retry.", "allowlist": ["app.py"], "acceptance": ["pytest -q"]}),
        encoding="utf-8",
    )
    failure_context = tmp_path / "runs" / "previous" / "failure_context.json"
    failure_context.parent.mkdir(parents=True)
    failure_context.write_text("{}", encoding="utf-8")
    captured = {}

    def fake_run(args, cwd, env, text, capture_output, timeout, check):
        captured["args"] = args
        run_dir = tmp_path / "runs" / "run-2"
        run_dir.mkdir(parents=True)
        (run_dir / "gate.json").write_text('{"status":"pass"}', encoding="utf-8")
        (run_dir / "scorecard.json").write_text('{"status":"pass"}', encoding="utf-8")
        (run_dir / "trace.jsonl").write_text("", encoding="utf-8")

        class Completed:
            returncode = 0
            stdout = "run_id=run-2\nstatus=pass\nartifacts=/runs/run-2\n"
            stderr = ""

        return Completed()

    client = HarnessClient(harness_root, "python", executor="docker", command_runner=fake_run)
    client.run_task(str(task_path), "api", "gpt-5.5", str(tmp_path / "runs"), True, failure_context_path=str(failure_context))

    assert captured["args"][captured["args"].index("--failure-context") + 1] == "/runs/previous/failure_context.json"


def test_report_endpoint_adds_browser_security_headers(client, tmp_path, monkeypatch):
    from tests.test_api import FakeHarnessClient, create_task

    monkeypatch.setattr("app.main.harness_client", FakeHarnessClient(tmp_path / "harness_runs" / "fake-run"))
    task_id = create_task(client)
    created = client.post("/runs", json={"task_id": task_id}, headers={"Idempotency-Key": "headers"}).json()

    response = client.get(f"/runs/{created['run_id']}/report")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'none'" in response.headers["content-security-policy"]


def test_harness_client_kills_process_when_cancellation_probe_trips(tmp_path: Path):
    client = HarnessClient(tmp_path, sys.executable)
    started = time.monotonic()

    with pytest.raises(RuntimeError, match="cancelled"):
        client._run_command(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            env={},
            timeout_seconds=30,
            run_id=123,
            should_cancel=lambda: time.monotonic() - started > 0.2,
        )

    assert time.monotonic() - started < 5


class FakeRedisCacheClient:
    def __init__(self):
        self.values = {}
        self.expire_calls = []
        self.locks = {}

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, ttl, value):
        self.values[key] = value
        self.expire_calls.append((key, ttl))

    def lock(self, key, timeout):
        self.locks[key] = timeout
        return f"lock:{key}:{timeout}"


def test_redis_cache_round_trips_json_and_negative_entries():
    fake = FakeRedisCacheClient()
    cache = RedisCache(fake, default_ttl=10, negative_ttl=2, jitter=0)

    cache.set("run:1", {"status": "pass"})
    cache.set("run:404", "__missing__", negative=True)

    assert cache.get("run:1") == {"status": "pass"}
    assert cache.get("run:404") == "__missing__"
    assert fake.expire_calls == [("run:1", 10), ("run:404", 2)]


def test_redis_cache_lock_uses_prefixed_key():
    fake = FakeRedisCacheClient()
    cache = RedisCache(fake, default_ttl=10, negative_ttl=2, jitter=0)

    lock = cache.lock_for("run:1")

    assert lock == "lock:lock:run:1:10"


def test_cache_factory_falls_back_to_memory_when_redis_unavailable():
    cache = build_cache(
        enable_redis=True,
        redis_url="redis://127.0.0.1:1/0",
        default_ttl=10,
        negative_ttl=2,
        jitter=0,
    )

    assert isinstance(cache, MemoryCache)
