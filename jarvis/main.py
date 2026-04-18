"""Entry point: configure logging, start scheduler, tray daemon, and background services."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
import threading

from jarvis.agent import JarvisAgent
from jarvis.config import load_settings
from jarvis.memory.profile import ProfileStore
from jarvis.scheduler.deps import SchedulerDeps, clear_scheduler_deps, set_scheduler_deps
from jarvis.scheduler.triggers import build_scheduler
from jarvis.ui.tray import build_tray_icon
from jarvis.voice.hotkey import HotkeyListener
from jarvis.voice.stt import SpeechToText
from jarvis.voice.tts import TextToSpeech

logger = logging.getLogger(__name__)


def _configure_logging(level: str) -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def _hotkey_loop(
    agent: JarvisAgent,
    hotkey: HotkeyListener,
    stt: SpeechToText,
    tts: TextToSpeech,
    stop: asyncio.Event,
) -> None:
    while not stop.is_set():
        try:
            t_hotkey = await asyncio.wait_for(hotkey.next_activation(), timeout=0.5)
        except asyncio.TimeoutError:
            continue
        try:
            utterance = await stt.transcribe_after_hotkey(t_hotkey)
            if not utterance.strip():
                await tts.speak("Got it.")
                continue
            result = await agent.run_turn(utterance)
            await tts.speak(result.text)
        except Exception:
            logger.exception("Voice hotkey pipeline failed")


async def amain() -> None:
    settings = load_settings()
    _configure_logging(settings.log_level)
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    profile = ProfileStore(settings.profile_db_path)
    await profile.init()
    await profile.prepopulate_if_needed()

    agent = JarvisAgent(settings, profile)
    stt = SpeechToText(settings)
    tts = TextToSpeech(settings)
    await tts.start()

    loop = asyncio.get_running_loop()
    morning_tz = (await profile.get_fact("timezone")) or "UTC"
    stop = asyncio.Event()

    def request_stop() -> None:
        stop.set()

    tray_icon = build_tray_icon(
        loop,
        on_quit=request_stop,
        on_status=lambda: "JARVIS is running",
    )

    tray_thread = threading.Thread(target=tray_icon.run, name="jarvis-tray", daemon=True)
    tray_thread.start()

    hotkey = HotkeyListener(loop=loop)
    hotkey.start()

    scheduler = None
    deps_armed = False
    try:
        set_scheduler_deps(
            SchedulerDeps(
                settings=settings,
                profile=profile,
                agent=agent,
                tts=tts,
                loop=loop,
            )
        )
        deps_armed = True
        scheduler = build_scheduler(morning_tz)
        scheduler.start()
        logger.info("Background scheduler started (morning_tz=%s)", morning_tz)

        hotkey_task: asyncio.Task[None] | None = None
        try:
            hotkey_task = asyncio.create_task(
                _hotkey_loop(agent, hotkey, stt, tts, stop),
                name="hotkey-loop",
            )
            await stop.wait()
        finally:
            if hotkey_task is not None:
                hotkey_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await hotkey_task
            if scheduler is not None:
                scheduler.shutdown(wait=True)
            hotkey.stop()
            tray_icon.stop()
            await agent.long_term.shutdown()
            await profile.shutdown()
            await tts.stop()
            await stt.shutdown()
    finally:
        if deps_armed:
            clear_scheduler_deps()


def main() -> None:
    if sys.version_info < (3, 11):
        raise SystemExit("JARVIS requires Python 3.11+")
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        logger.info("Interrupted")


if __name__ == "__main__":
    main()
