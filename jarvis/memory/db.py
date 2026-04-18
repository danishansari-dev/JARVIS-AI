"""Synchronous SQLite writers for sessions, ElevenLabs usage (``user_facts``), and structured briefings."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

YM_KEY = "elevenlabs_usage_ym"
CHARS_KEY = "elevenlabs_usage_chars"


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_writer_tables(conn: sqlite3.Connection) -> None:
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


def _upsert_fact(conn: sqlite3.Connection, key: str, value: str) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO user_facts(key, value, updated_at)
        VALUES(?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
        """,
        (key, value, ts),
    )


def log_session(db_path: Path, session_id: str, messages: list[Any], token_count: int) -> None:
    """Persist one completed agent exchange (see call site in ``agent.process``)."""
    try:
        payload = json.dumps(messages, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        logger.exception("log_session: could not serialize messages")
        payload = "[]"
    try:
        with _connect(db_path) as conn:
            _ensure_writer_tables(conn)
            conn.execute(
                """
                INSERT INTO sessions(id, messages_json, token_count)
                VALUES(?, ?, ?)
                """,
                (session_id, payload, int(token_count)),
            )
            conn.commit()
    except Exception:
        logger.exception("log_session failed")


def log_elevenlabs_usage(db_path: Path, chars_used: int) -> tuple[int, int]:
    """
    Increment ElevenLabs character usage for the current UTC calendar month in ``user_facts``.
    When the stored month key differs from the current YYYY-MM (new month), the counter resets.

    Returns ``(previous_total, new_total)`` for the active month. If ``chars_used`` <= 0, no write
    occurs and both values are the current stored total (0 when the month key does not match).
    """
    ym = datetime.now(timezone.utc).strftime("%Y-%m")
    try:
        with _connect(db_path) as conn:
            _ensure_writer_tables(conn)
            row_ym = conn.execute(
                "SELECT value FROM user_facts WHERE key = ?",
                (YM_KEY,),
            ).fetchone()
            row_ch = conn.execute(
                "SELECT value FROM user_facts WHERE key = ?",
                (CHARS_KEY,),
            ).fetchone()
            stored_ym = str(row_ym[0]) if row_ym and row_ym[0] is not None else ""
            try:
                prev = int(row_ch[0]) if row_ch and row_ch[0] is not None else 0
            except (TypeError, ValueError):
                prev = 0

            effective_prev = prev if stored_ym == ym else 0

            if chars_used <= 0:
                return effective_prev, effective_prev

            if stored_ym != ym:
                new_total = max(0, int(chars_used))
                baseline_prev = 0
            else:
                baseline_prev = prev
                new_total = prev + max(0, int(chars_used))

            _upsert_fact(conn, YM_KEY, ym)
            _upsert_fact(conn, CHARS_KEY, str(new_total))
            conn.commit()
            return baseline_prev, new_total
    except Exception:
        logger.exception("log_elevenlabs_usage failed")
        return 0, 0


def log_briefing(
    db_path: Path,
    date: str,
    weather: str,
    calendar_summary: str,
    bullets: list[str],
) -> None:
    """Store structured briefing fields for the dashboard (full spoken text may still live in ``daily_briefings``)."""
    try:
        bullets_json = json.dumps(list(bullets), ensure_ascii=False)
    except (TypeError, ValueError):
        bullets_json = "[]"
    try:
        with _connect(db_path) as conn:
            _ensure_writer_tables(conn)
            conn.execute(
                """
                INSERT INTO briefing_log(briefing_date, weather, calendar_summary, bullets_json)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(briefing_date) DO UPDATE SET
                    weather = excluded.weather,
                    calendar_summary = excluded.calendar_summary,
                    bullets_json = excluded.bullets_json,
                    created_at = CURRENT_TIMESTAMP
                """,
                (date, weather, calendar_summary, bullets_json),
            )
            conn.commit()
    except Exception:
        logger.exception("log_briefing failed")
