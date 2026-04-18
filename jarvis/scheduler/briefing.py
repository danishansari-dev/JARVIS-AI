"""Morning briefing: calendar, weather, news; TTS + SQLite."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Any

import feedparser
import httpx
from zoneinfo import ZoneInfo

from jarvis.memory.db import log_briefing
from jarvis.scheduler.deps import get_scheduler_deps
from jarvis.tools.calendar_tool import fetch_today_calendar_spoken_summary

logger = logging.getLogger(__name__)

OPEN_METEO_GEO = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
BBC_NEWS_RSS = "https://feeds.bbci.co.uk/news/rss.xml"


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w']+\b", text))


def _truncate_to_max_words(text: str, max_words: int) -> str:
    parts = text.split()
    if len(parts) <= max_words:
        return text.strip()
    return " ".join(parts[:max_words]).rstrip(",.;:") + "."


async def _geocode_city(city: str) -> tuple[float, float] | None:
    if not city.strip():
        return None
    params = {"name": city.strip(), "count": 1, "language": "en", "format": "json"}
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(OPEN_METEO_GEO, params=params)
        r.raise_for_status()
        data = r.json()
    results = data.get("results") or []
    if not results:
        return None
    lat = float(results[0]["latitude"])
    lon = float(results[0]["longitude"])
    return lat, lon


async def _fetch_weather_brief(lat: float, lon: float) -> str:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,weather_code,wind_speed_10m",
        "timezone": "auto",
        "wind_speed_unit": "kmh",
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(OPEN_METEO_FORECAST, params=params)
        r.raise_for_status()
        j: dict[str, Any] = r.json()
    cur = j.get("current") or {}
    temp = cur.get("temperature_2m")
    wind = cur.get("wind_speed_10m")
    if temp is None:
        return "Weather data was unavailable."
    w = f"Currently about {round(float(temp))} degrees Celsius"
    if wind is not None:
        w += f", wind around {round(float(wind))} kilometers per hour"
    w += "."
    return w


async def _fetch_headlines(max_items: int = 3) -> list[str]:
    async with httpx.AsyncClient(timeout=25.0) as client:
        r = await client.get(BBC_NEWS_RSS)
        r.raise_for_status()
        raw = r.content
    parsed = feedparser.parse(raw)
    titles: list[str] = []
    for entry in parsed.entries[:max_items]:
        t = (entry.get("title") or "").strip()
        if t:
            titles.append(t)
    return titles


async def morning_briefing() -> str:
    """Build today's spoken briefing, speak via TTS, persist for replay."""
    deps = get_scheduler_deps()
    settings = deps.settings
    profile = deps.profile
    tts = deps.tts

    tz_name = (await profile.get_fact("timezone")) or "UTC"
    city = (await profile.get_fact("user_city")) or ""

    try:
        tz = ZoneInfo(tz_name.strip() or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    today_local = datetime.now(tz).strftime("%Y-%m-%d")

    cal_part = await fetch_today_calendar_spoken_summary(settings, tz_name)

    weather_part = "Weather could not be resolved for your city."
    coords = await _geocode_city(city)
    if coords:
        try:
            weather_part = await _fetch_weather_brief(coords[0], coords[1])
        except Exception:
            logger.exception("Open-Meteo fetch failed")

    headlines: list[str] = []
    try:
        headlines = await _fetch_headlines(3)
    except Exception:
        logger.exception("BBC RSS fetch failed")

    news_part = (
        "Top headlines: " + "; ".join(headlines) + "."
        if headlines
        else "Headlines were unavailable."
    )

    greeting = "Good morning. Here is your briefing for today."
    body = f"{greeting} {cal_part} {weather_part} {news_part}"
    body = re.sub(r"\s+", " ", body).strip()
    if _word_count(body) > 200:
        body = _truncate_to_max_words(body, 200)

    await asyncio.to_thread(
        log_briefing,
        settings.profile_db_path,
        today_local,
        weather_part,
        cal_part,
        headlines,
    )

    try:
        await profile.save_daily_briefing(today_local, body)
    except Exception:
        logger.exception("Saving daily briefing to SQLite failed")

    try:
        await tts.speak(body)
    except Exception:
        logger.exception("TTS for morning briefing failed")

    return body
