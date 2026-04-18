"""Proactive scheduler coroutines (invoked from APScheduler via main asyncio loop)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from zoneinfo import ZoneInfo

from jarvis.scheduler.deps import get_scheduler_deps
from jarvis.tools.calendar_tool import list_calendar_events_between

logger = logging.getLogger(__name__)

SESSION_SUMMARY_TURNS_KEY = "last_session_summarize_turn"


def _downloads_dir() -> Path:
    return Path(os.environ.get("USERPROFILE", "")) / "Downloads"


async def calendar_check() -> None:
    """Remind via TTS if a calendar event starts within 10 minutes."""
    deps = get_scheduler_deps()
    settings = deps.settings
    profile = deps.profile
    tts = deps.tts

    tz_name = (await profile.get_fact("timezone")) or "UTC"
    try:
        tz = ZoneInfo(tz_name.strip() or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")

    now = datetime.now(tz)
    window_end = now + timedelta(minutes=10)
    time_min = now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    time_max = window_end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    try:
        events = await list_calendar_events_between(settings, time_min, time_max, max_results=20)
    except Exception:
        logger.exception("calendar_check: list events failed")
        return

    for ev in events:
        start_raw = ev.get("start") or ""
        eid = str(ev.get("id") or start_raw)
        dedupe = f"{eid}|{start_raw}"
        try:
            if await profile.calendar_reminder_was_sent(dedupe):
                continue
        except Exception:
            logger.exception("calendar_check: dedupe lookup failed")
            continue

        start_dt: datetime | None = None
        try:
            if "T" in start_raw:
                s = start_raw.replace("Z", "+00:00")
                start_dt = datetime.fromisoformat(s)
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
                start_dt = start_dt.astimezone(tz)
            else:
                start_dt = datetime.fromisoformat(start_raw).replace(tzinfo=tz)
        except Exception:
            logger.warning("calendar_check: could not parse start %r", start_raw)
            continue

        if not (now <= start_dt <= window_end):
            continue

        title = str(ev.get("summary") or "Event")
        when = start_dt.strftime("%H:%M")
        text = f"Reminder: {title} starts at {when}."
        try:
            await profile.calendar_reminder_mark(dedupe)
        except Exception:
            logger.exception("calendar_check: dedupe insert failed")
        try:
            await tts.speak(text)
        except Exception:
            logger.exception("calendar_check: TTS failed")


async def session_summarize() -> None:
    """If 5+ completed turns since last long-term session summary, run summarize_and_store."""
    deps = get_scheduler_deps()
    agent = deps.agent
    profile = deps.profile

    last_raw = await profile.scheduler_meta_get(SESSION_SUMMARY_TURNS_KEY)
    try:
        last_turn = int(last_raw) if last_raw is not None else 0
    except ValueError:
        last_turn = 0

    if agent.turn_count - last_turn < 5:
        return

    try:
        session = await agent.short_term.to_messages()
        await agent.long_term.summarize_and_store(session)
        await profile.scheduler_meta_set(SESSION_SUMMARY_TURNS_KEY, str(agent.turn_count))
        logger.info("session_summarize: stored summary at turn_count=%s", agent.turn_count)
    except Exception:
        logger.exception("session_summarize failed")


async def watchdog_downloads() -> None:
    """Notify about new or changed files in Downloads (tracked in SQLite)."""
    deps = get_scheduler_deps()
    profile = deps.profile
    tts = deps.tts
    root = _downloads_dir()
    if not root.is_dir():
        return

    try:
        paths: list[Path] = sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:200]
    except OSError:
        logger.exception("watchdog_downloads: cannot list %s", root)
        return

    new_items: list[tuple[str, str, float]] = []
    for path in paths:
        if not path.is_file():
            continue
        try:
            st = path.stat()
        except OSError:
            continue
        mtime = float(st.st_mtime)
        pstr = str(path.resolve())
        try:
            prev = await profile.download_notified_mtime(pstr)
        except Exception:
            logger.exception("watchdog_downloads: sqlite read failed")
            continue
        if prev is not None and prev >= mtime:
            continue
        new_items.append((pstr, path.name, mtime))

    if not new_items:
        return

    for pstr, _name, mtime in new_items:
        try:
            await profile.download_mark_notified(pstr, mtime)
        except Exception:
            logger.exception("watchdog_downloads: sqlite write failed for %s", pstr)

    names = [n for _, n, _ in new_items[:5]]
    if len(new_items) == 1:
        text = f"New download: {names[0]}."
    else:
        tail = f" and {len(new_items) - 3} more" if len(new_items) > 3 else ""
        shown = ", ".join(names[:3])
        text = f"You have {len(new_items)} new downloads: {shown}{tail}."

    try:
        await tts.speak(text)
    except Exception:
        logger.exception("watchdog_downloads: TTS failed")
