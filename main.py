from agent import JarvisAgent
from voice.stt import listen_and_transcribe
from voice.hotkey_listener import HotkeyListener
import threading, logging

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )

    agent = JarvisAgent()
    try:
        agent.tts.speak("JARVIS online. Ready.", force_local=True)
    except TypeError:
        agent.tts.speak("JARVIS online. Ready.")
        
    print("JARVIS online. Press Ctrl+Space to speak, or type below.")
    print("Type 'exit' to quit.\n")

    is_listening = threading.Event()

    def on_hotkey_pressed():
        if is_listening.is_set():
            return  # already listening, ignore
        is_listening.set()
        print("\n[Listening...]")
        try:
            user_input = listen_and_transcribe()
            if user_input and user_input.strip():
                print(f"You: {user_input}")
                response = agent.process(user_input)
                print(f"JARVIS: {response}\n")
        except Exception as e:
            logging.error(f"Voice pipeline error: {e}")
        finally:
            is_listening.clear()

    # Start hotkey listener in background
    hotkey = HotkeyListener(on_activate=on_hotkey_pressed)
    hotkey.start()

    # CLI fallback loop (always available)
    while True:
        try:
            user_input = input("You (type): ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit"):
                try:
                    agent.tts.speak("Shutting down.", force_local=True)
                except TypeError:
                    agent.tts.speak("Shutting down.")
                hotkey.stop()
                break
            response = agent.process(user_input)
            print(f"JARVIS: {response}\n")
        except KeyboardInterrupt:
            hotkey.stop()
            break

if __name__ == "__main__":
    main()
