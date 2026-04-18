"""Application configuration loaded from environment via pydantic-settings."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration for JARVIS."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    anthropic_api_key: str = Field(..., description="Anthropic API key for Claude")
    claude_model_fast: str = Field(
        default="claude-3-5-haiku-20241022",
        description="Fast model for routine turns",
    )
    claude_model_smart: str = Field(
        default="claude-sonnet-4-20250514",
        description="Capable model for complex tasks",
    )

    # Speech
    elevenlabs_api_key: str = Field(default="", description="ElevenLabs API key")
    elevenlabs_voice_id: str = Field(default="", description="Default ElevenLabs voice id")
    elevenlabs_output_format: str = Field(
        default="pcm_22050",
        description="PCM output format for streamed ElevenLabs audio (see ElevenLabs API docs)",
    )
    elevenlabs_model_id: str = Field(
        default="eleven_turbo_v2_5",
        description="ElevenLabs model id for speech synthesis",
    )
    piper_executable: Path = Field(
        default=Path("piper"),
        description="Path to piper TTS binary",
    )
    piper_model_path: Path | None = Field(
        default=None,
        description="Path to piper .onnx voice model",
    )
    whisper_model_size: str = Field(
        default="base.en",
        description="faster-whisper model id (voice pipeline pins base.en)",
    )
    vad_aggressiveness: int = Field(
        default=2,
        ge=0,
        le=3,
        description="webrtcvad aggressiveness (0=mild, 3=harsh)",
    )
    vad_silence_seconds: float = Field(
        default=1.2,
        gt=0.0,
        le=10.0,
        description="Stop recording after this many seconds of trailing silence",
    )

    # Paths
    data_dir: Path = Field(default=Path.home() / ".jarvis")
    chroma_path: Path | None = Field(
        default=None,
        description="Chroma persistence directory; defaults under data_dir",
    )
    sqlite_path: Path | None = Field(
        default=None,
        description="SQLite profile DB path; defaults to data_dir/jarvis.db",
    )
    google_credentials_path: Path | None = Field(
        default=None,
        description="OAuth client secrets JSON for Google APIs",
    )
    google_token_path: Path | None = Field(
        default=None,
        description="Stored OAuth token path",
    )

    # Briefing / weather
    open_meteo_user_agent: str = Field(
        default="JARVIS-local-assistant/0.1",
        description="User-Agent for Open-Meteo (no key required)",
    )
    briefing_news_rss_urls: str = Field(
        default="https://feeds.bbci.co.uk/news/rss.xml",
        description="Comma-separated list of RSS feed URLs",
    )

    # App launcher (merged with built-in friendly names → executable)
    app_launch_aliases_json: str = Field(
        default="",
        description='Optional JSON object, e.g. {"my ide":"devenv"} merged with default app aliases',
    )

    # Logging
    log_level: str = Field(default="INFO")

    @property
    def chroma_dir(self) -> Path:
        base = self.chroma_path or (self.data_dir / "chroma")
        base.mkdir(parents=True, exist_ok=True)
        return base

    @property
    def profile_db_path(self) -> Path:
        p = self.sqlite_path or (self.data_dir / "jarvis.db")
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def google_token_file(self) -> Path:
        return self.google_token_path or (self.data_dir / "google_token.json")

    @property
    def news_feeds(self) -> list[str]:
        return [u.strip() for u in self.briefing_news_rss_urls.split(",") if u.strip()]


def load_settings() -> Settings:
    """Load settings from environment and optional .env file."""
    return Settings()
