from __future__ import annotations

import os
import subprocess
import threading
import time


class ProcessRegistry:
    """Track running Harness subprocesses so API cancellation can reach the OS process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._processes: dict[int, subprocess.Popen[str]] = {}

    def register(self, run_id: int, process: subprocess.Popen[str]) -> None:
        with self._lock:
            self._processes[run_id] = process

    def unregister(self, run_id: int) -> None:
        with self._lock:
            self._processes.pop(run_id, None)

    def cancel(self, run_id: int) -> bool:
        with self._lock:
            process = self._processes.get(run_id)
        if process is None:
            return False
        _terminate_process_tree(process)
        self.unregister(run_id)
        return True


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            text=True,
            capture_output=True,
            check=False,
        )
        deadline = time.monotonic() + 1.0
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if process.poll() is None:
            process.kill()
            deadline = time.monotonic() + 1.0
            while process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
        return
    process.terminate()
    deadline = time.monotonic() + 1.0
    while process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    if process.poll() is None:
        process.kill()
        deadline = time.monotonic() + 1.0
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
