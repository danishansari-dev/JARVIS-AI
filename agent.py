from __future__ import annotations

import logging
import os
import re
import threading
import uuid
from datetime import datetime
from typing import Any

from anthropic import Anthropic

from memory.long_term import LongTermMemory
from memory.profile import UserProfile
from memory.short_term import ShortTermMemory
from tools import build_registry
from voice.tts import TTSEngine

logger = logging.getLogger(__name__)
logging.getLogger("chromadb.telemetry").setLevel(logging.ERROR)


def _load_env_file() -> None:
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return

    with open(env_path, encoding="utf-8") as env_file:
        for line in env_file:
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            key, value = raw.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_env_file()


class JarvisAgent:
    def __init__(self) -> None:
        self.provider = os.getenv("LLM_PROVIDER", "anthropic")
        self.client: Any = None
        self.genai: Any = None
        self.groq_client: Any = None
        self.gemini_model_fast = "gemini-2.0-flash"
        self.gemini_model_smart = "gemini-2.0-flash"
        self.groq_model = "llama-3.3-70b-versatile"
        self.session_id = str(uuid.uuid4())
        if self.provider == "gemini":
            import google.generativeai as genai

            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
            self.genai = genai
        elif self.provider == "groq":
            from groq import Groq

            self.groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        else:
            self.provider = "anthropic"
            self.client = Anthropic()
        self.memory = LongTermMemory()
        self.buffer = ShortTermMemory(max_turns=20)
        self.profile = UserProfile()
        self.registry = build_registry()
        self.tts = TTSEngine()
        self.default_model = "claude-haiku-4-5"
        self.smart_model = "claude-sonnet-4-5"
        self._memory_context: list[str] = []

    def _build_system_prompt(self) -> str:
        name = self.profile.get_fact("user_name", "User")
        city = self.profile.get_fact("user_city", "Unknown")
        now = datetime.now().isoformat(sep=" ", timespec="seconds")
        memory_text = "\n".join(self._memory_context) if self._memory_context else "(none)"
        facts = self.profile.all_facts()
        facts_text = "\n".join(f"{k}: {v}" for k, v in facts.items()) if facts else "(none)"
        return f"""You are JARVIS, a personal AI assistant.
Be concise. Acknowledge completed actions in 5 words or less.
Never say "Of course", "Certainly", "Happy to", or "Great question".
For simple tasks, respond only with the action taken.

User: {name}
Time: {now}
Location: {city}

[Memory context]
{memory_text}

[User preferences]
{facts_text}
User is on Windows. Always use Windows paths or relative paths.
Never use /Users/ or Unix-style home paths. Use ~ or ask for the actual path.
"""

    def _select_model(self, user_input: str) -> str:
        if self.provider == "gemini":
            return self.gemini_model_fast
        lower = user_input.lower()
        keywords = ["explain", "analyze", "compare", "write", "summarize", "draft"]
        if any(keyword in lower for keyword in keywords) and len(user_input) > 80:
            return self.smart_model
        return self.default_model

    @staticmethod
    def _extract_text(response: Any) -> str:
        parts: list[str] = []
        for block in getattr(response, "content", []):
            if getattr(block, "type", None) == "text":
                text = getattr(block, "text", "")
                if text:
                    parts.append(text)
        return "".join(parts).strip()

    def _run_summary_background(self, session_id: str) -> None:
        snapshot = self.buffer.get_last_n(10)
        thread = threading.Thread(
            target=self.memory.summarize_and_store,
            args=(snapshot, session_id),
            daemon=True,
            name="memory-summary",
        )
        thread.start()

    def _claude_tools(self) -> list[dict[str, Any]]:
        return self.registry.to_claude_tools()

    def _gemini_tools(self) -> list[dict[str, Any]]:
        gemini_tools: list[dict[str, Any]] = []
        for tool in self.registry.to_claude_tools():
            gemini_tools.append(
                {
                    "function_declarations": [
                        {
                            "name": tool["name"],
                            "description": tool["description"],
                            "parameters": tool["input_schema"],
                        }
                    ]
                }
            )
        return gemini_tools

    def _messages_to_gemini_contents(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        contents: list[dict[str, Any]] = []
        for message in messages:
            role = "model" if message.get("role") == "assistant" else "user"
            content = message.get("content", "")
            if isinstance(content, str):
                contents.append({"role": role, "parts": [{"text": content}]})
        return contents

    @staticmethod
    def _extract_gemini_text(response: Any) -> str:
        text = getattr(response, "text", None)
        if text:
            return str(text).strip()
        parts: list[str] = []
        for candidate in getattr(response, "candidates", []) or []:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", []) or []:
                part_text = getattr(part, "text", None)
                if part_text:
                    parts.append(str(part_text))
        return "".join(parts).strip()

    @staticmethod
    def _gemini_function_calls(response: Any) -> list[Any]:
        calls: list[Any] = []
        for candidate in getattr(response, "candidates", []) or []:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", []) or []:
                function_call = getattr(part, "function_call", None)
                if function_call is not None:
                    calls.append(function_call)
        return calls

    def _parse_tool_args(self, raw_args: str) -> dict[str, Any]:
        import json

        if not raw_args or raw_args.strip() in ("", "null", "{}"):
            return {}

        # Strip malformed XML-like wrapper if present and salvage JSON object.
        match = re.search(r"\{.*\}", raw_args, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        try:
            return json.loads(raw_args)
        except json.JSONDecodeError:
            return {}

    def _process_anthropic(self, user_input: str, system_prompt: str) -> str:
        selected_model = self._select_model(user_input)
        messages: list[dict[str, Any]] = self.buffer.to_messages()
        response = self.client.messages.create(
            model=selected_model,
            max_tokens=1024,
            system=system_prompt,
            tools=self._claude_tools(),
            messages=messages,
        )

        if getattr(response, "stop_reason", None) == "tool_use":
            while getattr(response, "stop_reason", None) == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                for block in response.content:
                    if getattr(block, "type", None) != "tool_use":
                        continue
                    tool_name = getattr(block, "name", "")
                    tool_input = getattr(block, "input", {}) or {}
                    result = self.registry.dispatch(tool_name, tool_input)
                    messages.append(
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": result,
                                }
                            ],
                        }
                    )
                response = self.client.messages.create(
                    model=selected_model,
                    max_tokens=1024,
                    system=system_prompt,
                    tools=self._claude_tools(),
                    messages=messages,
                )
        final_text = self._extract_text(response)

        self.buffer.add_turn("jarvis", final_text)
        if len(self.buffer) > 0 and len(self.buffer) % 5 == 0:
            self._run_summary_background(session_id=str(uuid.uuid4()))
        self.tts.speak(final_text)
        return final_text

    def _process_gemini(self, user_input: str, system_prompt: str) -> str:
        tools_for_gemini = []
        for tool in self.registry.to_claude_tools():
            func = self.genai.protos.FunctionDeclaration(
                name=tool["name"],
                description=tool["description"],
                parameters=self.genai.protos.Schema(
                    type=self.genai.protos.Type.OBJECT,
                    properties={
                        k: self.genai.protos.Schema(type=self.genai.protos.Type.STRING)
                        for k in tool["input_schema"]["properties"]
                    },
                    required=tool["input_schema"].get("required", []),
                ),
            )
            tools_for_gemini.append(func)

        gemini_tools = [self.genai.protos.Tool(function_declarations=tools_for_gemini)]

        history = []
        for msg in self.buffer.to_messages()[:-1]:
            history.append(
                {
                    "role": "user" if msg["role"] == "user" else "model",
                    "parts": [msg["content"]],
                }
            )

        chat = self.genai.GenerativeModel(
            model_name=self.gemini_model_fast,
            system_instruction=system_prompt,
            tools=gemini_tools,
        ).start_chat(history=history)

        response = chat.send_message(user_input)

        max_tool_rounds = 5
        for _ in range(max_tool_rounds):
            candidate = response.candidates[0]
            has_tool_call = any(
                hasattr(part, "function_call") and part.function_call.name
                for part in candidate.content.parts
            )

            if not has_tool_call:
                break

            tool_results = []
            for part in candidate.content.parts:
                if hasattr(part, "function_call") and part.function_call.name:
                    fc = part.function_call
                    tool_input = dict(fc.args)
                    result = self.registry.dispatch(fc.name, tool_input)
                    tool_results.append(
                        self.genai.protos.Part(
                            function_response=self.genai.protos.FunctionResponse(
                                name=fc.name,
                                response={"result": result},
                            )
                        )
                    )

            response = chat.send_message(tool_results)

        final_text = ""
        for part in response.candidates[0].content.parts:
            if hasattr(part, "text") and part.text:
                final_text += part.text

        if not final_text:
            final_text = "Done."

        self.buffer.add_turn("assistant", final_text)
        if len(self.buffer.to_messages()) % 5 == 0:
            import threading

            threading.Thread(
                target=self.memory.summarize_and_store,
                args=(self.buffer.get_last_n(10), self.session_id),
                daemon=True,
            ).start()

        self.tts.speak(final_text)
        return final_text

    def _process_groq(self, user_input: str, system_prompt: str) -> str:
        # Groq uses OpenAI-compatible API with tool calling
        # Convert registry tools to OpenAI function format
        tools_openai = []
        for tool in self.registry.to_claude_tools():
            tools_openai.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": tool["input_schema"],
                    },
                }
            )

        # Build messages: system + history + current user message
        messages = [{"role": "system", "content": system_prompt}]
        for msg in self.buffer.to_messages():
            messages.append(msg)

        # First call
        response = self.groq_client.chat.completions.create(
            model=self.groq_model,
            messages=messages,
            tools=tools_openai,
            tool_choice="auto",
            max_tokens=1024,
        )

        # Tool call loop (max 5 rounds)
        for _ in range(5):
            message = response.choices[0].message

            if not message.tool_calls:
                break

            # Append assistant message with tool calls
            messages.append(
                {
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in message.tool_calls
                    ],
                }
            )

            # Execute each tool call
            for tc in message.tool_calls:
                tool_input = self._parse_tool_args(tc.function.arguments)
                result = self.registry.dispatch(tc.function.name, tool_input)
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": result}
                )

            # Follow-up call with tool results
            response = self.groq_client.chat.completions.create(
                model=self.groq_model,
                messages=messages,
                tools=tools_openai,
                tool_choice="auto",
                max_tokens=1024,
            )

        # Extract final text
        final_text = response.choices[0].message.content or "Done."

        # Buffer + memory + TTS
        self.buffer.add_turn("jarvis", final_text)

        if len(self.buffer.to_messages()) % 5 == 0:
            import threading

            threading.Thread(
                target=self.memory.summarize_and_store,
                args=(self.buffer.get_last_n(10), self.session_id),
                daemon=True,
            ).start()

        self.tts.speak(final_text)
        return final_text

    def process(self, user_input: str) -> str:
        memory_chunks = self.memory.query(user_input, k=3)
        self._memory_context = memory_chunks[:3]
        system_prompt = self._build_system_prompt()

        self.buffer.add_turn("user", user_input)
        self._select_model(user_input)

        if self.provider == "groq":
            return self._process_groq(user_input, system_prompt)
        elif self.provider == "gemini":
            return self._process_gemini(user_input, system_prompt)
        else:
            return self._process_anthropic(user_input, system_prompt)

    def run_cli(self) -> None:
        while True:
            try:
                user_input = input("You: ").strip()
                if user_input.lower() in ["exit", "quit"]:
                    break
                response = self.process(user_input)
                print(f"JARVIS: {response}")
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"JARVIS: I encountered an error: {e}")


if __name__ == "__main__":
    agent = JarvisAgent()
    print(f"JARVIS online. provider={agent.provider}")
    agent.run_cli()
