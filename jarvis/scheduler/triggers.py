"""APScheduler BackgroundScheduler: proactive jobs on the main asyncio loop."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from concurrent.futures import TimeoutError as FuturesTimeoutError

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from zoneinfo import ZoneInfo

from jarvis.scheduler.briefing import morning_briefing
from jarvis.scheduler.deps import get_scheduler_deps
from jarvis.scheduler.jobs import calendar_check, session_summarize, watchdog_downloads

logger = logging.getLogger(__name__)


def _submit_coro(coro: Awaitable[object], job_id: str, timeout_s: float = 600.0) -> None:
    deps = get_scheduler_deps()
    fut = asyncio.run_coroutine_threadsafe(coro, deps.loop)
    try:
        fut.result(timeout=timeout_s)
    except FuturesTimeoutError:
        logger.error("Scheduler job %s timed out after %ss", job_id, timeout_s)
    except Exception:
        logger.exception("Scheduler job %s failed", job_id)


def _wrap(job_id: str, factory: Callable[[], Awaitable[object]], timeout_s: float = 600.0) -> Callable[[], None]:
    def _run() -> None:
        try:
            coro = factory()
        except Exception:
            logger.exception("Scheduler job %s: coroutine factory crashed", job_id)
            return
        try:
            _submit_coro(coro, job_id, timeout_s=timeout_s)
        except Exception:
            logger.exception("Scheduler job %s: scheduling failed", job_id)

    return _run


def build_scheduler(morning_timezone: str) -> BackgroundScheduler:
    """Background thread scheduler; coroutines run on the asyncio loop from ``main``."""
    tz_name = (morning_timezone or "UTC").strip() or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        logger.warning("Invalid morning timezone %r; using UTC", tz_name)
        tz = ZoneInfo("UTC")

    scheduler = BackgroundScheduler()

    scheduler.add_job(
        _wrap("morning_briefing", morning_briefing, timeout_s=900.0),
        CronTrigger(hour=8, minute=0, timezone=tz),
        id="morning_briefing",
        replace_existing=True,
    )
    scheduler.add_job(
        _wrap("calendar_check", calendar_check, timeout_s=120.0),
        IntervalTrigger(minutes=15),
        id="calendar_check",
        replace_existing=True,
    )
    scheduler.add_job(
        _wrap("session_summarize", session_summarize, timeout_s=600.0),
        IntervalTrigger(minutes=30),
        id="session_summarize",
        replace_existing=True,
    )
    scheduler.add_job(
        _wrap("watchdog_downloads", watchdog_downloads, timeout_s=120.0),
        IntervalTrigger(minutes=5),
        id="watchdog_downloads",
        replace_existing=True,
    )
    return scheduler
