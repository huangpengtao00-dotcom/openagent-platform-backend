from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class DemoTask:
    task_id: str
    difficulty: str
    name: str
    goal: str
    files: list[dict[str, str]]
    test_files: list[dict[str, str]]


def file(path: str, content: str) -> dict[str, str]:
    return {"path": path, "content": content.strip() + "\n"}


def profile(
    name: str,
    model: str,
    provider: str | None = None,
    base_url: str | None = None,
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "name": name,
        "mode": "api",
        "model": model,
        "allow_llm_calls": True,
        "timeout_seconds": timeout_seconds,
    }
    if provider:
        item["model_provider"] = provider
    if base_url:
        item["base_url"] = base_url
        item["wire_api"] = "chat_completions"
    return item


MODEL_PROFILES = [
    profile("DeepSeek API", "deepseek-v4-flash", "deepseek"),
    profile("NewAPI 5.4", "gpt-5.4", "newapi-5.4", "https://api.sbbbbbbbbb.xyz/v1"),
    profile("NewAPI 5.5", "gpt-5.5", "newapi-5.5", "https://api.sbbbbbbbbb.xyz/v1"),
]


TASKS = [
    DemoTask(
        "E1",
        "easy",
        "E1 Easy - Duration Parser",
        "支持 10s、2m、1h；空值、格式错误或未知单位返回 0，不要抛异常。",
        [
            file(
                "duration_parser.py",
                '''
def parse_duration(value):
    amount = int(value[:-1])
    unit = value[-1]
    if unit == "s":
        return amount
    if unit == "m":
        return amount * 60
    return amount
''',
            )
        ],
        [
            file(
                "test_duration_parser.py",
                '''
from duration_parser import parse_duration


def test_parse_supported_units():
    assert parse_duration("10s") == 10
    assert parse_duration("2m") == 120
    assert parse_duration("1h") == 3600


def test_parse_invalid_inputs_return_zero():
    assert parse_duration("") == 0
    assert parse_duration(None) == 0
    assert parse_duration("abc") == 0
    assert parse_duration("3d") == 0
''',
            )
        ],
    ),
    DemoTask(
        "E2",
        "easy",
        "E2 Easy - Percent Clamp",
        "把百分比限制在 0 到 100；None 返回 0；字符串数字要能转换，非法字符串返回 0。",
        [
            file(
                "metrics.py",
                '''
def normalize_percent(value):
    return int(value)
''',
            )
        ],
        [
            file(
                "test_metrics.py",
                '''
from metrics import normalize_percent


def test_normal_percent_values():
    assert normalize_percent(25) == 25
    assert normalize_percent("88") == 88


def test_clamps_out_of_range_values():
    assert normalize_percent(-5) == 0
    assert normalize_percent(150) == 100


def test_invalid_values_return_zero():
    assert normalize_percent(None) == 0
    assert normalize_percent("bad") == 0
''',
            )
        ],
    ),
    DemoTask(
        "E3",
        "easy",
        "E3 Easy - Pagination Bounds",
        "修复分页边界：page 从 1 开始，小于 1 时按 1 处理；page_size 小于 1 时返回空列表。",
        [
            file(
                "pager.py",
                '''
def page_items(items, page, page_size):
    start = page * page_size
    end = start + page_size
    return items[start:end]
''',
            )
        ],
        [
            file(
                "test_pager.py",
                '''
from pager import page_items


def test_page_starts_at_one():
    assert page_items([1, 2, 3, 4, 5], 1, 2) == [1, 2]
    assert page_items([1, 2, 3, 4, 5], 2, 2) == [3, 4]


def test_page_bounds_are_normalized():
    assert page_items([1, 2, 3], 0, 2) == [1, 2]
    assert page_items([1, 2, 3], -10, 2) == [1, 2]
    assert page_items([1, 2, 3], 1, 0) == []
''',
            )
        ],
    ),
    DemoTask(
        "M1",
        "medium",
        "M1 Medium - Config Merge",
        "合并用户配置和默认配置，保留嵌套 headers，不能修改 DEFAULTS。",
        [
            file(
                "config_loader.py",
                '''
DEFAULTS = {
    "timeout": 3,
    "headers": {"User-Agent": "OpenAgent", "Accept": "application/json"},
}


class ConfigLoader:
    def __init__(self, defaults=None):
        self.defaults = defaults or DEFAULTS

    def load_config(self, user_config):
        if user_config is None:
            return self.defaults
        if not isinstance(user_config, dict):
            raise ValueError("user_config must be a dict")
        config = self.defaults
        for key, value in user_config.items():
            config[key] = value
        return config


def load_config(user_config):
    return ConfigLoader().load_config(user_config)
''',
            )
        ],
        [
            file(
                "test_config_loader.py",
                '''
from config_loader import DEFAULTS, load_config


def test_merges_nested_headers_without_losing_defaults():
    config = load_config({"headers": {"Authorization": "Bearer token"}})
    assert config["timeout"] == 3
    assert config["headers"]["User-Agent"] == "OpenAgent"
    assert config["headers"]["Accept"] == "application/json"
    assert config["headers"]["Authorization"] == "Bearer token"


def test_does_not_mutate_defaults():
    before = DEFAULTS.copy()
    before["headers"] = DEFAULTS["headers"].copy()
    load_config({"timeout": 10, "headers": {"X-Trace": "1"}})
    assert DEFAULTS == before


def test_invalid_config_raises_value_error():
    try:
        load_config(["bad"])
    except ValueError:
        return
    raise AssertionError("expected ValueError")
''',
            )
        ],
    ),
    DemoTask(
        "M2",
        "medium",
        "M2 Medium - Artifact Search Filters",
        "支持按 status 和 tag 过滤；分页不能越界；缺少 tags 字段时按空列表处理。",
        [
            file(
                "artifact_search.py",
                '''
ARTIFACTS = [
    {"id": 1, "status": "pass", "tags": ["patch", "trace"]},
    {"id": 2, "status": "fail", "tags": ["cost"]},
    {"id": 3, "status": "pass"},
]


class ArtifactSearch:
    def __init__(self, rows=None):
        self.rows = rows or ARTIFACTS

    def search_artifacts(self, status=None, tag=None, page=1, page_size=10):
        rows = self.rows
        if status:
            rows = [row for row in rows if row["status"] == status]
        if tag:
            rows = [row for row in rows if tag in row["tags"]]
        if page < 1:
            raise ValueError("page must start from 1")
        start = page * page_size
        return rows[start:start + page_size]


def search_artifacts(status=None, tag=None, page=1, page_size=10):
    return ArtifactSearch().search_artifacts(status, tag, page, page_size)
''',
            )
        ],
        [
            file(
                "test_artifact_search.py",
                '''
from artifact_search import search_artifacts


def test_filters_by_status():
    assert [row["id"] for row in search_artifacts(status="pass")] == [1, 3]


def test_filters_by_tag_and_handles_missing_tags():
    assert [row["id"] for row in search_artifacts(tag="trace")] == [1]
    assert search_artifacts(tag="missing") == []


def test_pagination_starts_at_one_and_handles_bad_size():
    assert [row["id"] for row in search_artifacts(page=1, page_size=2)] == [1, 2]
    assert [row["id"] for row in search_artifacts(page=2, page_size=2)] == [3]
    assert search_artifacts(page=1, page_size=0) == []
''',
            )
        ],
    ),
    DemoTask(
        "M3",
        "medium",
        "M3 Medium - Usage Cost Rollup",
        "按 provider 聚合 token 和 cost；没有 usage 的 provider 也要保留 0 成本行；输出按 provider 名排序。",
        [
            file(
                "cost_rollup.py",
                '''
def rollup_cost(rows, providers):
    result = {}
    for row in rows:
        key = row["provider"]
        if key not in result:
            result[key] = {"provider": key, "runs": 0, "tokens": 0, "cost": 0.0}
        result[key]["runs"] += 1
        result[key]["tokens"] += row["tokens"]
        result[key]["cost"] += row["cost"]
    return list(result.values())
''',
            )
        ],
        [
            file(
                "test_cost_rollup.py",
                '''
from cost_rollup import rollup_cost


def test_rolls_up_by_provider():
    rows = [
        {"provider": "newapi-5.4", "tokens": 100, "cost": 0.01},
        {"provider": "newapi-5.4", "tokens": 50, "cost": 0.02},
        {"provider": "newapi-5.5", "tokens": 70, "cost": 0.03},
    ]
    result = rollup_cost(rows, ["deepseek", "newapi-5.4", "newapi-5.5"])
    by_provider = {item["provider"]: item for item in result}
    assert by_provider["newapi-5.4"]["runs"] == 2
    assert by_provider["newapi-5.4"]["tokens"] == 150
    assert round(by_provider["newapi-5.4"]["cost"], 2) == 0.03


def test_keeps_zero_rows_and_sorts_by_provider():
    result = rollup_cost([], ["newapi-5.5", "deepseek", "newapi-5.4"])
    assert [item["provider"] for item in result] == ["deepseek", "newapi-5.4", "newapi-5.5"]
    assert all(item["runs"] == 0 and item["tokens"] == 0 and item["cost"] == 0.0 for item in result)
''',
            )
        ],
    ),
    DemoTask(
        "H1",
        "hard",
        "H1 Hard - Async Retry Client",
        "实现异步请求重试：429 和 timeout 可以重试，最多 retries 次；非 2xx 直接返回错误；成功返回 JSON。",
        [
            file(
                "async_client.py",
                '''
import asyncio


class ApiClient:
    def __init__(self, session, retries=2):
        self.session = session
        self.retries = retries

    async def fetch_json(self, url):
        response = await self.session.get(url)
        if response.status == 429:
            await asyncio.sleep(0.1)
            response = await self.session.get(url)
        if response.status >= 400:
            return {"ok": False, "status": response.status}
        return await response.json()
''',
            )
        ],
        [
            file(
                "test_async_client.py",
                '''
import asyncio

from async_client import ApiClient


class Response:
    def __init__(self, status, payload=None):
        self.status = status
        self._payload = payload or {"ok": True}

    async def json(self):
        return self._payload


class Session:
    def __init__(self, events):
        self.events = list(events)
        self.calls = 0

    async def get(self, url):
        self.calls += 1
        event = self.events.pop(0)
        if event == "timeout":
            raise TimeoutError("timeout")
        return event


def run(coro):
    return asyncio.run(coro)


def test_retries_429_until_success():
    session = Session([Response(429), Response(429), Response(200, {"value": 1})])
    assert run(ApiClient(session, retries=3).fetch_json("/x")) == {"value": 1}
    assert session.calls == 3


def test_retries_timeout_until_success():
    session = Session(["timeout", Response(200, {"value": 2})])
    assert run(ApiClient(session, retries=2).fetch_json("/x")) == {"value": 2}
    assert session.calls == 2


def test_non_retryable_error_returns_error_immediately():
    session = Session([Response(500), Response(200)])
    assert run(ApiClient(session, retries=2).fetch_json("/x")) == {"ok": False, "status": 500}
    assert session.calls == 1
''',
            )
        ],
    ),
    DemoTask(
        "H2",
        "hard",
        "H2 Hard - Worker Queue Claim",
        "实现 run 队列抢占：重复入队不应重复执行；已取消和已完成的 run 要跳过；并发 claim 只能有一个 worker 成功。",
        [
            file(
                "worker_queue.py",
                '''
import threading


class RunQueue:
    def __init__(self):
        self.pending = []
        self.running = set()
        self.done = set()
        self.cancelled = set()
        self.lock = threading.Lock()

    def enqueue(self, run_id):
        self.pending.append(run_id)

    def cancel(self, run_id):
        self.cancelled.add(run_id)

    def complete(self, run_id):
        self.done.add(run_id)

    def claim_next(self):
        if not self.pending:
            return None
        run_id = self.pending.pop(0)
        self.running.add(run_id)
        return run_id
''',
            )
        ],
        [
            file(
                "test_worker_queue.py",
                '''
import threading

from worker_queue import RunQueue


def test_duplicate_enqueue_claims_once():
    queue = RunQueue()
    queue.enqueue(7)
    queue.enqueue(7)
    assert queue.claim_next() == 7
    assert queue.claim_next() is None


def test_skips_cancelled_and_completed_runs():
    queue = RunQueue()
    queue.enqueue(1)
    queue.enqueue(2)
    queue.enqueue(3)
    queue.cancel(1)
    queue.complete(2)
    assert queue.claim_next() == 3
    assert queue.claim_next() is None


def test_concurrent_claims_are_unique():
    queue = RunQueue()
    for run_id in [1, 2, 3]:
        queue.enqueue(run_id)
    claimed = []

    def worker():
        item = queue.claim_next()
        if item is not None:
            claimed.append(item)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(claimed) == [1, 2, 3]
    assert queue.claim_next() is None
''',
            )
        ],
    ),
    DemoTask(
        "H3",
        "hard",
        "H3 Hard - Artifact Path Resolver",
        "安全解析 artifact 路径：只能读取 root 内部文件；禁止绝对路径和路径穿越；缺文件返回 FileNotFoundError。",
        [
            file(
                "artifact_resolver.py",
                '''
from pathlib import Path


class ArtifactResolver:
    def __init__(self, root):
        self.root = Path(root)

    def read_text(self, name):
        path = self.root / name
        return path.read_text(encoding="utf-8")
''',
            )
        ],
        [
            file(
                "test_artifact_resolver.py",
                '''
from pathlib import Path

import pytest

from artifact_resolver import ArtifactResolver


def test_reads_file_inside_root(tmp_path):
    (tmp_path / "report.txt").write_text("ok", encoding="utf-8")
    resolver = ArtifactResolver(tmp_path)
    assert resolver.read_text("report.txt") == "ok"


def test_rejects_path_traversal(tmp_path):
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    resolver = ArtifactResolver(tmp_path)
    with pytest.raises(ValueError):
        resolver.read_text("../outside.txt")


def test_rejects_absolute_paths(tmp_path):
    resolver = ArtifactResolver(tmp_path)
    with pytest.raises(ValueError):
        resolver.read_text(str(Path(tmp_path / "report.txt").resolve()))


def test_missing_file_raises_file_not_found(tmp_path):
    resolver = ArtifactResolver(tmp_path)
    with pytest.raises(FileNotFoundError):
        resolver.read_text("missing.txt")
''',
            )
        ],
    ),
]


def request_json(
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    data = None
    request_headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json; charset=utf-8"
    if headers:
        request_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = resp.read().decode("utf-8")
    return json.loads(payload) if payload else None


def request_json_with_retry(
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    attempts: int = 4,
) -> Any:
    for attempt in range(1, attempts + 1):
        try:
            return request_json(method, url, body=body, headers=headers)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code == 429 and attempt < attempts:
                wait_seconds = 65
                print(f"create hit 429, waiting {wait_seconds}s before retry {attempt + 1}/{attempts}: {detail}")
                time.sleep(wait_seconds)
                continue
            raise RuntimeError(f"HTTP {exc.code} from {url}: {detail}") from exc


def wait_evaluation(
    api_url: str,
    evaluation_id: int,
    headers: dict[str, str],
    poll_seconds: int,
    max_wait_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + max_wait_seconds
    matrix_url = f"{api_url}/evaluations/{evaluation_id}/matrix"
    while time.monotonic() < deadline:
        matrix = request_json("GET", matrix_url, headers=headers)
        print(
            "eval={evaluation_id} status={status} pass={passed} fail={failed} "
            "running={running} pending={pending} cost=${cost}".format(
                evaluation_id=evaluation_id,
                status=matrix["status"],
                passed=matrix["passed"],
                failed=matrix["failed"],
                running=matrix["running"],
                pending=matrix["pending"],
                cost=matrix["estimated_cost_usd"],
            ),
            flush=True,
        )
        if matrix["pending"] == 0 and matrix["running"] == 0:
            return matrix
        time.sleep(poll_seconds)
    raise TimeoutError(f"timed out waiting for evaluation {evaluation_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed 9 interview benchmark evaluations into the live OpenAgent demo.")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--workspace-id", default="interview-demo")
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--user-prefix", default="interview-seed")
    parser.add_argument("--poll-seconds", type=int, default=8)
    parser.add_argument("--max-wait-seconds", type=int, default=420)
    parser.add_argument("--no-wait", action="store_true")
    args = parser.parse_args()

    base_headers = {
        "X-Tenant-ID": args.tenant_id,
        "X-Workspace-ID": args.workspace_id,
    }
    run_started_at = datetime.now().strftime("%Y%m%d-%H%M%S")
    created: list[dict[str, Any]] = []

    for task in TASKS:
        body = {
            "name": task.name,
            "goal": task.goal,
            "files": task.files,
            "test_files": task.test_files,
            "model_profiles": MODEL_PROFILES,
            "acceptance_command": "python -m pytest -q",
            "context_summary_files": 16,
        }
        headers = {
            **base_headers,
            "X-User-ID": f"{args.user_prefix}-{task.task_id}",
            "Idempotency-Key": f"seed-9-{run_started_at}-{task.task_id}",
        }
        print(f"creating {task.task_id} {task.name} [{task.difficulty}]", flush=True)
        response = request_json_with_retry("POST", f"{args.api_url}/evaluations", body=body, headers=headers)
        item = {
            "task_id": task.task_id,
            "difficulty": task.difficulty,
            "name": task.name,
            "evaluation_id": response["evaluation_id"],
            "platform_task_id": response["task"]["task_id"],
            "run_ids": [run["run_id"] for run in response["runs"]],
            "status": "created",
            "passed": 0,
            "failed": 0,
            "cost": 0,
        }
        if not args.no_wait:
            matrix = wait_evaluation(
                args.api_url,
                response["evaluation_id"],
                base_headers,
                args.poll_seconds,
                args.max_wait_seconds,
            )
            item.update(
                {
                    "status": matrix["status"],
                    "passed": matrix["passed"],
                    "failed": matrix["failed"],
                    "cost": matrix["estimated_cost_usd"],
                }
            )
        created.append(item)

    print("\nseeded evaluations")
    for item in created:
        print(
            "{task_id} {difficulty} eval={evaluation_id} runs={run_ids} "
            "status={status} pass={passed} fail={failed} cost=${cost}".format(**item)
        )

    history = request_json("GET", f"{args.api_url}/evaluations/history?limit=30", headers=base_headers)
    print("\nrecent history")
    for item in history[:15]:
        print(
            "eval={evaluation_id} task={task_id} status={status} runs={run_count} "
            "pass={passed} fail={failed} pass_rate={pass_rate:.2f} cost=${estimated_cost_usd} name={name}".format(
                **item
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
