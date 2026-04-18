"""Runtime dependencies for proactive scheduler jobs (set from ``main`` before scheduler starts)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from jarvis.agent import JarvisAgent
from jarvis.config import Settings
from jarvis.memory.profile import ProfileStore
from jarvis.voice.tts import TextToSpeech

_deps: "SchedulerDeps | None" = None


@dataclass
class SchedulerDeps:
    settings: Settings
    profile: ProfileStore
    agent: JarvisAgent
    tts: TextToSpeech
    loop: asyncio.AbstractEventLoop


def set_scheduler_deps(deps: SchedulerDeps) -> None:
    global _deps
    _deps = deps


def get_scheduler_deps() -> SchedulerDeps:
    if _deps is None:
        raise RuntimeError("Scheduler dependencies not configured; call set_scheduler_deps() from main")
    return _deps


def clear_scheduler_deps() -> None:
    global _deps
    _deps = None
