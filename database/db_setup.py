"""Initialize ``data/jarvis.db`` and provide connection helpers."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = _REPO_ROOT / "data"
DB_PATH = DATA_DIR / "jarvis.db"


def get_db() -> sqlite3.Connection:
    """Open SQLite at ``data/jarvis.db`` with row factory and foreign keys enabled."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create all tables if they do not exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                preview TEXT NOT NULL,
                message_count INTEGER NOT NULL,
                token_count INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS session_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                CHECK(role IN ('user', 'jarvis'))
            );

            CREATE TABLE IF NOT EXISTS user_facts (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS briefings (
                date TEXT PRIMARY KEY,
                weather TEXT NOT NULL,
                calendar_summary TEXT NOT NULL,
                bullets TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS elevenlabs_usage (
                month TEXT PRIMARY KEY,
                chars_used INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_session_messages_session_id
                ON session_messages(session_id);
            """
        )
        conn.commit()


def insert_sample_data() -> None:
    """Insert demo sessions, messages, and user facts when tables are empty (dev UX)."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        n_sessions = conn.execute("SELECT COUNT(*) AS c FROM sessions").fetchone()["c"]
        n_facts = conn.execute("SELECT COUNT(*) AS c FROM user_facts").fetchone()["c"]
        if int(n_sessions) > 0 or int(n_facts) > 0:
            return

        def _preview(text: str, max_len: int = 60) -> str:
            t = text.strip()
            return t if len(t) <= max_len else t[: max_len - 1] + "…"

        sessions_rows = [
            (
                "s_0a33",
                now,
                _preview("What is on my calendar tomorrow?"),
                4,
                1820,
            ),
            (
                "s_1b44",
                now,
                _preview("Draft a short email to Alex about the release slip."),
                2,
                2640,
            ),
            (
                "s_2c55",
                now,
                _preview("Remember: prefer concise answers unless I ask for detail."),
                2,
                890,
            ),
        ]
        conn.executemany(
            """
            INSERT INTO sessions (id, timestamp, preview, message_count, token_count)
            VALUES (?, ?, ?, ?, ?)
            """,
            sessions_rows,
        )

        messages: list[tuple[str, str, str, str]] = [
            ("s_0a33", "user", "What is on my calendar tomorrow?", now),
            (
                "s_0a33",
                "jarvis",
                "You have stand-up at 09:30 and a dentist block at 15:00.",
                now,
            ),
            ("s_0a33", "user", "Move the dentist to Thursday if possible.", now),
            (
                "s_0a33",
                "jarvis",
                "I cannot change calendar entries without your Google connection.",
                now,
            ),
            (
                "s_1b44",
                "user",
                "Draft a short email to Alex about the release slip.",
                now,
            ),
            (
                "s_1b44",
                "jarvis",
                "Subject: Release update\n\nHi Alex — we need to slip by one week…",
                now,
            ),
            (
                "s_2c55",
                "user",
                "Remember: prefer concise answers unless I ask for detail.",
                now,
            ),
            ("s_2c55", "jarvis", "Understood. I will keep replies tight by default.", now),
        ]
        conn.executemany(
            """
            INSERT INTO session_messages (session_id, role, content, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            messages,
        )

        facts = [
            ("memory.work_focus", "Deep work mornings; avoid scheduling before 11:00.", now),
            ("memory.preferred_tone", "Direct, minimal filler, British spelling ok.", now),
            ("memory.home_city", "Amsterdam", now),
            ("memory.default_model_hint", "Use fast model for one-line confirmations.", now),
            ("memory.last_topic", "Calendar + email triage workflow.", now),
        ]
        conn.executemany(
            """
            INSERT INTO user_facts (key, value, updated_at)
            VALUES (?, ?, ?)
            """,
            facts,
        )

        bullets = json.dumps(
            [
                "Local traffic lighter than usual on ring routes.",
                "Tech: major cloud vendor reports regional latency.",
                "Science: sample return mission milestone announced.",
            ],
            ensure_ascii=False,
        )
        conn.execute(
            """
            INSERT INTO briefings (date, weather, calendar_summary, bullets, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "12 °C, light breeze, mostly dry.",
                "Stand-up 09:30; focus block 10:00–12:00.",
                bullets,
                now,
            ),
        )

        conn.execute(
            """
            INSERT INTO elevenlabs_usage (month, chars_used)
            VALUES (?, ?)
            ON CONFLICT(month) DO NOTHING
            """,
            (datetime.now(timezone.utc).strftime("%Y-%m"), 4200),
        )

        conn.commit()


if __name__ == "__main__":
    init_db()
    insert_sample_data()
    print("DB ready")
