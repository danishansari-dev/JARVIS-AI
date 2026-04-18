import threading
from pydantic import BaseModel
from tools.registry import ToolRegistry

active_reminders = []

class ReminderInput(BaseModel):
    message: str
    minutes: int

def register_reminder_tools(registry: ToolRegistry, tts_engine) -> None:
    def _set_reminder(data: ReminderInput) -> str:
        def reminder_fire(message, engine):
            engine.speak_sync(f"Reminder: {message}")
            
        timer = threading.Timer(
            data.minutes * 60,
            reminder_fire,
            args=[data.message, tts_engine]
        )
        timer.start()
        active_reminders.append({"message": data.message, "minutes": data.minutes, "timer": timer})
        return f"Reminder set for {data.minutes} minute{'s' if data.minutes != 1 else ''}: {data.message}"

    registry.register(
        name="set_reminder",
        description="Set a background timer to speak a reminder message after a given number of minutes.",
        input_schema=ReminderInput,
        handler=_set_reminder,
    )
