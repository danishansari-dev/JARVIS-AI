"""SQLite user profile at ``data_dir/jarvis.db`` with interactive bootstrap on first run."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ProfileStore:
    """Key/value user facts with optional first-run prompts for name, timezone, and TTS speed."""

    def __init__(self, db_path: Path) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._executor = asyncio.ThreadPoolExecutor(max_workers=1, thread_name_prefix="jarvis-profile")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    async def init(self) -> None:
        def _init() -> None:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_facts (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS daily_briefings (
                        briefing_date TEXT PRIMARY KEY,
                        content TEXT NOT NULL,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scheduler_meta (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS downloads_notified (
                        path TEXT PRIMARY KEY,
                        mtime REAL NOT NULL,
                        notified_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS calendar_reminders_sent (
                        dedupe_key TEXT PRIMARY KEY,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sessions (
                        id TEXT PRIMARY KEY,
                        messages_json TEXT NOT NULL,
                        token_count INTEGER NOT NULL,
                        ended_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS briefing_log (
                        briefing_date TEXT PRIMARY KEY,
                        weather TEXT NOT NULL,
                        calendar_summary TEXT NOT NULL,
                        bullets_json TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.commit()

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, _init)

    async def prepopulate_if_needed(self) -> None:
        """On first run, collect name, timezone, and preferred TTS speed (TTY ``input`` or env defaults)."""
        existing = await self.get_fact("user_name")
        if existing and str(existing).strip():
            return

        name = ""
        tz = ""
        speed = "1.0"

        if sys.stdin.isatty() and sys.stdout.isatty():
            try:
                name = input("Your name (for JARVIS): ").strip()
                tz = input("Your timezone (e.g. Europe/Amsterdam): ").strip()
                speed = input("Preferred TTS speed (e.g. 1.0): ").strip() or "1.0"
            except EOFError:
                logger.warning("Profile prepopulate interrupted; using defaults")
        else:
            logger.info(
                "Non-interactive session: set user_name/timezone/tts_speed later via set_fact "
                "or rerun in a terminal to answer prompts."
            )

        if not name:
            name = "User"
        if not tz:
            tz = "UTC"

        await self.set_fact("user_name", name)
        await self.set_fact("timezone", tz)
        await self.set_fact("tts_speed", speed)
        city = ""
        if sys.stdin.isatty() and sys.stdout.isatty():
            try:
                city = input("City for weather briefings (e.g. London, press Enter to skip): ").strip()
            except EOFError:
                pass
        if city:
            await self.set_fact("user_city", city)
        logger.info("Profile bootstrap stored for user_name=%s timezone=%s", name, tz)

    async def get_fact(self, key: str) -> str | None:
        def _run() -> str | None:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT value FROM user_facts WHERE key = ?",
                    (key,),
                ).fetchone()
                return str(row["value"]) if row else None

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, _run)

    async def set_fact(self, key: str, value: str) -> None:
        def _run() -> None:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO user_facts(key, value, updated_at)
                    VALUES(?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (key, value, datetime.now(timezone.utc).isoformat()),
                )
                conn.commit()

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, _run)

    async def list_facts(self) -> list[dict[str, Any]]:
        def _run() -> list[dict[str, Any]]:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT key, value, updated_at FROM user_facts ORDER BY key ASC"
                ).fetchall()
                return [dict(r) for r in rows]

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, _run)

    async def scheduler_meta_get(self, key: str) -> str | None:
        def _run() -> str | None:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT value FROM scheduler_meta WHERE key = ?",
                    (key,),
                ).fetchone()
                return str(row[0]) if row else None

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, _run)

    async def scheduler_meta_set(self, key: str, value: str) -> None:
        def _run() -> None:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO scheduler_meta(key, value) VALUES(?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (key, value),
                )
                conn.commit()

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, _run)

    async def save_daily_briefing(self, date_iso: str, content: str) -> None:
        def _run() -> None:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO daily_briefings(briefing_date, content)
                    VALUES(?, ?)
                    ON CONFLICT(briefing_date) DO UPDATE SET
                        content = excluded.content,
                        created_at = CURRENT_TIMESTAMP
                    """,
                    (date_iso, content),
                )
                conn.commit()

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, _run)

    async def get_daily_briefing(self, date_iso: str) -> str | None:
        def _run() -> str | None:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT content FROM daily_briefings WHERE briefing_date = ?",
                    (date_iso,),
                ).fetchone()
                return str(row[0]) if row else None

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, _run)

    async def calendar_reminder_was_sent(self, dedupe_key: str) -> bool:
        def _run() -> bool:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT 1 FROM calendar_reminders_sent WHERE dedupe_key = ?",
                    (dedupe_key,),
                ).fetchone()
                return row is not None

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, _run)

    async def calendar_reminder_mark(self, dedupe_key: str) -> None:
        def _run() -> None:
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO calendar_reminders_sent(dedupe_key) VALUES(?)",
                    (dedupe_key,),
                )
                conn.commit()

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, _run)

    async def download_notified_mtime(self, path: str) -> float | None:
        def _run() -> float | None:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT mtime FROM downloads_notified WHERE path = ?",
                    (path,),
                ).fetchone()
                return float(row[0]) if row else None

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, _run)

    async def download_mark_notified(self, path: str, mtime: float) -> None:
        def _run() -> None:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO downloads_notified(path, mtime) VALUES(?, ?)
                    ON CONFLICT(path) DO UPDATE SET
                        mtime = excluded.mtime,
                        notified_at = CURRENT_TIMESTAMP
                    """,
                    (path, mtime),
                )
                conn.commit()

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, _run)

    async def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


def load_profile_facts_text_sync(db_path: Path) -> str:
    """Sync read of ``user_facts`` for system prompt assembly during agent ``__init__``."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_facts (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
        rows = conn.execute("SELECT key, value FROM user_facts ORDER BY key ASC").fetchall()
    finally:
        conn.close()
    lines: list[str] = []
    for key, value in rows:
        if str(key).startswith("_"):
            continue
        lines.append(f"- {key}: {value}")
    return "\n".join(lines) if lines else "(no profile facts yet)"
