from __future__ import annotations

import logging
import os
import re
import threading
import uuid
from datetime import datetime
from typing import Any

from groq import Groq

from memory.long_term import LongTermMemory
from memory.profile import UserProfile
from memory.short_term import ShortTermMemory
from tools import build_registry
from voice.tts import TTSEngine
from main_api import log_session

logger = logging.getLogger(__name__)
logging.getLogger("chromadb.telemetry").setLevel(logging.ERROR)
logging.getLogger("chromadb").setLevel(logging.WARNING)

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
        self.provider = "groq"
        self.groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = "llama-3.3-70b-versatile"
        
        self.memory = LongTermMemory()
        self.buffer = ShortTermMemory(max_turns=20)
        self.profile = UserProfile()
        
        self.tts = TTSEngine()
        self.registry = build_registry(tts_engine=self.tts)
        
        self.session_id = f"s_{uuid.uuid4().hex[:4]}"

    def _build_system_prompt(self, memory_chunks: list[str]) -> str:
        return f"""You are JARVIS, a personal AI assistant running on Windows.

RULES:
- Be concise. Max 2 sentences for simple tasks.
- Never say "Of course", "Certainly", "Happy to", "Great question".
- For completed actions, respond in 5 words or less. Example: "Done." "Opened." "Files moved."
- Only elaborate when the user explicitly asks for explanation.
- Always use Windows-style paths (C:\\Users\\...). Never use Unix paths like /Users/.
- When user says "Downloads", "Desktop", "Documents" — resolve to actual Windows path using home directory.

USER PROFILE:
Name: {self.profile.get_fact("name") or "Unknown"}
City: {self.profile.get_fact("city") or "Unknown"}  
Timezone: {self.profile.get_fact("timezone") or "Asia/Kolkata"}
Current time: {datetime.now().strftime("%A, %d %B %Y %I:%M %p")}

MEMORY CONTEXT:
{chr(10).join(f"- {chunk}" for chunk in memory_chunks) if memory_chunks else "No relevant memory found."}

USER PREFERENCES:
{chr(10).join(f"{k}: {v}" for k, v in self.profile.all_facts().items())}"""

    def _parse_tool_args(self, raw_args: str) -> dict[str, Any]:
        import json

        if not raw_args or raw_args.strip() in ("", "null", "{}"):
            return {}

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

    def process(self, user_input: str) -> str:
        memory_chunks = self.memory.query(user_input, k=3)
        system_prompt = self._build_system_prompt(memory_chunks)
        self.buffer.add_turn("user", user_input)

        tools_groq = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"]
                }
            }
            for t in self.registry.to_claude_tools()
        ]

        messages = [{"role": "system", "content": system_prompt}]
        messages += self.buffer.to_messages()

        try:
            response = self.groq_client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools_groq,
                tool_choice="auto",
                max_tokens=1024,
                temperature=0.3,
                timeout=15.0
            )
        except Exception as e:
            logger.error(f"Groq API Error: {e}")
            return f"I encountered an error predicting a response: {e}"

        for _ in range(5):
            message = response.choices[0].message
            if not message.tool_calls:
                break
            
            messages.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function", 
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in message.tool_calls
                ]
            })
            
            for tc in message.tool_calls:
                tool_input = self._parse_tool_args(tc.function.arguments)
                result = self.registry.dispatch(tc.function.name, tool_input)
                logging.info(f"[TOOL] {tc.function.name} → {str(result)[:80]}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": str(result)
                })
            
            try:
                response = self.groq_client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools_groq,
                    tool_choice="auto",
                    max_tokens=1024,
                    temperature=0.3,
                    timeout=15.0
                )
            except Exception as e:
                logger.error(f"Groq API Error during tool resolution: {e}")
                return "I encountered an error trying to process that tool."

        final_text = response.choices[0].message.content or "Done."
        self.buffer.add_turn("jarvis", final_text)

        if len(self.buffer) % 5 == 0:
            threading.Thread(
                target=self.memory.summarize_and_store,
                args=(self.buffer.get_last_n(10), self.session_id),
                daemon=True
            ).start()

        threading.Thread(
            target=log_session,
            args=(self.session_id, self.buffer.to_messages(), 0),
            daemon=True
        ).start()

        if len(final_text.split()) <= 10:
            try:
                self.tts.speak(final_text, force_local=True)
            except TypeError:
                self.tts.speak(final_text)
        else:
            self.tts.speak(final_text)

        return final_text
