from __future__ import annotations

import os
import subprocess
import time
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


class HarnessClient:
    def __init__(
        self,
        harness_root: Path,
        python: str,
        pythonpath: str = "src",
        command_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        process_registry: ProcessRegistry | None = None,
    ) -> None:
        self.harness_root = Path(harness_root).resolve()
        self.python = python
        self.pythonpath = pythonpath
        self.command_runner = command_runner
        self.process_registry = process_registry

    def run_task(
        self,
        task_spec_path: str,
        mode: str,
        model: str,
        runs_root: str,
        allow_llm_calls: bool,
        timeout_seconds: int | None = None,
        run_id: int | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> HarnessRunResult:
        runs_root_path = Path(runs_root).resolve()
        runs_root_path.mkdir(parents=True, exist_ok=True)
        args = [
            self.python,
            "-m",
            "openagent_harness.cli",
            "run",
            task_spec_path,
            "--mode",
            mode,
            "--model",
            model,
            "--runs",
            str(runs_root_path),
        ]
        if allow_llm_calls:
            args.append("--allow-llm-calls")

        env = os.environ.copy()
        env.update(_load_harness_env(self.harness_root))
        extra_pythonpath = str((self.harness_root / self.pythonpath).resolve())
        env["PYTHONPATH"] = extra_pythonpath + os.pathsep + env.get("PYTHONPATH", "")
        completed = self._run_command(args, env, timeout_seconds, run_id, should_cancel)
        if completed.returncode != 0:
            output = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(output or f"harness exited with {completed.returncode}")

        fields = _parse_stdout_fields(completed.stdout)
        run_dir = Path(fields.get("artifacts") or _latest_child(runs_root_path)).resolve()
        gate = read_json(run_dir / "gate.json") if (run_dir / "gate.json").exists() else {}
        scorecard = read_json(run_dir / "scorecard.json") if (run_dir / "scorecard.json").exists() else {}
        status = str(scorecard.get("status") or gate.get("status") or fields.get("status") or "fail")
        failure_type = _normalize_failure_type(scorecard.get("failure_type") or gate.get("failure_type") or fields.get("failure_type"))
        return HarnessRunResult(
            harness_run_id=str(fields.get("run_id") or run_dir.name),
            artifacts_dir=run_dir,
            status="pass" if status == "pass" else "fail",
            failure_type=failure_type,
            usage=parse_usage_from_artifacts(run_dir, fallback_model=model),
        )

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


def _load_harness_env(harness_root: Path) -> dict[str, str]:
    env_path = harness_root / ".env"
    if not env_path.exists():
        return {}
    values = dotenv_values(env_path)
    return {key: value for key, value in values.items() if key and value is not None}


def _latest_child(root: Path) -> Path:
    children = [item for item in root.iterdir() if item.is_dir()]
    if not children:
        raise FileNotFoundError(f"no harness run dir under {root}")
    return max(children, key=lambda item: item.stat().st_mtime)
