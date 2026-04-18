"""FastAPI control plane for JARVIS dashboard (port 8765)."""

from __future__ import annotations

import json
import logging
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sentence_transformers import SentenceTransformer

from database.db_setup import DB_PATH, get_db, init_db

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent
_CHROMA_DIR = _REPO_ROOT / "data" / "chroma"
_COLLECTION_NAME = "jarvis_memory"

_SERVER_STARTED_AT: float | None = None


class MiniLMEmbeddingFunction(EmbeddingFunction):
    """Chroma embedding adapter (all-MiniLM-L6-v2), matches ``jarvis.memory.long_term``."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model = SentenceTransformer(model_name)

    def __call__(self, input: Documents) -> list[list[float]]:
        return self._model.encode(list(input), convert_to_numpy=True).tolist()


def _chroma_collection():
    """Return collection or None if missing / unusable."""
    try:
        _CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(_CHROMA_DIR))
        embed_fn = MiniLMEmbeddingFunction()
        return client.get_collection(name=_COLLECTION_NAME, embedding_function=embed_fn)
    except Exception as exc:
        logger.warning("Chroma collection unavailable: %s", exc)
        return None


def _cosine_similarity_score(distance: float) -> float:
    """Map Chroma cosine *distance* to a 0–1 similarity-style score for the API."""
    try:
        d = float(distance)
    except (TypeError, ValueError):
        return 0.0
    sim = max(0.0, min(1.0, 1.0 - d))
    return round(sim, 2)


def _parse_tags(meta: dict[str, Any] | None) -> list[str]:
    if not meta:
        return []
    raw = meta.get("tags")
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except json.JSONDecodeError:
            pass
        return [s]
    return [str(raw)]


def _meta_ts(meta: dict[str, Any] | None) -> float | None:
    if not meta:
        return None
    for key in ("timestamp", "created_ts", "last_accessed_ts"):
        v = meta.get(key)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def _age_label(meta: dict[str, Any] | None) -> str:
    ts = _meta_ts(meta)
    if ts is None:
        return ""
    try:
        then = datetime.fromtimestamp(ts, tz=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - then
        days = max(0, int(delta.total_seconds() // 86400))
        if days == 0:
            h = int(delta.total_seconds() // 3600)
            if h == 0:
                m = max(1, int(delta.total_seconds() // 60))
                return f"{m}m ago"
            return f"{h}h ago"
        if days == 1:
            return "1d ago"
        return f"{days}d ago"
    except Exception:
        return ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _SERVER_STARTED_AT
    _SERVER_STARTED_AT = time.time()
    init_db()
    logger.info("SQLite initialized at %s", DB_PATH)
    yield


app = FastAPI(title="JARVIS API", version="0.4.1", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(127\.0\.0\.1|localhost)(:[0-9]+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/status")
def status() -> dict[str, Any]:
    if _SERVER_STARTED_AT is None:
        uptime = 0
    else:
        uptime = int(time.time() - _SERVER_STARTED_AT)

    with get_db() as conn:
        row = conn.execute(
            "SELECT value FROM user_facts WHERE key = ?",
            ("model_preference",),
        ).fetchone()
        model = str(row["value"]) if row else "haiku"

        ym = datetime.now(timezone.utc).strftime("%Y-%m")
        row_u = conn.execute(
            "SELECT chars_used FROM elevenlabs_usage WHERE month = ?",
            (ym,),
        ).fetchone()
        eleven_used = int(row_u["chars_used"]) if row_u else 0

    return {
        "version": "0.4.1",
        "online": True,
        "model": model,
        "uptime_seconds": uptime,
        "elevenlabs_used": eleven_used,
        "elevenlabs_limit": 10000,
    }


@app.get("/briefing/today")
def briefing_today() -> dict[str, Any]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with get_db() as conn:
        row = conn.execute(
            "SELECT date, weather, calendar_summary, bullets FROM briefings WHERE date = ?",
            (today,),
        ).fetchone()
    if not row:
        return {
            "date": today,
            "weather": "",
            "calendar_summary": "",
            "bullets": [],
        }
    bullets_raw = row["bullets"]
    try:
        bullets = json.loads(str(bullets_raw)) if bullets_raw else []
        if not isinstance(bullets, list):
            bullets = []
    except json.JSONDecodeError:
        bullets = []
    return {
        "date": str(row["date"]),
        "weather": str(row["weather"]),
        "calendar_summary": str(row["calendar_summary"]),
        "bullets": [str(b) for b in bullets],
    }


@app.get("/sessions")
def list_sessions() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, timestamp, preview, message_count, token_count
            FROM sessions
            ORDER BY timestamp DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="session not found")
        msgs = conn.execute(
            """
            SELECT role, content, timestamp
            FROM session_messages
            WHERE session_id = ?
            ORDER BY timestamp ASC, id ASC
            """,
            (session_id,),
        ).fetchall()
    return {
        "id": session_id,
        "messages": [
            {"role": str(m["role"]), "content": str(m["content"]), "timestamp": str(m["timestamp"])}
            for m in msgs
        ],
    }


@app.get("/memory/chunks")
def memory_chunks(
    query: str = Query("", alias="query"),
    limit: int = Query(12, ge=1, le=100),
) -> list[dict[str, Any]]:
    col = _chroma_collection()
    if col is None:
        return []

    try:
        if not query.strip():
            try:
                n_docs = col.count()
            except Exception:
                n_docs = 0
            if n_docs == 0:
                return []
            fetch_n = min(500, max(n_docs, limit))
            batch = col.get(include=["documents", "metadatas"], limit=fetch_n)
            ids = batch.get("ids") or []
            docs = batch.get("documents") or []
            metas = batch.get("metadatas") or []
            triples: list[tuple[str, str, dict[str, Any] | None, float]] = []
            for i, doc_id in enumerate(ids):
                meta = metas[i] if i < len(metas) else None
                ts = _meta_ts(meta) or 0.0
                text = docs[i] if i < len(docs) else ""
                triples.append((doc_id, str(text), meta, ts))
            triples.sort(key=lambda x: x[3], reverse=True)
            triples = triples[:limit]
            out: list[dict[str, Any]] = []
            for doc_id, text, meta, _ in triples:
                out.append(
                    {
                        "id": str(doc_id),
                        "text": text,
                        "tags": _parse_tags(meta),
                        "score": 1.0,
                        "age_label": _age_label(meta),
                    }
                )
            return out

        try:
            cnt = col.count()
        except Exception:
            cnt = 0
        if cnt == 0:
            return []
        n_results = min(limit, cnt)
        res = col.query(
            query_texts=[query.strip()],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
        ids = (res.get("ids") or [[]])[0]
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        out = []
        for i, doc_id in enumerate(ids):
            dist = dists[i] if i < len(dists) else 1.0
            meta = metas[i] if i < len(metas) else None
            text = docs[i] if i < len(docs) else ""
            out.append(
                {
                    "id": str(doc_id),
                    "text": str(text),
                    "tags": _parse_tags(meta),
                    "score": _cosine_similarity_score(dist),
                    "age_label": _age_label(meta),
                }
            )
        return out
    except Exception:
        logger.exception("memory_chunks failed")
        return []


@app.delete("/memory/chunks/{chunk_id}")
def delete_memory_chunk(chunk_id: str) -> dict[str, Any]:
    col = _chroma_collection()
    if col is None:
        raise HTTPException(status_code=503, detail="memory store unavailable")
    try:
        col.delete(ids=[chunk_id])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"deleted": True, "id": chunk_id}


@app.get("/settings")
def get_settings() -> dict[str, str]:
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM user_facts").fetchall()
    return {str(r["key"]): str(r["value"]) for r in rows}


@app.post("/settings")
def post_settings(body: dict[str, Any] = Body(...)) -> dict[str, int]:
    now = datetime.now(timezone.utc).isoformat()
    updated = 0
    with get_db() as conn:
        for key, value in body.items():
            if key.startswith("_"):
                continue
            k = str(key)
            if not re.match(r"^[a-zA-Z0-9_.-]+$", k):
                continue
            v = value if isinstance(value, str) else json.dumps(value, default=str)
            conn.execute(
                """
                INSERT INTO user_facts(key, value, updated_at)
                VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (k, str(v), now),
            )
            updated += 1
        conn.commit()
    return {"updated": updated}


# --- Data writers (called from agent / scheduler later) ---


def _normalize_role(role: str) -> str:
    r = (role or "").strip().lower()
    if r == "user":
        return "user"
    return "jarvis"


def log_session(session_id: str, messages: list[Any], token_count: int) -> None:
    """Upsert a session row and replace its messages."""
    now = datetime.now(timezone.utc).isoformat()
    preview = ""
    for m in messages:
        if not isinstance(m, dict):
            continue
        if str(m.get("role", "")).lower() in ("user",):
            preview = str(m.get("content", ""))[:60]
            break
    if len(preview) > 60:
        preview = preview[:59] + "…"

    with get_db() as conn:
        conn.execute("DELETE FROM session_messages WHERE session_id = ?", (session_id,))
        conn.execute(
            """
            INSERT INTO sessions(id, timestamp, preview, message_count, token_count)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                timestamp = excluded.timestamp,
                preview = excluded.preview,
                message_count = excluded.message_count,
                token_count = excluded.token_count
            """,
            (session_id, now, preview or "(no preview)", len(messages), int(token_count)),
        )
        for m in messages:
            if not isinstance(m, dict):
                continue
            role = _normalize_role(str(m.get("role", "")))
            content = str(m.get("content", ""))
            ts = str(m.get("timestamp") or now)
            conn.execute(
                """
                INSERT INTO session_messages(session_id, role, content, timestamp)
                VALUES(?, ?, ?, ?)
                """,
                (session_id, role, content, ts),
            )
        conn.commit()


def log_elevenlabs_usage(chars_used: int) -> None:
    """Increment ``chars_used`` for the current UTC month."""
    if chars_used <= 0:
        return
    ym = datetime.now(timezone.utc).strftime("%Y-%m")
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO elevenlabs_usage(month, chars_used) VALUES(?, ?)
            ON CONFLICT(month) DO UPDATE SET
                chars_used = elevenlabs_usage.chars_used + excluded.chars_used
            """,
            (ym, int(chars_used)),
        )
        conn.commit()


def log_briefing(
    date: str,
    weather: str,
    calendar_summary: str,
    bullets: list[str],
) -> None:
    """Upsert a briefing row."""
    now = datetime.now(timezone.utc).isoformat()
    bullets_json = json.dumps(list(bullets), ensure_ascii=False)
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO briefings(date, weather, calendar_summary, bullets, created_at)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                weather = excluded.weather,
                calendar_summary = excluded.calendar_summary,
                bullets = excluded.bullets,
                created_at = excluded.created_at
            """,
            (date, weather, calendar_summary, bullets_json, now),
        )
        conn.commit()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main_api:app", host="127.0.0.1", port=8765, reload=True)
