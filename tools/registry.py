from __future__ import annotations

import logging
import time
from typing import Callable, Type

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


class ToolRegistry:
    MAX_TOOLS = 20

    def __init__(self) -> None:
        self.tools = {}

    def register(
        self,
        name: str,
        description: str,
        input_schema: Type[BaseModel],
        handler: Callable,
    ) -> None:
        if len(self.tools) >= self.MAX_TOOLS:
            raise ValueError("Maximum number of tools reached")
        self.tools[name] = {
            "description": description,
            "schema": input_schema,
            "handler": handler,
        }

    def to_claude_tools(self) -> list[dict]:
        claude_tools: list[dict] = []
        for name, info in self.tools.items():
            model_schema = info["schema"].schema()
            claude_tools.append(
                {
                    "name": name,
                    "description": info["description"],
                    "input_schema": {
                        "type": "object",
                        "properties": model_schema.get("properties", {}),
                        "required": model_schema.get("required", []),
                    },
                }
            )
        return claude_tools

    def dispatch(self, tool_name: str, tool_input: dict) -> str:
        if tool_name not in self.tools:
            return f"Error: unknown tool '{tool_name}'"

        entry = self.tools[tool_name]
        schema = entry["schema"]
        handler = entry["handler"]
        started = time.perf_counter()

        try:
            validated_input = schema(**tool_input)
        except ValidationError as exc:
            result = f"Error: validation failed - {exc}"
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            logger.info(
                "tool=%s input=%s result=%s time_ms=%.2f",
                tool_name,
                tool_input,
                result,
                elapsed_ms,
            )
            return result

        try:
            handler_result = handler(validated_input)
            result = str(handler_result)
        except Exception as exc:  # noqa: BLE001
            result = f"Error: {exc}"

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        logger.info(
            "tool=%s input=%s result=%s time_ms=%.2f",
            tool_name,
            tool_input,
            result,
            elapsed_ms,
        )
        return result
