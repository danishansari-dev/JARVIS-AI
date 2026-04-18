"""Shared Google OAuth credential loading for Calendar and Gmail tools."""

from __future__ import annotations

import logging
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from jarvis.config import Settings

logger = logging.getLogger(__name__)

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]


def load_google_credentials(settings: Settings) -> Credentials:
    """Load or refresh OAuth credentials; may open a browser on first run."""
    if settings.google_credentials_path is None:
        raise RuntimeError("GOOGLE_CREDENTIALS_PATH is not configured")
    secrets = Path(settings.google_credentials_path)
    if not secrets.is_file():
        raise FileNotFoundError(str(secrets))
    token_path = settings.google_token_file
    creds: Credentials | None = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), GOOGLE_SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets), GOOGLE_SCOPES)
    creds = flow.run_local_server(port=0)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    logger.info("Stored Google OAuth token at %s", token_path)
    return creds
