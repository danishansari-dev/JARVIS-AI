"""Filesystem tools: list, glob-move, name search, open with default app (Windows: os.startfile)."""

from __future__ import annotations

import glob as glob_module
import os
import shutil
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from jarvis.tools.registry import ToolRegistry


class ListDirectoryInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str = Field(description="Absolute or home-relative directory path to list")


class MoveFilesInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_glob: str = Field(
        description="Glob pattern for files to move (e.g. C:/Downloads/*.pdf or ~/Documents/*.txt)",
    )
    destination: str = Field(
        description="Target directory path, or full file path when moving a single file",
    )


class SearchFilesInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    query: str = Field(description="Substring to match against file names (case-insensitive)")
    directory: str = Field(description="Root directory to search recursively")


class OpenFileInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str = Field(description="File or folder to open with the OS default application")


def _list_directory(inp: ListDirectoryInput) -> str:
    root = Path(inp.path).expanduser().resolve()
    if not root.is_dir():
        return f"Error: not a directory: {root}"
    names = sorted(p.name for p in root.iterdir())
    if not names:
        return f"Directory is empty: {root}"
    return "\n".join(names)


def _move_files(inp: MoveFilesInput) -> str:
    matches = sorted(glob_module.glob(inp.source_glob, recursive=True))
    files = [Path(p).resolve() for p in matches if Path(p).is_file()]
    if not files:
        return "No files matched the glob pattern."
    dest = Path(inp.destination).expanduser().resolve()
    moved: list[str] = []
    errors: list[str] = []

    if len(files) > 1 and dest.suffix and not dest.is_dir():
        return (
            "Error: multiple files matched the glob but destination looks like a file path. "
            "Use a directory path as destination."
        )

    if len(files) == 1 and dest.suffix and not dest.is_dir():
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(files[0]), str(dest))
            moved.append(f"{files[0]} -> {dest}")
        except OSError as exc:
            errors.append(f"{files[0]}: {exc}")
    else:
        dest.mkdir(parents=True, exist_ok=True)
        for src_path in files:
            target = dest / src_path.name
            try:
                shutil.move(str(src_path), str(target))
                moved.append(f"{src_path} -> {target}")
            except OSError as exc:
                errors.append(f"{src_path}: {exc}")

    lines = [f"Moved {len(moved)} file(s)."]
    lines.extend(moved)
    if errors:
        lines.append("Errors:")
        lines.extend(errors)
    return "\n".join(lines)


def _search_files(inp: SearchFilesInput) -> str:
    root = Path(inp.directory).expanduser().resolve()
    if not root.is_dir():
        return f"Error: not a directory: {root}"
    q = inp.query.strip().lower()
    if not q:
        return "Error: empty query."
    hits: list[str] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if q in p.name.lower():
            hits.append(str(p))
            if len(hits) >= 200:
                break
    if not hits:
        return f"No files under {root} matched name containing {inp.query!r}."
    return f"Found {len(hits)} file(s) (max 200):\n" + "\n".join(hits)


def _open_file(inp: OpenFileInput) -> str:
    target = Path(inp.path).expanduser().resolve()
    if not target.exists():
        return f"Error: path does not exist: {target}"
    if os.name == "nt":
        os.startfile(str(target))  # noqa: S606 — intentional Windows default handler
        return f"Opened with default application: {target}"
    import subprocess
    import sys

    if sys.platform == "darwin":
        subprocess.run(
            ["open", str(target)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        subprocess.run(
            ["xdg-open", str(target)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return f"Opened: {target}"


def register_filesystem_tools(registry: ToolRegistry) -> None:
    registry.register(
        "list_directory",
        "List file and folder names in a directory (one name per line).",
        ListDirectoryInput,
        _list_directory,
    )
    registry.register(
        "move_files",
        "Move all files matching a glob pattern into a destination folder (or rename to a file path).",
        MoveFilesInput,
        _move_files,
    )
    registry.register(
        "search_files",
        "Recursively find files whose names contain a substring under a root directory.",
        SearchFilesInput,
        _search_files,
    )
    registry.register(
        "open_file",
        "Open a file or folder with the OS default handler (Windows: os.startfile).",
        OpenFileInput,
        _open_file,
    )
