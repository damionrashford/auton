"""Slack Bolt app — makes Slack the primary UI for the multi-agent system.

Listens via **Socket Mode** (WebSocket) so no public HTTP endpoint is needed.
Handles two event types:

  1. ``app_mention`` — someone @mentions the bot in a channel
  2. ``message`` (im) — someone DMs the bot directly

Both route the message through ``OrchestratorAgent.run()`` and reply
in the same Slack thread.  Each thread maps to one ``conversation_id``
for multi-turn continuity.

Safety: Write operations (send email, create file, etc.) trigger an
inline Slack confirmation — the bot posts a message asking the user to
reply "yes" or "no" in the thread.

Requires:
  - SLACK_BOT_TOKEN  (xoxb-...)
  - SLACK_APP_TOKEN  (xapp-...) — needed for Socket Mode
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from auton.agents.orchestrator import OrchestratorAgent

# Rate limit: max messages per user per window
_RATE_LIMIT_MAX = 5
_RATE_LIMIT_WINDOW = 60  # seconds


class SlackBoltUI:
    """Manages the Slack Bolt async app and Socket Mode connection."""

    def __init__(
        self,
        bot_token: str,
        app_token: str,
        orchestrator: OrchestratorAgent,
        memory_store: Any | None = None,
        agent_queue: Any | None = None,
    ) -> None:
        self._bot_token = bot_token
        self._app_token = app_token
        self._orchestrator = orchestrator
        self._memory_store = memory_store
        self._agent_queue = agent_queue
        self._app: Any = None
        self._handler: Any = None
        self._task: asyncio.Task[None] | None = None
        self._started = False
        self._bot_user_id = ""
        # Rate limiting: user_id -> list of timestamps
        self._rate_tracker: dict[str, list[float]] = defaultdict(list)
        self._rate_lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        return self._started

    async def start(self) -> None:
        """Initialize Bolt app, register handlers, start Socket Mode."""
        try:
            from slack_bolt.adapter.socket_mode.async_handler import (
                AsyncSocketModeHandler,
            )
            from slack_bolt.async_app import AsyncApp
        except ImportError:
            logger.warning(
                "slack-bolt not installed. Install with: pip install slack-bolt. "
                "Slack UI will not be available."
            )
            return

        self._app = AsyncApp(token=self._bot_token)

        # Get our own bot user ID so we can strip @mentions
        try:
            client = self._app.client
            auth = await client.auth_test()
            self._bot_user_id = auth.get("user_id", "")
            logger.info(
                "Slack Bolt UI authenticated: bot_user_id=%s, team=%s",
                self._bot_user_id,
                auth.get("team", "?"),
            )
        except Exception:
            logger.error(
                "Slack auth_test failed — cannot start Bolt UI.",
                exc_info=True,
            )
            return

        # Register event handlers
        self._app.event("app_mention")(self._handle_mention)
        self._app.event("message")(self._handle_dm)

        # Start Socket Mode in a background task
        self._handler = AsyncSocketModeHandler(self._app, self._app_token)
        self._task = asyncio.create_task(self._run_socket_mode())
        self._started = True
        logger.info("Slack Bolt UI started (Socket Mode).")

    async def _run_socket_mode(self) -> None:
        """Run the Socket Mode handler (blocks until stopped)."""
        try:
            await self._handler.start_async()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Socket Mode handler crashed.")

    async def stop(self) -> None:
        """Shut down the Socket Mode connection."""
        if self._handler is not None:
            try:
                await self._handler.close_async()
            except Exception:
                logger.warning(
                    "Error closing Socket Mode handler.", exc_info=True
                )

        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        self._started = False
        logger.info("Slack Bolt UI stopped.")

    # ── Event handlers ───────────────────────────────────────────

    async def _handle_mention(
        self, event: dict[str, Any], say: Any
    ) -> None:
        """Handle @bot mentions in channels."""
        # Prevent infinite loop — skip bot's own messages
        if event.get("bot_id"):
            return
        if event.get("user") == self._bot_user_id:
            return

        text = event.get("text", "")
        user = event.get("user", "")
        channel = event.get("channel", "")
        thread_ts = event.get("thread_ts") or event.get("ts", "")

        clean_text = self._strip_mention(text)
        if not clean_text.strip():
            await say(
                text="Hey! Send me a message and I'll help you out.",
                thread_ts=thread_ts,
            )
            return

        logger.info(
            "Slack mention from %s in %s: %s",
            user,
            channel,
            clean_text[:100],
        )

        conversation_id = f"slack_{channel}_{thread_ts}"

        await self._process_and_reply(
            text=clean_text,
            conversation_id=conversation_id,
            say=say,
            channel=channel,
            thread_ts=thread_ts,
            user=user,
        )

    async def _handle_dm(self, event: dict[str, Any], say: Any) -> None:
        """Handle direct messages to the bot."""
        if event.get("bot_id"):
            return
        if event.get("user") == self._bot_user_id:
            return
        if event.get("subtype"):
            return
        channel_type = event.get("channel_type", "")
        if channel_type != "im":
            return

        text = event.get("text", "")
        user = event.get("user", "")
        channel = event.get("channel", "")
        thread_ts = event.get("thread_ts") or event.get("ts", "")

        if not text.strip():
            return

        logger.info("Slack DM from %s: %s", user, text[:80])

        conversation_id = f"slack_dm_{user}_{thread_ts}"

        await self._process_and_reply(
            text=text,
            conversation_id=conversation_id,
            say=say,
            channel=channel,
            thread_ts=thread_ts,
            user=user,
        )

    # ── Core processing ──────────────────────────────────────────

    async def _process_and_reply(
        self,
        text: str,
        conversation_id: str,
        say: Any,
        channel: str,
        thread_ts: str,
        user: str,
    ) -> None:
        """Run the orchestrator and reply in the Slack thread."""
        # Rate limiting
        if await self._is_rate_limited(user):
            await say(
                text=":warning: You're sending messages too fast. "
                "Please wait a minute.",
                thread_ts=thread_ts,
            )
            return

        # Send a "thinking" indicator
        thinking_resp = await say(
            text=":hourglass_flowing_sand: Working on it...",
            thread_ts=thread_ts,
        )
        thinking_ts = (
            thinking_resp.get("ts", "") if thinking_resp else ""
        )

        try:
            # Build a confirmation callback for this thread
            confirm_cb = self._make_confirmation_callback(
                channel, thread_ts
            )

            # Use bounded queue if available, otherwise direct call.
            if self._agent_queue is not None:
                resp = await self._agent_queue.enqueue(
                    user_message=text,
                    conversation_id=conversation_id,
                    memory_store=self._memory_store,
                    confirmation_callback=confirm_cb,
                    source="slack",
                )
            else:
                resp = await self._orchestrator.run(
                    user_message=text,
                    conversation_id=conversation_id,
                    ctx=None,
                    memory_store=self._memory_store,
                    confirmation_callback=confirm_cb,
                )

            reply = resp.reply
            if not reply:
                reply = (
                    "I wasn't able to generate a response. "
                    "Please try again."
                )

            # Slack 4000 char limit — split if needed
            chunks = self._split_message(reply, max_len=3900)

            # Post the actual response
            for chunk in chunks:
                await say(text=chunk, thread_ts=thread_ts)

            # Delegation footer
            if resp.delegations:
                roles = [d.target_role for d in resp.delegations]
                footer = (
                    f":robot_face: _Agents: {', '.join(roles)} "
                    f"| {resp.iterations_used} iterations_"
                )
                await say(text=footer, thread_ts=thread_ts)

        except Exception as exc:
            logger.exception("Slack message processing failed")
            await say(
                text=f":x: Something went wrong: `{exc!s:.200}`",
                thread_ts=thread_ts,
            )
        finally:
            # Always clean up the thinking message
            if thinking_ts:
                try:
                    await self._app.client.chat_delete(
                        channel=channel, ts=thinking_ts
                    )
                except Exception:
                    pass

    # ── Slack-native confirmation ─────────────────────────────────

    def _make_confirmation_callback(
        self, channel: str, thread_ts: str
    ) -> Any:
        """Build an async confirmation callback for write operations.

        Posts a confirmation request to the Slack thread and waits
        for the user to reply "yes" or "no" (up to 60 seconds).
        """
        app = self._app

        async def _confirm(
            tool_name: str, args: dict[str, Any]
        ) -> bool:
            # Post confirmation request
            args_preview = json.dumps(args, indent=2)
            if len(args_preview) > 500:
                args_preview = args_preview[:500] + "\n..."

            confirm_msg = await app.client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=(
                    f":warning: *Confirmation required*\n\n"
                    f"The agent wants to execute: `{tool_name}`\n"
                    f"```{args_preview}```\n"
                    f"Reply *yes* to approve or *no* to deny "
                    f"(60s timeout, defaults to deny)."
                ),
            )
            confirm_ts = confirm_msg.get("ts", "")

            # Poll for user reply in the thread
            deadline = asyncio.get_event_loop().time() + 60
            while asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(3)
                try:
                    replies = await app.client.conversations_replies(
                        channel=channel,
                        ts=thread_ts,
                        oldest=confirm_ts,
                        limit=10,
                    )
                    for msg in replies.get("messages", []):
                        # Skip the confirmation message itself
                        if msg.get("ts") == confirm_ts:
                            continue
                        # Skip bot messages
                        if msg.get("bot_id"):
                            continue
                        reply_text = msg.get("text", "").strip().lower()
                        if reply_text in ("yes", "y", "approve"):
                            await app.client.reactions_add(
                                channel=channel,
                                timestamp=confirm_ts,
                                name="white_check_mark",
                            )
                            return True
                        if reply_text in ("no", "n", "deny", "cancel"):
                            await app.client.reactions_add(
                                channel=channel,
                                timestamp=confirm_ts,
                                name="x",
                            )
                            return False
                except Exception:
                    logger.debug(
                        "Error polling for confirmation reply",
                        exc_info=True,
                    )

            # Timeout — default deny
            try:
                await app.client.reactions_add(
                    channel=channel,
                    timestamp=confirm_ts,
                    name="alarm_clock",
                )
                await app.client.chat_postMessage(
                    channel=channel,
                    thread_ts=thread_ts,
                    text="_Confirmation timed out — action denied._",
                )
            except Exception:
                pass
            return False

        return _confirm

    # ── Rate limiting ─────────────────────────────────────────────

    async def _is_rate_limited(self, user: str) -> bool:
        """Check if *user* has exceeded the per-minute message limit.

        Uses an asyncio lock to prevent race conditions from concurrent
        Slack events modifying the rate tracker simultaneously.
        """
        async with self._rate_lock:
            now = time.monotonic()
            window_start = now - _RATE_LIMIT_WINDOW

            # Prune old entries
            self._rate_tracker[user] = [
                t for t in self._rate_tracker[user] if t > window_start
            ]
            if len(self._rate_tracker[user]) >= _RATE_LIMIT_MAX:
                return True

            self._rate_tracker[user].append(now)
            return False

    # ── Helpers ───────────────────────────────────────────────────

    def _strip_mention(self, text: str) -> str:
        """Remove @bot mention from the message text."""
        pattern = rf"<@{re.escape(self._bot_user_id)}>"
        return re.sub(pattern, "", text).strip()

    def _split_message(
        self, text: str, max_len: int = 3900
    ) -> list[str]:
        """Split a long message into Slack-friendly chunks."""
        if len(text) <= max_len:
            return [text]

        chunks: list[str] = []
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break
            split_at = text.rfind("\n", 0, max_len)
            if split_at == -1:
                split_at = max_len
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip("\n")
        return chunks
