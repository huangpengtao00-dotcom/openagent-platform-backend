from __future__ import annotations

import os
import subprocess
import time
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from dotenv import dotenv_values

from .artifacts import parse_usage_from_artifacts, read_json
from .process_manager import ProcessRegistry, _terminate_process_tree


@dataclass(frozen=True)
class HarnessRunResult:
    harness_run_id: str
    artifacts_dir: Path
    status: str
    failure_type: str | None
    usage: dict
    error_message: str | None = None


_DOCKER_ENV_NAMES = {
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "OPENAGENT_API_KEY",
    "OPENAGENT_BASE_URL",
    "OPENAGENT_WIRE_API",
    "OPENAGENT_DISABLE_RESPONSE_STORAGE",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_WIRE_API",
    "OPENAI_DISABLE_RESPONSE_STORAGE",
}


class HarnessClient:
    def __init__(
        self,
        harness_root: Path,
        python: str,
        pythonpath: str = "src",
        *,
        executor: str = "local",
        docker_image: str = "openagent-harness:latest",
        container_harness_root: str = "/harness",
        container_runs_root: str = "/runs",
        command_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        process_registry: ProcessRegistry | None = None,
    ) -> None:
        self.harness_root = Path(harness_root).resolve()
        self.python = python
        self.pythonpath = pythonpath
        self.executor = executor
        self.docker_image = docker_image
        self.container_harness_root = container_harness_root.rstrip("/") or "/harness"
        self.container_runs_root = container_runs_root.rstrip("/") or "/runs"
        self.command_runner = command_runner
        self.process_registry = process_registry

    def run_task(
        self,
        task_spec_path: str,
        mode: str,
        model: str,
        runs_root: str,
        allow_llm_calls: bool,
        model_provider: str | None = None,
        base_url: str | None = None,
        wire_api: str | None = None,
        reasoning_effort: str | None = None,
        disable_response_storage: bool = False,
        timeout_seconds: int | None = None,
        failure_context_path: str | None = None,
        run_id: int | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> HarnessRunResult:
        runs_root_path = Path(runs_root).resolve()
        runs_root_path.mkdir(parents=True, exist_ok=True)
        task_arg = str(Path(task_spec_path).resolve())
        runs_arg = str(runs_root_path)
        failure_context_arg = str(Path(failure_context_path).resolve()) if failure_context_path else None
        if self.executor == "docker":
            task_arg = self._docker_task_spec(task_spec_path, runs_root_path, run_id)
            runs_arg = self.container_runs_root
            failure_context_arg = self._host_to_container_path(Path(failure_context_path).resolve(), runs_root_path) if failure_context_path else None

        inner_args = [
            self.python,
            "-m",
            "openagent_harness.cli",
            "run",
            task_arg,
            "--mode",
            mode,
            "--model",
            model,
            "--runs",
            runs_arg,
        ]
        if allow_llm_calls:
            inner_args.append("--allow-llm-calls")
        if base_url:
            inner_args.extend(["--base-url", base_url])
        if wire_api:
            inner_args.extend(["--wire-api", wire_api])
        if reasoning_effort:
            inner_args.extend(["--reasoning-effort", reasoning_effort])
        if disable_response_storage:
            inner_args.append("--disable-response-storage")
        if failure_context_arg:
            inner_args.extend(["--failure-context", failure_context_arg])

        env = os.environ.copy()
        env.update(_load_harness_env(self.harness_root))
        _apply_provider_env(env, model_provider=model_provider, base_url=base_url, wire_api=wire_api)
        extra_pythonpath = str((self.harness_root / self.pythonpath).resolve())
        env["PYTHONPATH"] = extra_pythonpath + os.pathsep + env.get("PYTHONPATH", "")
        args = self._docker_args(inner_args, runs_root_path, env) if self.executor == "docker" else inner_args
        completed = self._run_command(args, env, timeout_seconds, run_id, should_cancel)
        if completed.returncode != 0:
            output = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(output or f"harness exited with {completed.returncode}")

        fields = _parse_stdout_fields(completed.stdout)
        if self.executor == "docker" and fields.get("artifacts"):
            fields["artifacts"] = self._container_to_host_path(fields["artifacts"], runs_root_path)
        run_dir = _resolve_run_dir_from_stdout(fields, runs_root_path)
        gate = read_json(run_dir / "gate.json") if (run_dir / "gate.json").exists() else {}
        scorecard = read_json(run_dir / "scorecard.json") if (run_dir / "scorecard.json").exists() else {}
        status = str(scorecard.get("status") or gate.get("status") or fields.get("status") or "fail")
        failure_type = _normalize_failure_type(scorecard.get("failure_type") or gate.get("failure_type") or fields.get("failure_type"))
        error_message = _failure_message_from_artifacts(run_dir)
        return HarnessRunResult(
            harness_run_id=str(fields.get("run_id") or run_dir.name),
            artifacts_dir=run_dir,
            status="pass" if status == "pass" else "fail",
            failure_type=failure_type,
            usage=parse_usage_from_artifacts(run_dir, fallback_model=model),
            error_message=error_message,
        )

    def _docker_args(self, inner_args: list[str], runs_root_path: Path, env: dict[str, str]) -> list[str]:
        args = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{self.harness_root}:{self.container_harness_root}:ro",
            "-v",
            f"{runs_root_path}:{self.container_runs_root}",
            "-w",
            self.container_harness_root,
            "-e",
            f"PYTHONPATH={self.container_harness_root}/{self.pythonpath}",
        ]
        for name in sorted(_DOCKER_ENV_NAMES):
            if env.get(name):
                args.extend(["-e", name])
        args.append(self.docker_image)
        args.extend(inner_args)
        return args

    def _docker_task_spec(self, task_spec_path: str, runs_root_path: Path, run_id: int | None) -> str:
        spec_path = Path(task_spec_path)
        if not spec_path.is_absolute():
            spec_path = self.harness_root / spec_path
        spec_path = spec_path.resolve()
        data = json.loads(spec_path.read_text(encoding="utf-8"))
        repo = Path(str(data["repo"]))
        if repo.is_absolute():
            data["repo"] = self._host_to_container_path(repo.resolve(), runs_root_path)
        spec_dir = runs_root_path / ".docker_specs"
        spec_dir.mkdir(parents=True, exist_ok=True)
        docker_spec = spec_dir / f"run-{run_id or uuid.uuid4().hex}.json"
        docker_spec.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return self._host_to_container_path(docker_spec, runs_root_path)

    def _host_to_container_path(self, path: Path, runs_root_path: Path) -> str:
        resolved = Path(path).resolve()
        if resolved == self.harness_root or self.harness_root in resolved.parents:
            return _join_container_path(self.container_harness_root, resolved.relative_to(self.harness_root).as_posix())
        if resolved == runs_root_path or runs_root_path in resolved.parents:
            return _join_container_path(self.container_runs_root, resolved.relative_to(runs_root_path).as_posix())
        raise RuntimeError(f"path is not mounted for docker harness executor: {resolved}")

    def _container_to_host_path(self, value: str, runs_root_path: Path) -> str:
        normalized = value.replace("\\", "/")
        prefix = self.container_runs_root.rstrip("/")
        if normalized == prefix:
            return str(runs_root_path)
        if normalized.startswith(prefix + "/"):
            return str((runs_root_path / normalized[len(prefix) + 1 :]).resolve())
        return value

    def _run_command(
        self,
        args: list[str],
        env: dict[str, str],
        timeout_seconds: int | None,
        run_id: int | None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if self.command_runner is not None:
            return self.command_runner(
                args,
                cwd=self.harness_root,
                env=env,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )

        creationflags = 0
        start_new_session = False
        if os.name == "posix":
            start_new_session = True
        elif os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

        process = subprocess.Popen(
            args,
            cwd=self.harness_root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=start_new_session,
            creationflags=creationflags,
        )
        if run_id is not None and self.process_registry is not None:
            self.process_registry.register(run_id, process)
        try:
            stdout, stderr = self._communicate_until_done(process, args, timeout_seconds, should_cancel)
        finally:
            if run_id is not None and self.process_registry is not None:
                self.process_registry.unregister(run_id)

        return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)

    def _communicate_until_done(
        self,
        process: subprocess.Popen[str],
        args: list[str],
        timeout_seconds: int | None,
        should_cancel: Callable[[], bool] | None,
    ) -> tuple[str, str]:
        started = time.monotonic()
        while True:
            if should_cancel is not None and should_cancel():
                _terminate_process_tree(process)
                stdout, stderr = process.communicate()
                raise RuntimeError("run cancelled")

            poll_timeout = 0.2
            if timeout_seconds is not None:
                remaining = timeout_seconds - (time.monotonic() - started)
                if remaining <= 0:
                    _terminate_process_tree(process)
                    stdout, stderr = process.communicate()
                    raise subprocess.TimeoutExpired(
                        cmd=args,
                        timeout=timeout_seconds,
                        output=stdout,
                        stderr=stderr,
                    )
                poll_timeout = min(poll_timeout, remaining)

            try:
                return process.communicate(timeout=poll_timeout)
            except subprocess.TimeoutExpired:
                continue


def _parse_stdout_fields(output: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            fields[key.strip()] = value.strip()
    return fields


def _normalize_failure_type(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "nil"}:
        return None
    return text


def _failure_message_from_artifacts(run_dir: Path) -> str | None:
    candidates: list[object] = []
    api_run_path = run_dir / "api_agent_run.json"
    if api_run_path.exists():
        api_run = read_json(api_run_path)
        candidates.extend([api_run.get("summary"), api_run.get("error"), api_run.get("message")])
    test_result_path = run_dir / "test_result.json"
    if test_result_path.exists():
        test_result = read_json(test_result_path)
        candidates.extend([test_result.get("stderr"), test_result.get("stdout")])
    for candidate in candidates:
        if candidate is None:
            continue
        text = str(candidate).strip()
        if text and text.lower() not in {"none", "null", "nil"}:
            return text[:1200]
    return None


def _join_container_path(root: str, relative: str) -> str:
    if not relative:
        return root
    return f"{root.rstrip('/')}/{relative}"


def _load_harness_env(harness_root: Path) -> dict[str, str]:
    env_path = harness_root / ".env"
    if not env_path.exists():
        return {}
    values = dotenv_values(env_path)
    return {key: value for key, value in values.items() if key and value is not None}


def _apply_provider_env(env: dict[str, str], *, model_provider: str | None, base_url: str | None, wire_api: str | None) -> None:
    provider = _normalize_provider_name(model_provider)
    provider_key_env = _provider_key_env(provider)
    if provider_key_env and env.get(provider_key_env):
        env["OPENAGENT_API_KEY"] = env[provider_key_env]
        env["OPENAI_API_KEY"] = env[provider_key_env]
    if base_url:
        env["OPENAGENT_BASE_URL"] = base_url
        env["OPENAI_BASE_URL"] = base_url
    elif provider.startswith("newapi") and env.get("NEWAPI_BASE_URL"):
        env["OPENAGENT_BASE_URL"] = env["NEWAPI_BASE_URL"]
        env["OPENAI_BASE_URL"] = env["NEWAPI_BASE_URL"]
    if wire_api:
        env["OPENAGENT_WIRE_API"] = wire_api
        env["OPENAI_WIRE_API"] = wire_api


def _normalize_provider_name(value: str | None) -> str:
    return (value or "").strip().lower().replace("_", "-").replace(" ", "-")


def _provider_key_env(provider: str) -> str | None:
    aliases = {
        "newapi-5.4": "NEWAPI_5_4_API_KEY",
        "newapi-5-4": "NEWAPI_5_4_API_KEY",
        "gpt-5.4-newapi": "NEWAPI_5_4_API_KEY",
        "newapi-5.5": "NEWAPI_5_5_API_KEY",
        "newapi-5-5": "NEWAPI_5_5_API_KEY",
        "gpt-5.5-newapi": "NEWAPI_5_5_API_KEY",
    }
    return aliases.get(provider)


def _resolve_run_dir_from_stdout(fields: dict[str, str], runs_root: Path) -> Path:
    if fields.get("artifacts"):
        run_dir = Path(fields["artifacts"]).resolve()
    elif fields.get("run_id"):
        run_dir = (runs_root / fields["run_id"]).resolve()
    else:
        raise RuntimeError("harness output did not include artifacts or run_id")
    if runs_root != run_dir and runs_root not in run_dir.parents:
        raise RuntimeError(f"harness artifacts path escaped runs root: {run_dir}")
    if not run_dir.is_dir():
        raise FileNotFoundError(f"harness run dir not found: {run_dir}")
    return run_dir
