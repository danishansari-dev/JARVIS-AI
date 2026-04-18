"""Short-term conversation buffer with Haiku compaction of the oldest 10 turns."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

logger = logging.getLogger(__name__)

MAX_TURNS = 20
TURNS_TO_SUMMARIZE = 10
MESSAGES_PER_TURN = 2
MAX_MESSAGES = MAX_TURNS * MESSAGES_PER_TURN
COMPACT_MESSAGE_BATCH = TURNS_TO_SUMMARIZE * MESSAGES_PER_TURN


class ConversationBuffer:
    """Rolling window of messages; compacts oldest 10 turns (20 msgs) when count exceeds 40."""

    def __init__(
        self,
        summarize_fn: Callable[[list[dict[str, Any]]], Awaitable[str]] | None = None,
    ) -> None:
        self._messages: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._summarize_fn = summarize_fn

    async def _compact_if_needed_unlocked(self) -> None:
        while len(self._messages) > MAX_MESSAGES:
            batch = self._messages[:COMPACT_MESSAGE_BATCH]
            self._messages = self._messages[COMPACT_MESSAGE_BATCH:]
            if self._summarize_fn is not None:
                try:
                    summary_text = await self._summarize_fn(batch)
                except Exception:
                    logger.exception("Haiku compaction failed; folding raw turns")
                    summary_text = "\n".join(
                        f"{m.get('role', '?')}: {m.get('content', '')}" for m in batch
                    )
            else:
                summary_text = "\n".join(
                    f"{m.get('role', '?')}: {m.get('content', '')}" for m in batch
                )
            summary_msg = {
                "role": "user",
                "content": f"[Earlier conversation summary]\n{summary_text.strip()}",
            }
            self._messages.insert(0, summary_msg)

    async def add_turn(self, role: str, content: str) -> None:
        if role not in ("user", "assistant", "system"):
            raise ValueError("role must be user, assistant, or system")
        async with self._lock:
            self._messages.append({"role": role, "content": content})
            await self._compact_if_needed_unlocked()

    async def to_messages(self) -> list[dict[str, str]]:
        """Return a copy suitable for Anthropic ``messages`` (role/content only)."""
        async with self._lock:
            out: list[dict[str, str]] = []
            for m in self._messages:
                out.append(
                    {
                        "role": cast(str, m["role"]),
                        "content": cast(str, m["content"]),
                    }
                )
            return out

    async def clear(self) -> None:
        async with self._lock:
            self._messages.clear()
