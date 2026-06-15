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
    rate_limit_runs_per_minute: int
    cache_default_ttl_seconds: int
    cache_negative_ttl_seconds: int
    cache_ttl_jitter_seconds: int
    allow_real_llm_calls: bool
    auto_start_runs: bool


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        app_env=os.getenv("APP_ENV", "dev"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./openagent_platform.db"),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        enable_redis=_bool("ENABLE_REDIS", False),
        harness_root=Path(os.getenv("HARNESS_ROOT", "../OpenAgent-Harness-v1-final")).resolve(),
        harness_python=os.getenv("HARNESS_PYTHON", "python"),
        harness_pythonpath=os.getenv("HARNESS_PYTHONPATH", "src"),
        harness_runs_root=Path(os.getenv("HARNESS_RUNS_ROOT", "./artifacts/harness_runs")).resolve(),
        harness_default_model=os.getenv("HARNESS_DEFAULT_MODEL", "deepseek-v4-flash"),
        rate_limit_runs_per_minute=_int("RATE_LIMIT_RUNS_PER_MINUTE", 5),
        cache_default_ttl_seconds=_int("CACHE_DEFAULT_TTL_SECONDS", 300),
        cache_negative_ttl_seconds=_int("CACHE_NEGATIVE_TTL_SECONDS", 60),
        cache_ttl_jitter_seconds=_int("CACHE_TTL_JITTER_SECONDS", 60),
        allow_real_llm_calls=_bool("ALLOW_REAL_LLM_CALLS", False),
        auto_start_runs=_bool("AUTO_START_RUNS", True),
    )
