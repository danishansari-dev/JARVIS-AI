from tools.registry import ToolRegistry
from tools.filesystem import register_filesystem_tools
from tools.apps import register_app_tools
from tools.weather import register_weather_tools
from tools.system_control import register_system_tools
from tools.reminder import register_reminder_tools
from tools.screenshot import register_screenshot_tools

def build_registry(tts_engine=None) -> ToolRegistry:
    registry = ToolRegistry()
    register_filesystem_tools(registry)
    register_app_tools(registry)
    register_weather_tools(registry)
    register_system_tools(registry)
    register_screenshot_tools(registry)
    if tts_engine:
        register_reminder_tools(registry, tts_engine)
    return registry

