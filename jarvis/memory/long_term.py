"""Long-term memory using ChromaDB + local sentence-transformers embeddings."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings
from anthropic import Anthropic
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class LongTermMemory:
    def __init__(self) -> None:
        self._client = chromadb.PersistentClient(
            path="data/chroma",
            settings=Settings(anonymized_telemetry=False)
        )
        self._collection = self._client.get_or_create_collection(name="jarvis_memory")
        start = datetime.now(UTC)
        self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
        elapsed_ms = (datetime.now(UTC) - start).total_seconds() * 1000.0
        logger.info("Loaded all-MiniLM-L6-v2 in %.1f ms", elapsed_ms)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _token_count(text: str) -> int:
        return len(text.split())

    def _chunk_text(self, text: str, max_tokens: int = 200) -> list[str]:
        normalized = text.strip()
        if not normalized:
            return []
        if self._token_count(normalized) <= max_tokens:
            return [normalized]

        sentences = [s.strip() for s in normalized.split(". ") if s.strip()]
        chunks: list[str] = []
        current: list[str] = []
        current_tokens = 0

        for sentence in sentences:
            sentence_text = sentence if sentence.endswith(".") else f"{sentence}."
            sentence_tokens = self._token_count(sentence_text)
            if current and current_tokens + sentence_tokens > max_tokens:
                chunks.append(" ".join(current).strip())
                current = []
                current_tokens = 0
            current.append(sentence_text)
            current_tokens += sentence_tokens

        if current:
            chunks.append(" ".join(current).strip())
        return chunks if chunks else [normalized]

    @staticmethod
    def _coerce_metadata(metadata: dict[str, Any]) -> dict[str, str | int | float | bool]:
        coerced: dict[str, str | int | float | bool] = {}
        for key, value in metadata.items():
            if isinstance(value, (str, int, float, bool)):
                coerced[key] = value
            else:
                coerced[key] = str(value)
        return coerced

    def store(self, text: str, metadata: dict = {}) -> str | list[str]:
        meta = self._coerce_metadata(dict(metadata))
        meta["timestamp"] = self._now_iso()

        chunks = self._chunk_text(text, max_tokens=200)
        if not chunks:
            raise ValueError("Cannot store empty text")

        embeddings = self._embedder.encode(chunks, convert_to_numpy=True).tolist()
        ids = [str(uuid.uuid4()) for _ in chunks]
        metadatas = [dict(meta, chunk_index=i) for i in range(len(chunks))]
        self._collection.upsert(ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas)
        return ids[0] if len(ids) == 1 else ids

    @staticmethod
    def _parse_iso_timestamp(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None

    @staticmethod
    def _recency_decay(timestamp_iso: str | None) -> float:
        parsed = LongTermMemory._parse_iso_timestamp(timestamp_iso)
        if parsed is None:
            return 0.3
        age_days = (datetime.now(UTC) - parsed).days
        if age_days <= 7:
            return 1.0
        if age_days <= 30:
            return 0.8
        if age_days <= 90:
            return 0.5
        return 0.3

    def query(self, text: str, k: int = 5) -> list[str]:
        query_embedding = self._embedder.encode([text], convert_to_numpy=True).tolist()[0]
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=max(k * 2, 1),
            include=["documents", "distances", "metadatas"],
        )

        documents = (results.get("documents") or [[]])[0] or []
        distances = (results.get("distances") or [[]])[0] or []
        metadatas = (results.get("metadatas") or [[]])[0] or []

        ranked: list[tuple[float, str]] = []
        for doc, distance, metadata in zip(documents, distances, metadatas, strict=False):
            try:
                dist = float(distance)
            except (TypeError, ValueError):
                continue
            if dist >= 0.25:
                continue
            decay = self._recency_decay((metadata or {}).get("timestamp"))
            adjusted_score = (1.0 - dist) * decay
            ranked.append((adjusted_score, doc))

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [doc for _, doc in ranked[:k]]

    def summarize_and_store(self, messages: list[dict], session_id: str) -> None:
        if not messages:
            return

        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for summarize_and_store")

        transcript_lines: list[str] = []
        for message in messages:
            role = str(message.get("role", "")).strip() or "unknown"
            content = str(message.get("content", "")).strip()
            transcript_lines.append(f"{role}: {content}")
        transcript = "\n".join(transcript_lines)

        prompt = (
            "Extract 3-5 key facts or preferences from this conversation as short bullet points.\n"
            "Each bullet max 20 words. Facts only — no filler.\n\n"
            f"{transcript}"
        )

        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model=os.getenv("CLAUDE_MODEL_FAST", "claude-3-5-haiku-latest"),
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )

        bullets: list[str] = []
        for block in response.content:
            if getattr(block, "type", None) != "text":
                continue
            for raw_line in block.text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                cleaned = line.lstrip("-*• ").strip()
                if cleaned:
                    bullets.append(cleaned)

        now = self._now_iso()
        for bullet in bullets:
            self.store(
                bullet,
                {"session_id": session_id, "type": "session_summary", "timestamp": now},
            )

    def prune_old(self, days: int = 90) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        records = self._collection.get(include=["metadatas"])
        ids = records.get("ids") or []
        metadatas = records.get("metadatas") or []

        to_delete: list[str] = []
        for doc_id, metadata in zip(ids, metadatas, strict=False):
            timestamp = self._parse_iso_timestamp((metadata or {}).get("timestamp"))
            if timestamp is not None and timestamp < cutoff:
                to_delete.append(doc_id)

        if to_delete:
            self._collection.delete(ids=to_delete)
        return len(to_delete)


if __name__ == "__main__":
    mem = LongTermMemory()
    mem.store(
        "User prefers concise answers. Dislikes long explanations.",
        {"type": "preference"},
    )
    results = mem.query("how should I respond to the user")
    print("Query results:", results)
    print("Memory OK" if results else "Stored but below threshold — expected on first run")
