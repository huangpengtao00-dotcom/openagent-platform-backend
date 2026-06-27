from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


def _float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return float(value)


def _default_harness_root_for_backend(backend_root: Path) -> Path:
    bundle_root = backend_root.parent
    candidates = [
        bundle_root / "02_OpenAgent_Harness",
        bundle_root / "OpenAgent-Harness",
    ]
    for candidate in candidates:
        if (candidate / "pyproject.toml").exists() and (candidate / "src" / "openagent_harness" / "cli.py").exists():
            return candidate.resolve()
    return (bundle_root / "02_OpenAgent_Harness").resolve()


def _default_harness_root() -> Path:
    return _default_harness_root_for_backend(Path(__file__).resolve().parents[1])


def _queue_backend() -> str:
    raw = os.getenv("QUEUE_BACKEND", os.getenv("RUN_QUEUE_BACKEND", "db")).strip().lower()
    aliases = {
        "database": "db",
        "polling": "db",
        "dbpolling": "db",
    }
    return aliases.get(raw, raw)


@dataclass
class Settings:
    app_env: str
    database_url: str
    redis_url: str
    enable_redis: bool
    harness_root: Path
    harness_python: str
    harness_pythonpath: str
    harness_runs_root: Path
    harness_default_model: str
    harness_executor: str
    harness_docker_image: str
    harness_container_root: str
    harness_container_runs_root: str
    evaluation_memory_path: Path
    rate_limit_runs_per_minute: int
    cache_default_ttl_seconds: int
    cache_negative_ttl_seconds: int
    cache_ttl_jitter_seconds: int
    allow_real_llm_calls: bool
    auto_start_runs: bool
    run_queue_backend: str
    run_queue_key: str
    real_api_budget_limit_cny: float
    usd_to_cny_rate: float


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        app_env=os.getenv("APP_ENV", "dev"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./openagent_platform.db"),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        enable_redis=_bool("ENABLE_REDIS", False),
        harness_root=Path(os.getenv("HARNESS_ROOT")).resolve() if os.getenv("HARNESS_ROOT") else _default_harness_root(),
        harness_python=os.getenv("HARNESS_PYTHON", "python"),
        harness_pythonpath=os.getenv("HARNESS_PYTHONPATH", "src"),
        harness_runs_root=Path(os.getenv("HARNESS_RUNS_ROOT", "./artifacts/harness_runs")).resolve(),
        harness_default_model=os.getenv("HARNESS_DEFAULT_MODEL", "deepseek-v4-flash"),
        harness_executor=os.getenv("HARNESS_EXECUTOR", "local").strip().lower(),
        harness_docker_image=os.getenv("HARNESS_DOCKER_IMAGE", "openagent-harness:latest"),
        harness_container_root=os.getenv("HARNESS_CONTAINER_ROOT", "/harness"),
        harness_container_runs_root=os.getenv("HARNESS_CONTAINER_RUNS_ROOT", "/runs"),
        evaluation_memory_path=Path(os.getenv("EVALUATION_MEMORY_PATH", "./artifacts/evaluation_memory.jsonl")).resolve(),
        rate_limit_runs_per_minute=_int("RATE_LIMIT_RUNS_PER_MINUTE", 5),
        cache_default_ttl_seconds=_int("CACHE_DEFAULT_TTL_SECONDS", 300),
        cache_negative_ttl_seconds=_int("CACHE_NEGATIVE_TTL_SECONDS", 60),
        cache_ttl_jitter_seconds=_int("CACHE_TTL_JITTER_SECONDS", 60),
        allow_real_llm_calls=_bool("ALLOW_REAL_LLM_CALLS", True),
        auto_start_runs=_bool("AUTO_START_RUNS", True),
        run_queue_backend=_queue_backend(),
        run_queue_key=os.getenv("RUN_QUEUE_KEY", "openagent:runs"),
        real_api_budget_limit_cny=_float("REAL_API_BUDGET_LIMIT_CNY", 1.0),
        usd_to_cny_rate=_float("USD_TO_CNY_RATE", 7.25),
    )
