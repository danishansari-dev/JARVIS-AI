"""Tool registry: Pydantic-validated tools with Claude-compatible schemas (max 8)."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

MAX_ACTIVE_TOOLS = 8


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    description: str
    input_schema: type[BaseModel]
    handler: Callable[[BaseModel], Any]


class ToolRegistry:
    """Registers tools, exposes Claude ``tools`` JSON, and dispatches with Pydantic validation."""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(
        self,
        name: str,
        description: str,
        input_schema: type[BaseModel],
        handler: Callable[[BaseModel], Any],
    ) -> None:
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        if len(self._tools) >= MAX_ACTIVE_TOOLS:
            raise RuntimeError(f"At most {MAX_ACTIVE_TOOLS} tools may be registered at once")
        self._tools[name] = RegisteredTool(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=handler,
        )

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def registered_tool_names(self) -> list[str]:
        return sorted(self._tools.keys())

    def to_claude_tools(self) -> list[dict[str, Any]]:
        """Anthropic Messages API tool definitions (``name``, ``description``, ``input_schema``)."""
        out: list[dict[str, Any]] = []
        for t in self._tools.values():
            out.append(
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema.model_json_schema(),
                }
            )
        return out

    async def dispatch(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        tool = self._tools.get(tool_name)
        if tool is None:
            raise KeyError(f"Unknown tool: {tool_name}")
        try:
            model = tool.input_schema.model_validate(tool_input)
        except ValidationError as exc:
            logger.warning("Tool validation failed for %s: %s", tool_name, exc)
            raise
        fn = tool.handler
        if inspect.iscoroutinefunction(fn):
            raw = await fn(model)
        else:
            raw = await asyncio.to_thread(fn, model)
        if not isinstance(raw, str):
            return str(raw)
        return raw
