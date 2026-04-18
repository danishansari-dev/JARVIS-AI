"""Google Calendar operations behind a single validated tool."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal, Union

from googleapiclient.discovery import build
from pydantic import BaseModel, Field, RootModel

from jarvis.config import Settings
from jarvis.tools.google_credentials import load_google_credentials
from jarvis.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class CalendarListArgs(BaseModel):
    action: Literal["list_events"] = "list_events"
    max_results: int = Field(default=10, ge=1, le=50)
    days_ahead: int = Field(default=1, ge=0, le=30, description="Include events until now + this many days")


class CalendarCreateArgs(BaseModel):
    action: Literal["create_event"] = "create_event"
    summary: str = Field(description="Event title")
    start_iso: str = Field(description="Start time in ISO-8601 format")
    end_iso: str = Field(description="End time in ISO-8601 format")
    description: str | None = Field(default=None)


CalendarUnion = Annotated[
    Union[CalendarListArgs, CalendarCreateArgs],
    Field(discriminator="action"),
]


class CalendarInvocation(RootModel[CalendarUnion]):
    pass


def _calendar_service(settings: Settings) -> Any:
    creds = load_google_credentials(settings)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


async def fetch_calendar_summary(
    settings: Settings,
    *,
    max_results: int = 6,
    days_ahead: int = 1,
) -> str:
    """Return a short human-readable agenda string for briefings."""
    if settings.google_credentials_path is None:
        return ""
    try:
        events = await _list_events(
            settings,
            CalendarListArgs(max_results=max_results, days_ahead=days_ahead),
        )
    except Exception:
        logger.exception("Calendar summary failed")
        return "Calendar: unavailable."
    if not events:
        return "Calendar: no upcoming events in the selected window."
    lines = ["Calendar:"]
    for ev in events:
        lines.append(f"- {ev.get('start')}: {ev.get('summary')}")
    return "\n".join(lines)


async def _list_events(settings: Settings, args: CalendarListArgs) -> list[dict[str, Any]]:
    def _run() -> list[dict[str, Any]]:
        service = _calendar_service(settings)
        now = datetime.now(timezone.utc).isoformat()
        until = (datetime.now(timezone.utc) + timedelta(days=args.days_ahead)).isoformat()
        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now,
                timeMax=until,
                maxResults=args.max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        items = events_result.get("items", [])
        out: list[dict[str, Any]] = []
        for ev in items:
            start = ev["start"].get("dateTime", ev["start"].get("date"))
            out.append({"summary": ev.get("summary"), "start": start, "id": ev.get("id")})
        return out

    return await asyncio.to_thread(_run)


async def list_calendar_events_between(
    settings: Settings,
    time_min_iso: str,
    time_max_iso: str,
    *,
    max_results: int = 50,
) -> list[dict[str, Any]]:
    """List primary-calendar events with start in ``[time_min_iso, time_max_iso]`` (RFC3339)."""
    if settings.google_credentials_path is None:
        return []

    def _run() -> list[dict[str, Any]]:
        service = _calendar_service(settings)
        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=time_min_iso,
                timeMax=time_max_iso,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        items = events_result.get("items", [])
        out: list[dict[str, Any]] = []
        for ev in items:
            start = ev["start"].get("dateTime", ev["start"].get("date"))
            out.append(
                {
                    "id": ev.get("id", ""),
                    "summary": ev.get("summary", "(no title)"),
                    "start": start,
                }
            )
        return out

    return await asyncio.to_thread(_run)


async def fetch_today_calendar_spoken_summary(settings: Settings, tz_name: str) -> str:
    """Human-readable list of today's events in the user's timezone (for briefings)."""
    if settings.google_credentials_path is None:
        return "Calendar is not connected."
    from zoneinfo import ZoneInfo

    try:
        tz = ZoneInfo(tz_name.strip() or "UTC")
    except Exception:
        logger.warning("Invalid timezone %r; using UTC", tz_name)
        tz = ZoneInfo("UTC")
    now_local = datetime.now(tz)
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    time_min = start_local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    time_max = end_local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        events = await list_calendar_events_between(settings, time_min, time_max, max_results=50)
    except Exception:
        logger.exception("Today's calendar fetch failed")
        return "Calendar could not be read today."
    if not events:
        return "Nothing on your calendar for today."
    parts = [f"You have {len(events)} event(s) today."]
    for ev in events[:12]:
        parts.append(f"{ev.get('start')}: {ev.get('summary')}.")
    return " ".join(parts)


async def _create_event(settings: Settings, args: CalendarCreateArgs) -> str:
    def _run() -> str:
        service = _calendar_service(settings)
        body = {
            "summary": args.summary,
            "description": args.description or "",
            "start": {"dateTime": args.start_iso},
            "end": {"dateTime": args.end_iso},
        }
        created = service.events().insert(calendarId="primary", body=body).execute()
        return str(created.get("htmlLink", created.get("id", "ok")))

    return await asyncio.to_thread(_run)


def build_calendar_handler(settings: Settings):
    async def _handler(inv: CalendarInvocation) -> list[dict[str, Any]] | str:
        inner = inv.root
        if isinstance(inner, CalendarListArgs):
            return await _list_events(settings, inner)
        if isinstance(inner, CalendarCreateArgs):
            return await _create_event(settings, inner)
        raise TypeError("Unsupported calendar payload")

    return _handler


def register_calendar_tool(registry: ToolRegistry, settings: Settings) -> None:
    if settings.google_credentials_path is None:
        logger.info("Skipping calendar tool: GOOGLE_CREDENTIALS_PATH not set")
        return
    registry.register(
        "calendar",
        "List upcoming Google Calendar events or create a new event.",
        CalendarInvocation,
        build_calendar_handler(settings),
    )
