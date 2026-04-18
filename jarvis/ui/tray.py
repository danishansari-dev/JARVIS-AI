"""System tray icon and menu for the JARVIS daemon."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable

import pystray
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


def _build_icon_image() -> Image.Image:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, 56, 56), fill=(30, 144, 255, 255), outline=(10, 80, 160, 255), width=3)
    return image


def build_tray_icon(
    loop: asyncio.AbstractEventLoop,
    on_quit: Callable[[], None],
    on_status: Callable[[], str] | None = None,
) -> pystray.Icon:
    """Create a pystray icon; call `icon.run()` from a dedicated thread."""

    image = _build_icon_image()

    def status_action(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        if on_status is None:
            logger.info("Status requested")
            return
        text = on_status()

        def _notify() -> None:
            logger.info("JARVIS status: %s", text)

        loop.call_soon_threadsafe(_notify)

    def quit_action(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        loop.call_soon_threadsafe(on_quit)
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Status", status_action, default=True),
        pystray.MenuItem("Exit", quit_action),
    )
    return pystray.Icon("jarvis", image, "JARVIS", menu)
