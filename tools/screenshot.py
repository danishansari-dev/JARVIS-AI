from pathlib import Path
from datetime import datetime
import tempfile
from pydantic import BaseModel
from tools.registry import ToolRegistry

try:
    import pyautogui
    import PIL
except ImportError:
    pass

class ScreenshotInput(BaseModel):
    save_to_desktop: bool = True

def _take_screenshot(data: ScreenshotInput) -> str:
    try:
        screenshot = pyautogui.screenshot()
        if data.save_to_desktop:
            path = Path.home() / "Desktop" / f"screenshot_{datetime.now().strftime('%H%M%S')}.png"
        else:
            path = Path(tempfile.mktemp(suffix=".png"))
            
        screenshot.save(str(path))
        return f"Screenshot saved: {path.name}"
    except Exception as e:
        return f"Failed to take screenshot: {e}"

def register_screenshot_tools(registry: ToolRegistry) -> None:
    registry.register(
        name="take_screenshot",
        description="Take a screenshot and save it to the desktop or a temp folder.",
        input_schema=ScreenshotInput,
        handler=_take_screenshot,
    )
