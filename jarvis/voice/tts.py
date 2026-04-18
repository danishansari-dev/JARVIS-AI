"""Hybrid TTS engine: Piper for short prompts, ElevenLabs for longer prompts."""

from __future__ import annotations

import io
import logging
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pygame
import requests

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _SpeakRequest:
    text: str
    force_local: bool
    done: threading.Event | None


class TTSEngine:
    """Route TTS between local Piper and ElevenLabs streaming."""

    def __init__(self) -> None:
        if load_dotenv is not None:
            load_dotenv()
        self.api_key: str = os.getenv("ELEVENLABS_API_KEY", "").strip()
        self.voice_id: str = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
        self.model_id: str = os.getenv("ELEVENLABS_MODEL_ID", "eleven_turbo_v2_5").strip()
        self.output_format: str = os.getenv("ELEVENLABS_OUTPUT_FORMAT", "pcm_22050").strip()
        self.piper_model_path: str = os.getenv("PIPER_MODEL_PATH", "").strip()
        self._queue: queue.Queue[_SpeakRequest | None] = queue.Queue()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True, name="tts-worker")
        self._running = True

        pygame.mixer.init()
        self._worker.start()

    def speak(self, text: str, force_local: bool = False) -> None:
        """Queue speech synthesis and return immediately."""
        cleaned = text.strip()
        if not cleaned:
            return
        self._queue.put(_SpeakRequest(text=cleaned, force_local=force_local, done=None))

    def speak_sync(self, text: str) -> None:
        """Queue synthesis and block until playback finishes."""
        cleaned = text.strip()
        if not cleaned:
            return
        done = threading.Event()
        self._queue.put(_SpeakRequest(text=cleaned, force_local=False, done=done))
        done.wait()

    def _worker_loop(self) -> None:
        while self._running:
            item = self._queue.get()
            if item is None:
                break
            try:
                self._speak_impl(item.text, item.force_local)
            except Exception:
                logger.exception("TTS playback failed")
            finally:
                if item.done is not None:
                    item.done.set()

    def _speak_impl(self, text: str, force_local: bool) -> None:
        words = len(text.split())
        use_local = force_local or words <= 6
        if use_local:
            logger.info("Using Piper TTS (%d words)", words)
            audio_bytes = self._synthesize_with_piper(text)
            suffix = ".wav"
        else:
            logger.info("Using ElevenLabs streaming TTS (%d words)", words)
            try:
                audio_bytes = self._synthesize_with_elevenlabs(text)
                self._track_usage(len(text))
                suffix = ".mp3"
            except Exception as e:
                logger.warning("ElevenLabs TTS failed: %s. Falling back to Piper.", e)
                audio_bytes = self._synthesize_with_piper(text)
                suffix = ".wav"
        self._play_audio_bytes(audio_bytes, suffix=suffix)

    def _synthesize_with_elevenlabs(self, text: str) -> bytes:
        if not self.api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is required for cloud TTS")
        if not self.voice_id:
            raise RuntimeError("ELEVENLABS_VOICE_ID is required for cloud TTS")
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": self.model_id,
            "output_format": self.output_format,
        }
        response = requests.post(url, headers=headers, json=payload, timeout=60, stream=True)
        response.raise_for_status()
        output = io.BytesIO()
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                output.write(chunk)
        return output.getvalue()

    def _synthesize_with_piper(self, text: str) -> bytes:
        model_path = Path(self.piper_model_path)
        if not model_path.is_file():
            raise RuntimeError("PIPER_MODEL_PATH must point to a valid .onnx model file")
        piper_bin = shutil.which("piper") or shutil.which("piper.exe")
        if piper_bin is None:
            raise RuntimeError("Piper executable not found on PATH")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            out_path = Path(tmp.name)
        try:
            proc = subprocess.run(
                [piper_bin, "--model", str(model_path), "--output_file", str(out_path)],
                input=text.encode("utf-8"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=False,
            )
            if proc.returncode != 0:
                stderr_text = proc.stderr.decode("utf-8", errors="replace")
                raise RuntimeError(f"Piper synthesis failed: {stderr_text}")
            return out_path.read_bytes()
        finally:
            out_path.unlink(missing_ok=True)

    def _play_audio_bytes(self, audio_bytes: bytes, suffix: str) -> None:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            temp_path = Path(tmp.name)
            temp_path.write_bytes(audio_bytes)
        try:
            pygame.mixer.music.load(str(temp_path))
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.05)
        finally:
            # On Windows the mixer can keep a handle open briefly after playback.
            pygame.mixer.music.stop()
            unload = getattr(pygame.mixer.music, "unload", None)
            if callable(unload):
                unload()
            for _ in range(10):
                try:
                    temp_path.unlink(missing_ok=True)
                    break
                except PermissionError:
                    time.sleep(0.05)

    def _track_usage(self, chars: int) -> None:
        from main_api import log_elevenlabs_usage

        log_elevenlabs_usage(chars)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    tts = TTSEngine()
    tts.speak_sync("JARVIS online. All systems nominal.")
