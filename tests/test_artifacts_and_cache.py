from __future__ import annotations

import json
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
