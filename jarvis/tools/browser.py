"""Playwright-based browser automation (async) behind one registered tool."""

from __future__ import annotations

import logging
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, HttpUrl, RootModel
from playwright.async_api import Browser, Page, async_playwright

from jarvis.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class BrowserSearchArgs(BaseModel):
    action: Literal["search"] = "search"
    query: str = Field(description="Search query; opens DuckDuckGo results")


class BrowserSummarizeArgs(BaseModel):
    action: Literal["summarize_page"] = "summarize_page"
    url: HttpUrl = Field(description="Page URL to fetch and extract readable text from")


class BrowserFillArgs(BaseModel):
    action: Literal["fill_form"] = "fill_form"
    url: HttpUrl = Field(description="Page containing the form")
    selector: str = Field(description="CSS selector for the input field")
    value: str = Field(description="Text to type into the field")


BrowserUnion = Annotated[
    Union[BrowserSearchArgs, BrowserSummarizeArgs, BrowserFillArgs],
    Field(discriminator="action"),
]


class BrowserInvocation(RootModel[BrowserUnion]):
    pass


class BrowserSession:
    """Owns a Playwright browser instance for reuse across tool calls."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser: Browser | None = None

    async def _ensure_browser(self) -> Browser:
        if self._browser is not None:
            return self._browser
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        return self._browser

    async def new_page(self) -> Page:
        browser = await self._ensure_browser()
        return await browser.new_page()

    async def shutdown(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None


def _visible_text_from_html(html: str) -> str:
    from html.parser import HTMLParser

    class _TextExtractor(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.parts: list[str] = []

        def handle_data(self, data: str) -> None:
            text = data.strip()
            if text:
                self.parts.append(text)

    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        logger.exception("HTML parse failed; returning raw slice")
        return html[:8000]
    return "\n".join(parser.parts)[:8000]


async def _browser_search(session: BrowserSession, args: BrowserSearchArgs) -> str:
    page = await session.new_page()
    try:
        q = args.query.replace(" ", "+")
        await page.goto(f"https://duckduckgo.com/?q={q}", wait_until="domcontentloaded")
        title = await page.title()
        snippet = await page.inner_text("body")
        return f"{title}\n{snippet[:4000]}"
    finally:
        await page.close()


async def _browser_summarize(session: BrowserSession, args: BrowserSummarizeArgs) -> str:
    page = await session.new_page()
    try:
        await page.goto(str(args.url), wait_until="domcontentloaded")
        html = await page.content()
        text = _visible_text_from_html(html)
        return text[:6000] or "(empty page)"
    finally:
        await page.close()


async def _browser_fill(session: BrowserSession, args: BrowserFillArgs) -> str:
    page = await session.new_page()
    try:
        await page.goto(str(args.url), wait_until="domcontentloaded")
        await page.fill(args.selector, args.value)
        return "filled"
    finally:
        await page.close()


def build_browser_tool_handler(session: BrowserSession):
    async def _handler(inv: BrowserInvocation) -> str:
        inner = inv.root
        if isinstance(inner, BrowserSearchArgs):
            return await _browser_search(session, inner)
        if isinstance(inner, BrowserSummarizeArgs):
            return await _browser_summarize(session, inner)
        if isinstance(inner, BrowserFillArgs):
            return await _browser_fill(session, inner)
        raise TypeError("Unsupported browser payload")

    return _handler


def register_browser_tool(registry: ToolRegistry, session: BrowserSession) -> None:
    registry.register(
        "browser",
        "Search the web, summarize a page's text, or fill a form field via Playwright.",
        BrowserInvocation,
        build_browser_tool_handler(session),
    )
