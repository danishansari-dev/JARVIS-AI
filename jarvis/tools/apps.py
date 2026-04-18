"""App control tools: launch by friendly name, kill by name, list processes, clipboard."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

import psutil
import pyperclip
from pydantic import BaseModel, ConfigDict, Field

from jarvis.config import Settings
from jarvis.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

_DEFAULT_APP_ALIASES: dict[str, str] = {
    "notepad": "notepad",
    "calculator": "calc",
    "calc": "calc",
    "edge": "msedge",
    "browser": "msedge",
    "chrome": "chrome",
    "firefox": "firefox",
    "code": "code",
    "vscode": "code",
    "terminal": "wt",
    "windows terminal": "wt",
    "wt": "wt",
    "explorer": "explorer",
    "file explorer": "explorer",
    "spotify": "spotify",
    "slack": "slack",
    "discord": "discord",
    "outlook": "outlook",
    "teams": "ms-teams",
    "powershell": "powershell",
    "cmd": "cmd",
    "command prompt": "cmd",
}


def _merged_aliases(settings: Settings) -> dict[str, str]:
    merged = dict(_DEFAULT_APP_ALIASES)
    raw = (settings.app_launch_aliases_json or "").strip()
    if raw:
        try:
            extra = json.loads(raw)
            if isinstance(extra, dict):
                for k, v in extra.items():
                    if isinstance(k, str) and isinstance(v, str):
                        merged[k.strip().lower()] = v.strip()
        except json.JSONDecodeError:
            logger.warning("app_launch_aliases_json is not valid JSON; using defaults only")
    return merged


class LaunchAppInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    app_name: str = Field(
        description="Friendly app name (e.g. notepad, calculator, edge) or raw executable name",
    )


class KillAppInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    app_name: str = Field(
        description="Substring matched case-insensitively against running process names (e.g. notepad)",
    )


class GetRunningAppsInput(BaseModel):
    model_config = ConfigDict(extra="ignore")


class SetClipboardInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str = Field(description="Plain text to place on the system clipboard")


def _launch_app(settings: Settings, inp: LaunchAppInput) -> str:
    key = inp.app_name.strip().lower()
    aliases = _merged_aliases(settings)
    candidate = aliases.get(key, inp.app_name.strip())
    exe_path = shutil.which(candidate)
    if exe_path is None:
        p = Path(candidate)
        if p.is_file():
            exe_path = str(p.resolve())
        else:
            return (
                f"Could not resolve executable for {inp.app_name!r}. "
                f"Tried {candidate!r}. Configure APP_LAUNCH_ALIASES_JSON or use a full path."
            )
    import subprocess

    subprocess.Popen(
        [exe_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    return f"Launched {inp.app_name!r} using {exe_path}"


def _kill_app(inp: KillAppInput) -> str:
    needle = inp.app_name.strip().lower()
    if not needle:
        return "Error: empty app_name."
    killed: list[int] = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if needle in name:
                psutil.Process(proc.info["pid"]).terminate()
                killed.append(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if not killed:
        return f"No processes matched {inp.app_name!r}."
    return f"Sent terminate to {len(killed)} process(es): {killed}"


def _get_running_apps(_inp: GetRunningAppsInput) -> str:
    names: list[str] = []
    for proc in psutil.process_iter(["name"]):
        try:
            n = proc.info.get("name")
            if n:
                names.append(str(n))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    unique = sorted(set(names))
    top = unique[:20]
    return "Running process names (unique, first 20 alphabetically):\n" + "\n".join(top)


def _set_clipboard(inp: SetClipboardInput) -> str:
    pyperclip.copy(inp.text)
    n = len(inp.text)
    return f"Clipboard updated ({n} characters)."


def register_apps_tools(registry: ToolRegistry, settings: Settings) -> None:
    registry.register(
        "launch_app",
        "Start an application by friendly name (mapped in config) or executable name on PATH.",
        LaunchAppInput,
        lambda m: _launch_app(settings, m),
    )
    registry.register(
        "kill_app",
        "Terminate running processes whose executable name contains the given substring.",
        KillAppInput,
        _kill_app,
    )
    registry.register(
        "get_running_apps",
        "List up to 20 unique running process names (alphabetically) for quick orientation.",
        GetRunningAppsInput,
        _get_running_apps,
    )
    registry.register(
        "set_clipboard",
        "Copy plain text to the system clipboard.",
        SetClipboardInput,
        _set_clipboard,
    )
