#!/usr/bin/env python3
"""Smoke-test JARVIS FastAPI (``main_api.py``) on port 8765."""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import httpx

DEFAULT_BASE = "http://127.0.0.1:8765"
BASE = os.environ.get("JARVIS_API_BASE", DEFAULT_BASE).rstrip("/")


def _print_response(name: str, r: httpx.Response) -> None:
    body = r.text
    if len(body) > 600:
        body = body[:600] + "\n... [truncated]"
    print(f"\n--- {name} ---")
    print(f"status: {r.status_code}")
    print(body)


def main() -> int:
    failures: list[str] = []
    first_session_id: str | None = None

    with httpx.Client(base_url=BASE, timeout=15.0) as client:
        # GET /health
        r = client.get("/health")
        _print_response("GET /health", r)
        if r.status_code != 200:
            failures.append("GET /health")

        # GET /status
        r = client.get("/status")
        _print_response("GET /status", r)
        if r.status_code != 200:
            failures.append("GET /status")

        # GET /briefing/today
        r = client.get("/briefing/today")
        _print_response("GET /briefing/today", r)
        if r.status_code != 200:
            failures.append("GET /briefing/today")

        # GET /sessions
        r = client.get("/sessions")
        _print_response("GET /sessions", r)
        if r.status_code != 200:
            failures.append("GET /sessions")
        else:
            try:
                data = r.json()
                if isinstance(data, list) and data:
                    sid = data[0].get("id")
                    if sid:
                        first_session_id = str(sid)
            except json.JSONDecodeError:
                failures.append("GET /sessions (invalid JSON)")

        # GET /sessions/{id}
        if first_session_id:
            r = client.get(f"/sessions/{first_session_id}")
            _print_response(f"GET /sessions/{first_session_id}", r)
            if r.status_code != 200:
                failures.append(f"GET /sessions/{first_session_id}")
        else:
            print("\n--- GET /sessions/{id} ---\n[SKIP] no sessions in DB; seed with `python -m database.db_setup`")

        # GET /memory/chunks
        r = client.get("/memory/chunks")
        _print_response("GET /memory/chunks", r)
        if r.status_code != 200:
            failures.append("GET /memory/chunks")

        # GET /memory/chunks?query=calendar
        r = client.get("/memory/chunks", params={"query": "calendar"})
        _print_response("GET /memory/chunks?query=calendar", r)
        if r.status_code != 200:
            failures.append("GET /memory/chunks?query=calendar")

        # GET /settings
        r = client.get("/settings")
        _print_response("GET /settings (before POST)", r)
        if r.status_code != 200:
            failures.append("GET /settings (before POST)")

        # POST /settings
        post_body = {"name": "Danish", "city": "Dharwad", "timezone": "Asia/Kolkata"}
        r = client.post("/settings", json=post_body)
        _print_response("POST /settings", r)
        if r.status_code != 200:
            failures.append("POST /settings")
        else:
            try:
                upd = r.json()
                if upd.get("updated") != len(post_body):
                    failures.append(
                        f"POST /settings (expected updated={len(post_body)}, got {upd!r})"
                    )
            except json.JSONDecodeError:
                failures.append("POST /settings (invalid JSON)")

        # GET /settings again + verify
        r = client.get("/settings")
        _print_response("GET /settings (after POST)", r)
        if r.status_code != 200:
            failures.append("GET /settings (after POST)")
        else:
            try:
                settings: dict[str, Any] = r.json()
                if not isinstance(settings, dict):
                    failures.append("GET /settings (after POST): not a dict")
                else:
                    for key, expected in post_body.items():
                        if settings.get(key) != expected:
                            failures.append(
                                f"GET /settings verify: key {key!r} expected {expected!r}, got {settings.get(key)!r}"
                            )
            except json.JSONDecodeError:
                failures.append("GET /settings (after POST) (invalid JSON)")

    print()
    if failures:
        print("FAILED endpoints / checks:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("ALL ENDPOINTS OK")
    return 0


if __name__ == "__main__":
    print(f"JARVIS API base: {BASE}\n")
    try:
        sys.exit(main())
    except httpx.ConnectError as e:
        print(f"Cannot connect to {BASE}: {e}", file=sys.stderr)
        print("Start the server: python main_api.py", file=sys.stderr)
        sys.exit(2)
