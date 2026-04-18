"""Hotkey-triggered microphone capture with WebRTC VAD and faster-whisper transcription."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
try:
    import webrtcvad
except ImportError:
    class webrtcvad:
        class Vad:
            def __init__(self, aggressiveness: int):
                pass
            def is_speech(self, pcm_bytes: bytes, sample_rate: int) -> bool:
                pcm = np.frombuffer(pcm_bytes, dtype=np.int16)
                return float(np.sqrt(np.mean(pcm.astype(np.float32)**2))) > 300.0

from faster_whisper import WhisperModel

from jarvis.config import Settings

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
CHANNELS = 1
DTYPE_SD = "int16"
FRAME_MS = 30
FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_MS / 1000)  # 480 @ 16kHz / 30ms
BYTES_PER_FRAME = FRAME_SAMPLES * 2
SILENCE_SECONDS = 1.2
MAX_RECORD_SECONDS = 45.0
WHISPER_MODEL = "base.en"


def _record_fixed_seconds(seconds: float, samplerate: int = SAMPLE_RATE) -> np.ndarray:
    """Blocking capture of a fixed duration (mono int16 -> float32 [-1, 1])."""
    frames = int(seconds * samplerate)
    recording = sd.rec(
        frames,
        samplerate=samplerate,
        channels=CHANNELS,
        dtype=DTYPE_SD,
        blocking=True,
    )
    sd.wait()
    mono = np.asarray(recording, dtype=np.int16).reshape(-1)
    return (mono.astype(np.float32) / 32768.0).clip(-1.0, 1.0)


def _record_until_silence_sync(
    vad_aggressiveness: int = 2,
    silence_seconds: float = SILENCE_SECONDS,
    max_seconds: float = MAX_RECORD_SECONDS,
) -> np.ndarray:
    """Record mono 16kHz PCM until `silence_seconds` of trailing silence after speech."""
    vad = webrtcvad.Vad(int(np.clip(vad_aggressiveness, 0, 3)))
    silence_frames = int(np.ceil(silence_seconds / (FRAME_MS / 1000.0)))
    max_frames = int(np.ceil(max_seconds / (FRAME_MS / 1000.0)))

    chunks: list[np.ndarray] = []
    speech_frames = 0
    silence_count = 0
    recording = False

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype=DTYPE_SD,
        blocksize=FRAME_SAMPLES,
    )
    stream.start()
    try:
        for _ in range(max_frames):
            data, overflowed = stream.read(FRAME_SAMPLES)
            if overflowed:
                logger.warning("Audio input overflow; consider increasing blocksize or CPU headroom")
            frame_i16 = np.asarray(data, dtype=np.int16).reshape(-1)
            if frame_i16.size != FRAME_SAMPLES:
                continue
            pcm_bytes = frame_i16.tobytes()
            if len(pcm_bytes) != BYTES_PER_FRAME:
                continue
            try:
                is_speech = vad.is_speech(pcm_bytes, SAMPLE_RATE)
            except ValueError:
                logger.exception("webrtcvad rejected frame layout")
                is_speech = False

            if is_speech:
                recording = True
                speech_frames += 1
                silence_count = 0
                chunks.append(frame_i16.copy())
                continue

            if not recording:
                continue

            chunks.append(frame_i16.copy())
            silence_count += 1
            if speech_frames >= 1 and silence_count >= silence_frames:
                break

        if not chunks:
            return np.zeros(1, dtype=np.float32)
        mono = np.concatenate(chunks, axis=0).reshape(-1)
        return (mono.astype(np.float32) / 32768.0).clip(-1.0, 1.0)
    finally:
        stream.stop()
        stream.close()


class SpeechToText:
    """faster-whisper STT with sounddevice capture and VAD end-of-utterance detection."""

    def __init__(
        self,
        settings: Settings,
        device: str = "cpu",
        compute_type: str = "int8",
    ) -> None:
        self._settings = settings
        self._model_name = WHISPER_MODEL
        self._device = device
        self._compute_type = compute_type
        self._model: WhisperModel | None = None
        self._lock = asyncio.Lock()
        self._executor = asyncio.ThreadPoolExecutor(max_workers=1, thread_name_prefix="whisper")

    async def _ensure_model(self) -> WhisperModel:
        async with self._lock:
            if self._model is None:
                logger.info("Loading faster-whisper model %s", self._model_name)

                def _load() -> WhisperModel:
                    return WhisperModel(
                        self._model_name,
                        device=self._device,
                        compute_type=self._compute_type,
                    )

                loop = asyncio.get_running_loop()
                self._model = await loop.run_in_executor(self._executor, _load)
            return self._model

    async def transcribe_audio(
        self,
        audio_f32: np.ndarray,
        *,
        language: str = "en",
    ) -> str:
        """Transcribe mono float32 PCM sampled at 16 kHz."""
        model = await self._ensure_model()

        def _run() -> str:
            if audio_f32.size < 8:
                return ""
            segments, _info = model.transcribe(
                audio_f32,
                language=language,
                without_timestamps=True,
            )
            parts = [s.text for s in segments]
            return " ".join(parts).strip()

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, _run)

    async def transcribe_after_hotkey(self, t_hotkey: float) -> str:
        """Record with VAD after a hotkey instant, then transcribe and log end-to-end latency."""

        def _capture() -> np.ndarray:
            return _record_until_silence_sync(
                vad_aggressiveness=self._settings.vad_aggressiveness,
                silence_seconds=self._settings.vad_silence_seconds,
            )

        loop = asyncio.get_running_loop()
        audio = await loop.run_in_executor(self._executor, _capture)
        text = await self.transcribe_audio(audio, language="en")
        latency_ms = (time.perf_counter() - t_hotkey) * 1000.0
        logger.info(
            "stt_latency_hotkey_to_transcribe_complete_ms=%.1f text_len=%d",
            latency_ms,
            len(text),
        )
        return text

    async def transcribe_file(self, audio_path: Path, language: str | None = None) -> str:
        """Transcribe audio from a file path (blocking decode in executor)."""
        path = Path(audio_path)

        def _decode() -> np.ndarray:
            data, sr = _load_wav_as_float32(path)
            if sr != SAMPLE_RATE:
                raise ValueError(f"Expected {SAMPLE_RATE} Hz mono WAV, got {sr}")
            return data

        loop = asyncio.get_running_loop()
        audio = await loop.run_in_executor(self._executor, _decode)
        return await self.transcribe_audio(audio, language=language or "en")

    async def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


def _load_wav_as_float32(path: Path) -> tuple[np.ndarray, int]:
    import wave

    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        ch = wf.getnchannels()
        sw = wf.getsampwidth()
        n = wf.getnframes()
        raw = wf.readframes(n)
    if sw != 2:
        raise ValueError("Only 16-bit WAV is supported")
    pcm = np.frombuffer(raw, dtype=np.int16)
    if ch > 1:
        pcm = pcm.reshape(-1, ch)[:, 0]
    return (pcm.astype(np.float32) / 32768.0).clip(-1.0, 1.0), sr


async def _cli_test() -> None:
    """Record 5 seconds, transcribe, speak back (requires working mic, speakers, and .env)."""
    import os

    os.environ.setdefault("ANTHROPIC_API_KEY", "local-voice-self-test")

    from jarvis.config import load_settings
    from jarvis.voice.tts import TextToSpeech

    settings = load_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

    stt = SpeechToText(settings)
    tts = TextToSpeech(settings)
    await tts.start()
    try:
        logger.info("Recording %.1f seconds…", 5.0)
        audio = await asyncio.to_thread(_record_fixed_seconds, 5.0)
        t0 = time.perf_counter()
        text = await stt.transcribe_audio(audio, language="en")
        logger.info(
            "Self-test transcribe_latency_ms=%.1f text=%s",
            (time.perf_counter() - t0) * 1000.0,
            text or "(empty)",
        )
        await tts.speak(text or "I did not catch that.")
    finally:
        await tts.stop()
        await stt.shutdown()


def main() -> None:
    asyncio.run(_cli_test())


if __name__ == "__main__":
    main()
