#!/usr/bin/env python3
"""Run FastAPI (8765) and Vite dashboard (5173) together; prefixed logs; clean shutdown on Ctrl+C."""

from __future__ import annotations

import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = REPO_ROOT / "dashboard"

API_PREFIX = "[API] "
UI_PREFIX = "[UI]  "


def _pump_stdout(proc: subprocess.Popen[str], prefix: str) -> None:
    if proc.stdout is None:
        return
    for line in iter(proc.stdout.readline, ""):
        if line == "" and proc.poll() is not None:
            break
        sys.stdout.write(prefix + line)
        sys.stdout.flush()


def _terminate_tree(proc: subprocess.Popen[str] | None, name: str) -> None:
    if proc is None or proc.poll() is not None:
        return
    print(f"\nStopping {name} (pid={proc.pid})...", flush=True)
    try:
        proc.terminate()
    except OSError:
        pass
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except OSError:
            pass
        proc.wait(timeout=3)


def main() -> int:
    if not DASHBOARD.is_dir():
        print(f"dashboard/ not found at {DASHBOARD}", file=sys.stderr)
        return 1

    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        print("npm not found on PATH", file=sys.stderr)
        return 1

    api_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "main_api:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8765",
    ]
    ui_cmd = [npm, "run", "dev", "--", "--port", "5173"]

    api_proc = subprocess.Popen(
        api_cmd,
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    ui_proc = subprocess.Popen(
        ui_cmd,
        cwd=str(DASHBOARD),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    t_api = threading.Thread(target=_pump_stdout, args=(api_proc, API_PREFIX), daemon=True)
    t_ui = threading.Thread(target=_pump_stdout, args=(ui_proc, UI_PREFIX), daemon=True)
    t_api.start()
    t_ui.start()

    print(
        "Started:\n"
        f"  {API_PREFIX.strip()} http://127.0.0.1:8765  ({' '.join(api_cmd)})\n"
        f"  {UI_PREFIX.strip()} http://127.0.0.1:5173/ ({' '.join(ui_cmd)})\n"
        "Ctrl+C to stop both.\n",
        flush=True,
    )

    exit_code = 0
    try:
        while True:
            api_done = api_proc.poll() is not None
            ui_done = ui_proc.poll() is not None
            if api_done:
                rc = api_proc.returncode if api_proc.returncode is not None else 0
                print(f"\n{API_PREFIX.strip()} exited with code {rc}", flush=True)
                exit_code = rc
                break
            if ui_done:
                rc = ui_proc.returncode if ui_proc.returncode is not None else 0
                print(f"\n{UI_PREFIX.strip()} exited with code {rc}", flush=True)
                exit_code = rc
                break
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\nCtrl+C received — shutting down...", flush=True)
    finally:
        _terminate_tree(ui_proc, "dashboard (vite)")
        _terminate_tree(api_proc, "FastAPI (uvicorn)")
        # allow pump threads to drain
        time.sleep(0.2)

    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
