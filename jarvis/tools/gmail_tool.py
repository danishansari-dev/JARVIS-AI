"""Gmail read and draft operations behind a single validated tool."""

from __future__ import annotations

import asyncio
import base64
import logging
from email.message import EmailMessage
from typing import Annotated, Any, Literal, Union

from googleapiclient.discovery import build
from pydantic import BaseModel, EmailStr, Field, RootModel

from jarvis.config import Settings
from jarvis.tools.google_credentials import load_google_credentials
from jarvis.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class GmailReadArgs(BaseModel):
    action: Literal["read_recent"] = "read_recent"
    max_messages: int = Field(default=5, ge=1, le=50)


class GmailDraftArgs(BaseModel):
    action: Literal["draft_reply"] = "draft_reply"
    to: EmailStr
    subject: str
    body: str
    thread_id: str | None = Field(default=None, description="Optional Gmail thread id to reply in")


GmailUnion = Annotated[Union[GmailReadArgs, GmailDraftArgs], Field(discriminator="action")]


class GmailInvocation(RootModel[GmailUnion]):
    pass


def _gmail_service(settings: Settings) -> Any:
    creds = load_google_credentials(settings)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


async def _read_recent(settings: Settings, args: GmailReadArgs) -> list[dict[str, Any]]:
    def _run() -> list[dict[str, Any]]:
        service = _gmail_service(settings)
        results = (
            service.users()
            .messages()
            .list(userId="me", maxResults=args.max_messages)
            .execute()
        )
        messages = results.get("messages", [])
        out: list[dict[str, Any]] = []
        for m in messages:
            msg = service.users().messages().get(userId="me", id=m["id"], format="metadata").execute()
            headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
            out.append(
                {
                    "id": m["id"],
                    "snippet": msg.get("snippet"),
                    "subject": headers.get("subject"),
                    "from": headers.get("from"),
                }
            )
        return out

    return await asyncio.to_thread(_run)


async def _draft_reply(settings: Settings, args: GmailDraftArgs) -> str:
    def _run() -> str:
        service = _gmail_service(settings)
        message = EmailMessage()
        message["To"] = str(args.to)
        message["Subject"] = args.subject
        message.set_content(args.body)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        body: dict[str, Any] = {"message": {"raw": raw}}
        if args.thread_id:
            body["message"]["threadId"] = args.thread_id
        draft = service.users().drafts().create(userId="me", body=body).execute()
        return str(draft.get("id", "draft"))

    return await asyncio.to_thread(_run)


def build_gmail_handler(settings: Settings):
    async def _handler(inv: GmailInvocation) -> list[dict[str, Any]] | str:
        inner = inv.root
        if isinstance(inner, GmailReadArgs):
            return await _read_recent(settings, inner)
        if isinstance(inner, GmailDraftArgs):
            return await _draft_reply(settings, inner)
        raise TypeError("Unsupported gmail payload")

    return _handler


def register_gmail_tool(registry: ToolRegistry, settings: Settings) -> None:
    if settings.google_credentials_path is None:
        logger.info("Skipping gmail tool: GOOGLE_CREDENTIALS_PATH not set")
        return
    registry.register(
        "gmail",
        "Read recent Gmail messages or create a draft email.",
        GmailInvocation,
        build_gmail_handler(settings),
    )
