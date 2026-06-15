from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .artifacts import parse_usage_from_artifacts, read_json


@dataclass(frozen=True)
class HarnessRunResult:
    harness_run_id: str
    artifacts_dir: Path
    status: str
    failure_type: str | None
    usage: dict


class HarnessClient:
    def __init__(self, harness_root: Path, python: str, pythonpath: str = "src") -> None:
        self.harness_root = Path(harness_root).resolve()
        self.python = python
        self.pythonpath = pythonpath

    def run_task(
        self,
        task_spec_path: str,
        mode: str,
        model: str,
        runs_root: str,
        allow_llm_calls: bool,
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
        extra_pythonpath = str((self.harness_root / self.pythonpath).resolve())
        env["PYTHONPATH"] = extra_pythonpath + os.pathsep + env.get("PYTHONPATH", "")
        completed = subprocess.run(
            args,
            cwd=self.harness_root,
            env=env,
            text=True,
            capture_output=True,
            timeout=None,
            check=False,
        )
        if completed.returncode != 0:
            output = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(output or f"harness exited with {completed.returncode}")

        fields = _parse_stdout_fields(completed.stdout)
        run_dir = Path(fields.get("artifacts") or _latest_child(runs_root_path)).resolve()
        gate = read_json(run_dir / "gate.json") if (run_dir / "gate.json").exists() else {}
        scorecard = read_json(run_dir / "scorecard.json") if (run_dir / "scorecard.json").exists() else {}
        status = str(scorecard.get("status") or gate.get("status") or fields.get("status") or "fail")
        failure_type = scorecard.get("failure_type") or gate.get("failure_type") or fields.get("failure_type")
        return HarnessRunResult(
            harness_run_id=str(fields.get("run_id") or run_dir.name),
            artifacts_dir=run_dir,
            status="pass" if status == "pass" else "fail",
            failure_type=str(failure_type) if failure_type else None,
            usage=parse_usage_from_artifacts(run_dir, fallback_model=model),
        )


def _parse_stdout_fields(output: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            fields[key.strip()] = value.strip()
    return fields


def _latest_child(root: Path) -> Path:
    children = [item for item in root.iterdir() if item.is_dir()]
    if not children:
        raise FileNotFoundError(f"no harness run dir under {root}")
    return max(children, key=lambda item: item.stat().st_mtime)

