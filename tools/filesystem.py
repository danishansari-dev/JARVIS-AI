from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess

from pydantic import BaseModel

from tools.registry import ToolRegistry


class ListDirInput(BaseModel):
    path: str = "."


class MoveFilesInput(BaseModel):
    source_glob: str
    destination: str


class SearchFilesInput(BaseModel):
    query: str
    directory: str = "."


class OpenFileInput(BaseModel):
    path: str


WINDOWS_FOLDER_MAP = {
    "downloads": pathlib.Path.home() / "Downloads",
    "desktop": pathlib.Path.home() / "Desktop", 
    "documents": pathlib.Path.home() / "Documents",
    "pictures": pathlib.Path.home() / "Pictures",
    "music": pathlib.Path.home() / "Music",
    "videos": pathlib.Path.home() / "Videos",
    "home": pathlib.Path.home(),
}

def _normalize_path(path: str) -> pathlib.Path:
    p_lower = path.lower().strip().strip("/\\")
    
    # Direct folder name match ("downloads", "desktop", etc.)
    if p_lower in WINDOWS_FOLDER_MAP:
        return WINDOWS_FOLDER_MAP[p_lower]
    
    # Unix-style home path: /Users/Danish/Downloads → C:\Users\Danish\Downloads
    if path.startswith("/Users/") or path.startswith("~/"):
        # Strip the unix prefix and get the tail
        tail = re.sub(r'^/Users/[^/]+/', '', path)
        tail = tail.lstrip("~/")
        if not tail:
            return pathlib.Path.home()
        return pathlib.Path.home() / tail
    
    # ~ expansion
    if path.startswith("~"):
        return pathlib.Path(path).expanduser()
    
    # Already a valid Windows path
    p = pathlib.Path(path)
    if p.exists():
        return p
    
    # Last resort: check if it's a folder name that matches known folders
    for key, val in WINDOWS_FOLDER_MAP.items():
        if key in p_lower:
            return val
    
    return p


def _list_directory(data: ListDirInput) -> str:
    target = _normalize_path(data.path)
    if not target.exists():
        return f"Path not found: {target}"
    entries = sorted(target.iterdir(), key=lambda p: p.name.lower())
    lines: list[str] = []
    for entry in entries:
        size = entry.stat().st_size if entry.is_file() else 0
        kind = "DIR" if entry.is_dir() else "FILE"
        lines.append(f"{kind:4} {entry.name} ({size} bytes)")
    return "\n".join(lines) if lines else f"Empty directory: {target}"


def _move_files(data: MoveFilesInput) -> str:
    destination = _normalize_path(data.destination).resolve()
    home = pathlib.Path.home().resolve()

    if home not in destination.parents and destination != home:
        raise ValueError("Destination must be under user home directory")

    destination.mkdir(parents=True, exist_ok=True)

    moved = 0
    for source in pathlib.Path(".").glob(data.source_glob):
        if source.is_file():
            shutil.move(str(source), str(destination / source.name))
            moved += 1
    return f"Moved {moved} files to {data.destination}"


def _search_files(data: SearchFilesInput) -> str:
    base = _normalize_path(data.directory)
    if not base.exists():
        return f"Directory not found: {base}"

    query = data.query.lower()
    matches: list[str] = []
    for root, _, files in os.walk(base):
        for file_name in files:
            if query in file_name.lower():
                matches.append(str(pathlib.Path(root) / file_name))
                if len(matches) >= 20:
                    return "\n".join(matches)
    return "\n".join(matches) if matches else "No matches found"


def _open_file(data: OpenFileInput) -> str:
    target = _normalize_path(data.path)
    if not target.exists():
        return f"File not found: {target}"
    os.startfile(str(target))  # type: ignore[attr-defined]
    return f"Opened {target.name}"


def register_filesystem_tools(registry: ToolRegistry) -> None:
    registry.register(
        name="list_directory",
        description="List files and folders in a directory with sizes.",
        input_schema=ListDirInput,
        handler=_list_directory,
    )
    registry.register(
        name="move_files",
        description="Move files matching a glob into a destination folder.",
        input_schema=MoveFilesInput,
        handler=_move_files,
    )
    registry.register(
        name="search_files",
        description="Search files by filename query within a directory.",
        input_schema=SearchFilesInput,
        handler=_search_files,
    )
    registry.register(
        name="open_file",
        description="Open a file with the system default application.",
        input_schema=OpenFileInput,
        handler=_open_file,
    )
