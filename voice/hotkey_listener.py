import logging
import threading
try:
    from pynput import keyboard
except ImportError:
    pass

class HotkeyListener:
    def __init__(self, on_activate: callable):
        self.on_activate = on_activate  # called when hotkey pressed
        
        try:
            self.hotkey = keyboard.HotKey(
                keyboard.HotKey.parse("<ctrl>+<space>"),
                self._on_hotkey
            )
        except NameError:
            self.hotkey = None
            
        self._listener = None

    def _on_hotkey(self):
        threading.Thread(target=self.on_activate, daemon=True).start()

    def start(self):
        if not self.hotkey:
            logging.error("pynput not installed. Hotkey listener will not start.")
            return

        self._listener = keyboard.Listener(
            on_press=self.hotkey.press,
            on_release=self.hotkey.release
        )
        self._listener.start()
        logging.info("Hotkey listener started: Ctrl+Space to activate JARVIS")

    def stop(self):
        if self._listener:
            self._listener.stop()
