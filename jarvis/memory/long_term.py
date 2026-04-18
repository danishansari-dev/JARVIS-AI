"""ChromaDB long-term memory: chunked storage, cosine query, session summarization, pruning."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

import chromadb
import tiktoken
from anthropic import AsyncAnthropic
from chromadb.api.types import Documents, EmbeddingFunction, Metadatas
from sentence_transformers import SentenceTransformer

from jarvis.config import Settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "jarvis_memory"
CHUNK_MAX_TOKENS = 200
# Cosine distance (Chroma: ~1 - similarity for normalized vectors); keep strong matches only.
MAX_COSINE_DISTANCE = 0.25


class MiniLMEmbeddingFunction(EmbeddingFunction):
    """EmbeddingFunction adapter for Chroma using all-MiniLM-L6-v2."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model = SentenceTransformer(model_name)

    def __call__(self, input: Documents) -> list[list[float]]:
        return self._model.encode(list(input), convert_to_numpy=True).tolist()


def _chunk_text_by_tokens(text: str, max_tokens: int = CHUNK_MAX_TOKENS) -> list[str]:
    enc = tiktoken.get_encoding("cl100k_base")
    ids = enc.encode(text)
    if not ids:
        return []
    chunks: list[str] = []
    for i in range(0, len(ids), max_tokens):
        chunk = enc.decode(ids[i : i + max_tokens])
        if chunk.strip():
            chunks.append(chunk)
    return chunks


class LongTermMemory:
    """Persistent Chroma collection with MiniLM embeddings, chunk upserts, and session summaries."""

    def __init__(
        self,
        persist_directory: Path,
        settings: Settings | None = None,
        collection_name: str = COLLECTION_NAME,
    ) -> None:
        self._settings = settings
        self._persist_directory = Path(persist_directory)
        self._persist_directory.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self._persist_directory))
        self._embed_fn = MiniLMEmbeddingFunction()
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=self._embed_fn,
            metadata={"hnsw:space": "cosine"},
        )
        self._executor = asyncio.ThreadPoolExecutor(max_workers=1, thread_name_prefix="chroma")

    def _now_ts(self) -> float:
        return time.time()

    def _merge_meta(self, base: dict[str, Any], chunk_index: int, parent_id: str) -> dict[str, Any]:
        ts = self._now_ts()
        out: dict[str, Any] = {
            "created_ts": ts,
            "last_accessed_ts": ts,
            "chunk_index": int(chunk_index),
            "parent_id": parent_id,
        }
        for k, v in base.items():
            if k in ("created_ts", "last_accessed_ts", "chunk_index", "parent_id"):
                continue
            if isinstance(v, (str, int, float, bool)):
                out[k] = v
            else:
                out[k] = str(v)
        return out

    async def upsert(self, text: str, metadata: dict[str, Any]) -> None:
        """Chunk ``text`` into ~200-token pieces, embed with MiniLM, and upsert into Chroma."""
        chunks = _chunk_text_by_tokens(text.strip(), CHUNK_MAX_TOKENS)
        if not chunks:
            return
        parent_id = str(uuid.uuid4())
        ids = [f"{parent_id}:{i}" for i in range(len(chunks))]
        metadatas: list[dict[str, Any]] = [
            self._merge_meta(metadata, i, parent_id) for i in range(len(chunks))
        ]

        def _run() -> None:
            self._collection.upsert(ids=ids, documents=chunks, metadatas=metadatas)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, _run)

    async def query(self, text: str, k: int = 5) -> list[str]:
        """Cosine search; drop chunks with distance > 0.25 (similarity < 0.75); return text only."""

        def _run() -> Any:
            return self._collection.query(
                query_texts=[text],
                n_results=k,
                include=["documents", "distances", "metadatas", "ids"],
            )

        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(self._executor, _run)
        docs = (raw.get("documents") or [[]])[0] or []
        dists = (raw.get("distances") or [[]])[0] or []
        ids = (raw.get("ids") or [[]])[0] or []
        out_docs: list[str] = []
        touch_ids: list[str] = []
        for doc, dist, doc_id in zip(docs, dists, ids, strict=False):
            try:
                d = float(dist)
            except (TypeError, ValueError):
                continue
            if d > MAX_COSINE_DISTANCE:
                continue
            out_docs.append(doc)
            touch_ids.append(doc_id)

        if touch_ids:
            await self._touch_last_accessed(touch_ids)
        return out_docs

    async def _touch_last_accessed(self, ids: list[str]) -> None:
        now = self._now_ts()

        def _run() -> None:
            existing = self._collection.get(ids=ids, include=["documents", "metadatas"])
            got_ids = existing.get("ids") or []
            documents = existing.get("documents") or []
            metas = existing.get("metadatas") or []
            if not got_ids:
                return
            new_metas: list[dict[str, Any]] = []
            for md in metas:
                m = dict(md or {})
                m["last_accessed_ts"] = now
                new_metas.append(m)
            self._collection.upsert(ids=list(got_ids), documents=list(documents), metadatas=new_metas)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, _run)

    async def summarize_and_store(self, session_messages: list[dict[str, Any]]) -> None:
        """Summarize a session with Claude Haiku into 3–5 bullets and store each as a memory chunk."""
        if not self._settings:
            raise RuntimeError("LongTermMemory requires Settings for summarize_and_store")
        if not session_messages:
            return
        lines = []
        for m in session_messages:
            role = str(m.get("role", ""))
            raw = m.get("content", "")
            if isinstance(raw, str):
                content = raw
            else:
                content = json.dumps(raw, default=str)
            lines.append(f"{role}: {content}")
        transcript = "\n".join(lines)
        client = AsyncAnthropic(api_key=self._settings.anthropic_api_key)
        msg = await client.messages.create(
            model=self._settings.claude_model_fast,
            max_tokens=600,
            system=(
                "Extract 3-5 concise, durable facts from the session as Markdown bullet lines "
                "starting with '- '. No preamble."
            ),
            messages=[{"role": "user", "content": transcript}],
        )
        bullets: list[str] = []
        for block in msg.content:
            if block.type == "text":
                for line in block.text.splitlines():
                    s = line.strip()
                    if s.startswith(("- ", "* ", "• ")):
                        bullets.append(s.lstrip("*• ").lstrip("- ").strip())
        if not bullets:
            return
        for b in bullets:
            if b:
                await self.upsert(b, {"source": "session_summary"})

    async def prune_old(self, days: int = 90) -> int:
        """Remove chunks created before ``days`` ago and not accessed in the last 30 days."""
        now = self._now_ts()
        created_cutoff = now - float(days) * 86400.0
        access_cutoff = now - 30.0 * 86400.0

        def _run() -> int:
            batch = self._collection.get(include=["metadatas"])
            got_ids = batch.get("ids") or []
            metas = batch.get("metadatas") or []
            to_delete: list[str] = []
            for doc_id, md in zip(got_ids, metas, strict=False):
                if not md or "created_ts" not in md or "last_accessed_ts" not in md:
                    continue
                try:
                    created = float(md["created_ts"])
                    accessed = float(md["last_accessed_ts"])
                except (TypeError, ValueError, KeyError):
                    continue
                if created < created_cutoff and accessed < access_cutoff:
                    to_delete.append(doc_id)
            if to_delete:
                self._collection.delete(ids=to_delete)
            return len(to_delete)

        loop = asyncio.get_running_loop()
        removed = int(await loop.run_in_executor(self._executor, _run))
        if removed:
            logger.info("long_term_prune_removed=%d", removed)
        return removed

    async def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
