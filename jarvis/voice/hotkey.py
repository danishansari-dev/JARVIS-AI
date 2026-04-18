"""Global hotkey listener using pynput; forwards events to an asyncio queue."""

from __future__ import annotations

import asyncio
import logging
import threading
import time

from pynput import keyboard

logger = logging.getLogger(__name__)


class HotkeyListener:
    """Runs pynput in a background thread and schedules asyncio callbacks safely."""

    def __init__(self, combo: str = "<ctrl>+<alt>+j", loop: asyncio.AbstractEventLoop | None = None) -> None:
        self._combo = combo
        self._loop = loop
        self._events: asyncio.Queue[float] = asyncio.Queue()
        self._hook: keyboard.GlobalHotKeys | None = None
        self._thread: threading.Thread | None = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def next_activation(self) -> float:
        """Return ``time.perf_counter()`` captured on the pynput thread at key-down."""
        return await self._events.get()

    def _on_hotkey(self) -> None:
        loop = self._loop or asyncio.get_event_loop_policy().get_event_loop()
        try:
            loop.call_soon_threadsafe(self._events.put_nowait, time.perf_counter())
        except RuntimeError:
            logger.exception("Failed to schedule hotkey event")

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        def _run() -> None:
            self._hook = keyboard.GlobalHotKeys({self._combo: self._on_hotkey})
            assert self._hook is not None
            self._hook.start()
            self._hook.join()

        self._thread = threading.Thread(target=_run, name="jarvis-hotkeys", daemon=True)
        self._thread.start()
        logger.info("Hotkey listener started (%s)", self._combo)

    def stop(self) -> None:
        if self._hook is not None:
            try:
                self._hook.stop()
            except Exception:
                logger.debug("Hotkey stop error", exc_info=True)
            self._hook = None
