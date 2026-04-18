import subprocess
import psutil
from typing import Optional
from pydantic import BaseModel
from tools.registry import ToolRegistry

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    import screen_brightness_control as sbc
    import pythoncom
except ImportError:
    pass

class SystemControlInput(BaseModel):
    action: str
    value: Optional[int] = None

def _system_control(data: SystemControlInput) -> str:
    action = data.action
    
    if action == "set_volume":
        if data.value is None:
            return "Volume value required."
        try:
            pythoncom.CoInitialize()
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            vol_scalar = max(0.0, min(1.0, data.value / 100.0))
            volume.SetMasterVolumeLevelScalar(vol_scalar, None)
            return f"Volume set to {data.value}%"
        except Exception as e:
            return f"Failed to set volume: {e}"
            
    elif action == "get_volume":
        try:
            pythoncom.CoInitialize()
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            vol = round(volume.GetMasterVolumeLevelScalar() * 100)
            return f"{vol}%"
        except Exception as e:
            return f"Failed to get volume: {e}"
            
    elif action == "get_battery":
        batt = psutil.sensors_battery()
        if not batt:
            return "No battery detected."
        status = 'charging' if batt.power_plugged else 'discharging'
        return f"Battery: {round(batt.percent)}% {status}"
        
    elif action == "lock_screen":
        try:
            subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"])
            return "Screen locked."
        except Exception as e:
            return f"Failed to lock screen: {e}"
            
    elif action == "get_system_info":
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")
        
        mem_used = round(mem.used / (1024**3), 1)
        mem_total = round(mem.total / (1024**3), 1)
        disk_free = round(disk.free / (1024**3), 1)
        
        return f"CPU: {cpu}% | RAM: {mem_used}GB/{mem_total}GB | C: Free {disk_free}GB"
    
    return f"Unknown action: {action}"

def register_system_tools(registry: ToolRegistry) -> None:
    registry.register(
        name="system_control",
        description="Control system volume, check battery, lock screen, or get system info.",
        input_schema=SystemControlInput,
        handler=_system_control,
    )
