"""JARVIS agent: streaming Claude orchestration with tools, memory, and profile-aware system prompt."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, cast

from anthropic import AsyncAnthropic
from anthropic.types import MessageParam, ToolParam, ToolResultBlockParam

from jarvis.config import Settings
from jarvis.memory.db import log_session
from jarvis.memory.long_term import LongTermMemory
from jarvis.memory.profile import ProfileStore, load_profile_facts_text_sync
from jarvis.memory.short_term import ConversationBuffer
from jarvis.tools.apps import register_apps_tools
from jarvis.tools.filesystem import register_filesystem_tools
from jarvis.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 12
SMART_MODEL_KEYWORDS = frozenset({"explain", "analyze", "compare", "write", "summarize"})

TONE_BLOCK = """You are JARVIS. Be concise. Acknowledge completed actions in 5 words or less.
Never say 'Of course', 'Certainly', 'Happy to', or 'Great question'.
For simple tasks, respond with only the action taken. Elaborate only when asked."""


def _message_usage_tokens(msg: Any) -> int:
    """Best-effort token total from an Anthropic ``Message`` (streaming final message)."""
    u = getattr(msg, "usage", None)
    if u is None:
        return 0
    total = 0
    for name in ("input_tokens", "output_tokens"):
        v = getattr(u, name, None)
        if v is not None:
            try:
                total += int(v)
            except (TypeError, ValueError):
                pass
    return total


@dataclass
class AgentTurnResult:
    text: str
    action: dict[str, Any] | None


class JarvisAgent:
    """Orchestrates memory retrieval, Claude streaming (with tools), and conversation persistence."""

    def __init__(
        self,
        settings: Settings,
        profile: ProfileStore,
        long_term: LongTermMemory | None = None,
    ) -> None:
        self._settings = settings
        self._profile = profile
        self._long_term = long_term or LongTermMemory(settings.chroma_dir, settings=settings)
        self._registry = ToolRegistry()
        register_filesystem_tools(self._registry)
        register_apps_tools(self._registry, settings)

        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.short_term = ConversationBuffer(summarize_fn=self.summarize_turns)

        self._profile_facts_text = load_profile_facts_text_sync(settings.profile_db_path)
        self._turn_count = 0
        self._last_tool_action: dict[str, Any] | None = None

    @property
    def long_term(self) -> LongTermMemory:
        return self._long_term

    @property
    def turn_count(self) -> int:
        """Completed user/assistant cycles via ``process`` / ``run_turn`` (for scheduler hooks)."""
        return self._turn_count

    def _select_model(self, user_input: str) -> str:
        """Haiku (fast) by default; Sonnet when complex keywords and long input."""
        if len(user_input) > 80:
            lower = user_input.lower()
            if any(kw in lower for kw in SMART_MODEL_KEYWORDS):
                return self._settings.claude_model_smart
        return self._settings.claude_model_fast

    def _build_system_prompt(self, memory_chunks: list[str]) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
        tools = ", ".join(self._registry.registered_tool_names())
        mem = "\n".join(f"- {c}" for c in memory_chunks) if memory_chunks else "(none)"
        return "\n\n".join(
            [
                "IDENTITY\nYou are JARVIS, a capable single-user desktop assistant running locally on Windows.",
                f"TONE\n{TONE_BLOCK}",
                f"RETRIEVED_MEMORY\n{mem}",
                f"USER_PROFILE\n{self._profile_facts_text}",
                f"AVAILABLE_TOOLS\n{tools}",
                f"CURRENT_DATETIME\n{now}",
            ]
        )

    def _anthropic_tools(self) -> list[ToolParam]:
        return cast(list[ToolParam], self._registry.to_claude_tools())

    async def summarize_turns(self, batch: list[dict[str, Any]]) -> str:
        body = "\n".join(f"{m.get('role', '?')}: {m.get('content', '')}" for m in batch)
        msg = await self._client.messages.create(
            model=self._settings.claude_model_fast,
            max_tokens=512,
            system=(
                "Summarize the oldest portion of the conversation in at most 6 short bullet points. "
                "Preserve names, dates, and user intent."
            ),
            messages=[{"role": "user", "content": body}],
        )
        parts: list[str] = []
        for block in msg.content:
            if block.type == "text":
                parts.append(block.text)
        return "\n".join(parts).strip()

    async def process(
        self,
        user_input: str,
        *,
        force_smart_model: bool = False,
    ) -> AsyncGenerator[str, None]:
        """Stream assistant text chunks; run tools between streaming rounds when required."""
        self._last_tool_action = None
        stripped = user_input.strip()
        memory_chunks = await self._long_term.query(stripped, k=5)
        system_prompt = self._build_system_prompt(memory_chunks)
        hist = await self.short_term.to_messages()
        messages: list[MessageParam] = [*hist, {"role": "user", "content": user_input}]
        model = (
            self._settings.claude_model_smart
            if force_smart_model
            else self._select_model(user_input)
        )
        tools = self._anthropic_tools()
        text_chunks: list[str] = []
        session_id = str(uuid.uuid4())
        token_total = 0

        for _ in range(MAX_TOOL_ROUNDS):
            async with self._client.messages.stream(
                model=model,
                max_tokens=4096,
                system=system_prompt,
                messages=messages,
                tools=tools,
            ) as stream:
                async for event in stream:
                    if getattr(event, "type", None) == "text":
                        piece = getattr(event, "text", "") or ""
                        if piece:
                            text_chunks.append(piece)
                            yield piece
                msg = await stream.get_final_message()
                token_total += _message_usage_tokens(msg)

            messages.append({"role": "assistant", "content": msg.content})

            if (msg.stop_reason or "") != "tool_use":
                break

            tool_results: list[ToolResultBlockParam] = []
            for block in msg.content:
                if block.type != "tool_use":
                    continue
                name = block.name
                raw = block.input
                try:
                    if isinstance(raw, str):
                        args_obj: dict[str, Any] = json.loads(raw)
                    elif isinstance(raw, dict):
                        args_obj = raw
                    else:
                        args_obj = {}
                    payload = await self._registry.dispatch(name, args_obj)
                    self._last_tool_action = {
                        "tool": name,
                        "result_preview": payload[:500],
                    }
                except Exception as exc:
                    logger.exception("Tool dispatch failed for %s", name)
                    payload = f"Tool error: {exc}"
                    self._last_tool_action = {"tool": name, "error": str(exc)}
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": payload,
                    }
                )
            if not tool_results:
                break
            messages.append({"role": "user", "content": tool_results})

        full_text = "".join(text_chunks).strip()
        await self.short_term.add_turn("user", user_input)
        await self.short_term.add_turn("assistant", full_text)
        if full_text or user_input:
            await self._long_term.upsert(
                f"User: {user_input}\nAssistant: {full_text}",
                {"source": "turn"},
            )

        turn_messages: list[dict[str, str]] = [
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": full_text},
        ]
        await asyncio.to_thread(
            log_session,
            self._settings.profile_db_path,
            session_id,
            turn_messages,
            token_total,
        )

        self._turn_count += 1

    async def run_turn(self, user_text: str, use_smart_model: bool = False) -> AgentTurnResult:
        """Consume ``process`` and return the full reply (non-streaming callers / voice loop)."""
        parts: list[str] = []
        async for chunk in self.process(user_text, force_smart_model=use_smart_model):
            parts.append(chunk)
        return AgentTurnResult(text="".join(parts).strip(), action=self._last_tool_action)
