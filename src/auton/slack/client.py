"""Async Slack service wrapping the Slack SDK's AsyncWebClient.

Provides typed helper methods for common Slack operations used by the
AI agent.  Does NOT use Slack Bolt's event-driven App — we only need
the API client for outbound operations.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class SlackService:
    """Async wrapper around Slack SDK's AsyncWebClient."""

    def __init__(self, bot_token: str) -> None:
        self._bot_token = bot_token
        self._client: Any = None
        self._started = False
        self._bot_user_id: str = ""

    @property
    def is_connected(self) -> bool:
        return self._started

    @property
    def web_client(self) -> Any:
        """Return the underlying AsyncWebClient (or None)."""
        return self._client

    async def start(self) -> None:
        """Verify auth and initialize the client."""
        from slack_sdk.web.async_client import AsyncWebClient

        self._client = AsyncWebClient(token=self._bot_token)

        try:
            resp = await self._client.auth_test()
            self._bot_user_id = resp.get("user_id", "")
            self._started = True
            logger.info(
                "Slack Bolt connected (bot_user_id=%s, team=%s).",
                self._bot_user_id,
                resp.get("team", "unknown"),
            )
        except Exception:
            logger.warning("Slack auth_test failed. Continuing without Slack.", exc_info=True)
            self._started = False

    async def stop(self) -> None:
        """Shut down the Slack client."""
        self._started = False
        self._client = None
        logger.info("Slack service stopped.")

    # ── Tool methods ─────────────────────────────────────────────

    async def send_message(
        self,
        channel: str,
        text: str,
        thread_ts: str | None = None,
    ) -> dict[str, Any]:
        """Send a message to a Slack channel or thread."""
        kwargs: dict[str, Any] = {"channel": channel, "text": text}
        if thread_ts:
            kwargs["thread_ts"] = thread_ts

        resp = await self._client.chat_postMessage(**kwargs)
        return {
            "ok": resp.get("ok", False),
            "ts": resp.get("ts", ""),
            "channel": resp.get("channel", channel),
        }

    async def get_channel_history(
        self,
        channel: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Fetch recent messages from a channel."""
        resp = await self._client.conversations_history(
            channel=channel, limit=limit
        )
        messages = resp.get("messages", [])
        return [
            {
                "user": m.get("user", ""),
                "text": m.get("text", ""),
                "ts": m.get("ts", ""),
                "thread_ts": m.get("thread_ts"),
            }
            for m in messages
        ]

    async def search_messages(
        self,
        query: str,
        count: int = 10,
    ) -> list[dict[str, Any]]:
        """Search messages across the workspace."""
        resp = await self._client.search_messages(query=query, count=count)
        matches = resp.get("messages", {}).get("matches", [])
        return [
            {
                "text": m.get("text", ""),
                "user": m.get("user", ""),
                "channel": m.get("channel", {}).get("name", ""),
                "ts": m.get("ts", ""),
                "permalink": m.get("permalink", ""),
            }
            for m in matches[:count]
        ]

    async def list_channels(
        self,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List public channels in the workspace."""
        resp = await self._client.conversations_list(
            types="public_channel", limit=limit
        )
        channels = resp.get("channels", [])
        return [
            {
                "id": c.get("id", ""),
                "name": c.get("name", ""),
                "topic": c.get("topic", {}).get("value", ""),
                "num_members": c.get("num_members", 0),
            }
            for c in channels
        ]

    async def get_thread_replies(
        self,
        channel: str,
        thread_ts: str,
    ) -> list[dict[str, Any]]:
        """Fetch replies in a thread."""
        resp = await self._client.conversations_replies(
            channel=channel, ts=thread_ts
        )
        messages = resp.get("messages", [])
        return [
            {
                "user": m.get("user", ""),
                "text": m.get("text", ""),
                "ts": m.get("ts", ""),
            }
            for m in messages
        ]

    async def add_reaction(
        self,
        channel: str,
        timestamp: str,
        name: str,
    ) -> bool:
        """Add an emoji reaction to a message."""
        try:
            await self._client.reactions_add(
                channel=channel, timestamp=timestamp, name=name
            )
            return True
        except Exception:
            return False

    async def get_user_info(self, user_id: str) -> dict[str, Any]:
        """Get information about a Slack user."""
        resp = await self._client.users_info(user=user_id)
        user = resp.get("user", {})
        profile = user.get("profile", {})
        return {
            "id": user.get("id", ""),
            "name": user.get("name", ""),
            "real_name": profile.get("real_name", ""),
            "email": profile.get("email", ""),
            "title": profile.get("title", ""),
            "status_text": profile.get("status_text", ""),
        }

    async def set_channel_topic(
        self,
        channel: str,
        topic: str,
    ) -> bool:
        """Set the topic for a channel."""
        try:
            await self._client.conversations_setTopic(channel=channel, topic=topic)
            return True
        except Exception:
            return False

    async def upload_file(
        self,
        channels: str,
        content: str,
        filename: str,
        title: str = "",
    ) -> dict[str, Any]:
        """Upload text content as a file to a channel."""
        resp = await self._client.files_upload_v2(
            channels=channels,
            content=content,
            filename=filename,
            title=title or filename,
        )
        return {
            "ok": resp.get("ok", False),
            "file_id": resp.get("file", {}).get("id", ""),
        }

    def to_json(self, data: Any) -> str:
        """Serialize data to JSON string for tool responses."""
        return json.dumps(data, indent=2, default=str)
