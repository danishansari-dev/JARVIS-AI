"""ElevenLabs streaming TTS with Piper fallback, queued sentence playback, and monthly usage tracking."""

from __future__ import annotations

import asyncio
import io
import logging
import re
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import httpx
import numpy as np
import sounddevice as sd

from jarvis.config import Settings
from jarvis.memory.db import log_elevenlabs_usage

logger = logging.getLogger(__name__)

WARN_CHARS_SOFT = 8_000
WARN_CHARS_HARD = 10_000

_ELEVENLABS_PCM_RATES: dict[str, int] = {
    "pcm_8000": 8000,
    "pcm_16000": 16_000,
    "pcm_22050": 22_050,
    "pcm_24000": 24_000,
    "pcm_44100": 44_100,
    "pcm_48000": 48_000,
}


def _split_for_tts(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?…])\s+|\n+", text)
    chunks = [p.strip() for p in parts if p.strip()]
    return chunks if chunks else [text]


def _is_acknowledgement(text: str) -> bool:
    """Route short confirmations to Piper to conserve ElevenLabs quota."""
    key = " ".join(re.findall(r"[A-Za-z']+", text.strip().lower()))
    return key in {"done", "opening", "got it"}


def _maybe_warn_elevenlabs(prev: int, new_total: int) -> None:
    if prev < WARN_CHARS_SOFT <= new_total:
        logger.warning(
            "ElevenLabs monthly characters crossed %d (now %d / soft cap %d)",
            WARN_CHARS_SOFT,
            new_total,
            WARN_CHARS_SOFT,
        )
    if prev < WARN_CHARS_HARD <= new_total:
        logger.warning(
            "ElevenLabs monthly characters crossed %d (now %d / hard cap %d)",
            WARN_CHARS_HARD,
            new_total,
            WARN_CHARS_HARD,
        )
    if new_total >= WARN_CHARS_HARD:
        logger.warning(
            "ElevenLabs monthly usage at or above %d characters (%d). Consider switching to Piper.",
            WARN_CHARS_HARD,
            new_total,
        )


class TextToSpeech:
    """Sentence-queue TTS: ElevenLabs HTTP streaming primary, Piper offline fallback."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._http: httpx.AsyncClient | None = None

    async def start(self) -> None:
        self._http = httpx.AsyncClient(timeout=120.0)

    async def stop(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def speak(self, text: str) -> None:
        if not text.strip():
            return
        if self._http is None:
            raise RuntimeError("TextToSpeech.start() must be awaited before speak()")
        sentences = _split_for_tts(text)
        if not sentences:
            return
        queue: asyncio.Queue[tuple[bytes, int] | None] = asyncio.Queue(maxsize=4)

        async def producer() -> None:
            try:
                for sentence in sentences:
                    try:
                        pcm, sr = await self._synthesize_sentence(sentence)
                    except Exception:
                        logger.exception("Sentence synthesis failed (%s)", sentence[:80])
                        continue
                    await queue.put((pcm, sr))
            finally:
                await queue.put(None)

        async def consumer() -> None:
            while True:
                item = await queue.get()
                if item is None:
                    break
                pcm, sr = item
                await asyncio.to_thread(self._play_pcm_blocking, pcm, sr)

        await asyncio.gather(producer(), consumer())

    async def _synthesize_sentence(self, sentence: str) -> tuple[bytes, int]:
        if _is_acknowledgement(sentence):
            return await asyncio.to_thread(self._piper_to_pcm, sentence)
        key = self._settings.elevenlabs_api_key.strip()
        voice = self._settings.elevenlabs_voice_id.strip()
        if not key or not voice:
            return await asyncio.to_thread(self._piper_to_pcm, sentence)
        try:
            pcm = await self._elevenlabs_sentence_pcm(sentence)
            prev, new_total = await asyncio.to_thread(
                log_elevenlabs_usage,
                self._settings.profile_db_path,
                len(sentence),
            )
            _maybe_warn_elevenlabs(prev, new_total)
            rate = _ELEVENLABS_PCM_RATES.get(
                self._settings.elevenlabs_output_format,
                22_050,
            )
            return pcm, rate
        except Exception as exc:
            msg = str(exc).lower()
            if "429" in msg or "quota" in msg or "402" in msg:
                logger.warning("ElevenLabs unavailable (%s); falling back to Piper", exc)
            else:
                logger.warning("ElevenLabs request failed (%s); falling back to Piper", exc)
            return await asyncio.to_thread(self._piper_to_pcm, sentence)

    async def _elevenlabs_sentence_pcm(self, sentence: str) -> bytes:
        assert self._http is not None
        voice_id = self._settings.elevenlabs_voice_id
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
        params = {
            "output_format": self._settings.elevenlabs_output_format,
        }
        headers = {
            "xi-api-key": self._settings.elevenlabs_api_key,
            "Accept": "application/octet-stream",
        }
        payload = {
            "text": sentence,
            "model_id": self._settings.elevenlabs_model_id,
        }
        async with self._http.stream(
            "POST",
            url,
            params=params,
            json=payload,
            headers=headers,
        ) as resp:
            if resp.status_code in (401, 402, 403, 429):
                detail = (await resp.aread())[:400]
                raise RuntimeError(f"elevenlabs_http_{resp.status_code}:{detail!r}")
            resp.raise_for_status()
            buffer = bytearray()
            async for chunk in resp.aiter_bytes():
                buffer.extend(chunk)
        return bytes(buffer)

    def _piper_to_pcm(self, text: str) -> tuple[bytes, int]:
        model = self._settings.piper_model_path
        exe = self._settings.piper_executable
        if model is None or not Path(model).is_file():
            raise RuntimeError("Piper model missing; configure PIPER_MODEL_PATH for offline TTS")
        piper_bin = Path(exe) if Path(exe).is_file() else Path(shutil.which(str(exe)) or exe)
        if not piper_bin.is_file() and shutil.which(str(exe)) is None:
            raise FileNotFoundError(str(exe))

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            out_path = Path(tmp.name)

        try:
            completed = subprocess.run(
                [
                    str(piper_bin),
                    "--model",
                    str(model),
                    "--output_file",
                    str(out_path),
                ],
                input=text.encode("utf-8"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=False,
            )
            if completed.returncode != 0:
                err = (completed.stderr or b"").decode("utf-8", errors="replace")
                raise RuntimeError(err)
            wav_bytes = out_path.read_bytes()
        finally:
            try:
                out_path.unlink(missing_ok=True)
            except OSError:
                logger.debug("Could not remove Piper temp wav", exc_info=True)

        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            if wf.getsampwidth() != 2:
                raise ValueError("Piper must output 16-bit WAV")
            sr = wf.getframerate()
            ch = wf.getnchannels()
            frames = wf.readframes(wf.getnframes())
        pcm = np.frombuffer(frames, dtype=np.int16)
        if ch > 1:
            pcm = pcm.reshape(-1, ch)[:, 0]
        return pcm.tobytes(), int(sr)

    def _play_pcm_blocking(self, pcm: bytes, sample_rate: int) -> None:
        if not pcm:
            return
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        sd.play(audio, sample_rate, blocking=True)
