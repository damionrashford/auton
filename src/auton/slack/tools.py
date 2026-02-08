"""Internal Slack tool definitions and handler.

These tools are registered with the MCPBridge as internal tools,
so the LLM can call them the same way it calls external MCP tools.
"""

from __future__ import annotations

import json
from typing import Any

from auton.slack.client import SlackService

# ── Tool schemas (OpenAI function-calling format) ────────────────

SLACK_TOOLS: list[dict[str, Any]] = [
    {
        "name": "slack_send_message",
        "description": (
            "Send a message to a Slack channel or thread. "
            "Use channel ID (Cxxxxxxxxxx) or #channel-name."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "description": "Channel ID or #channel-name.",
                },
                "text": {
                    "type": "string",
                    "description": "Message text (supports Slack markdown/mrkdwn).",
                },
                "thread_ts": {
                    "type": "string",
                    "description": "Thread timestamp to reply in a thread (optional).",
                },
            },
            "required": ["channel", "text"],
        },
    },
    {
        "name": "slack_get_channel_history",
        "description": "Fetch recent messages from a Slack channel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "description": "Channel ID or #channel-name.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of messages to fetch (default 20, max 200).",
                    "default": 20,
                },
            },
            "required": ["channel"],
        },
    },
    {
        "name": "slack_search_messages",
        "description": (
            "Search messages across the Slack workspace. "
            "Supports Slack search operators (from:user, in:channel, etc.)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query string.",
                },
                "count": {
                    "type": "integer",
                    "description": "Number of results to return (default 10).",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "slack_list_channels",
        "description": "List public channels in the Slack workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max number of channels to return (default 100).",
                    "default": 100,
                },
            },
            "required": [],
        },
    },
    {
        "name": "slack_get_thread_replies",
        "description": "Fetch all replies in a Slack thread.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "description": "Channel ID where the thread lives.",
                },
                "thread_ts": {
                    "type": "string",
                    "description": "Timestamp of the parent message.",
                },
            },
            "required": ["channel", "thread_ts"],
        },
    },
    {
        "name": "slack_add_reaction",
        "description": "Add an emoji reaction to a Slack message.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Channel ID."},
                "timestamp": {
                    "type": "string",
                    "description": "Message timestamp.",
                },
                "name": {
                    "type": "string",
                    "description": "Emoji name without colons (e.g. 'thumbsup').",
                },
            },
            "required": ["channel", "timestamp", "name"],
        },
    },
    {
        "name": "slack_get_user_info",
        "description": "Get information about a Slack user by their ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "Slack user ID (Uxxxxxxxxxx).",
                },
            },
            "required": ["user_id"],
        },
    },
    {
        "name": "slack_upload_file",
        "description": "Upload text content as a file to a Slack channel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "channels": {
                    "type": "string",
                    "description": "Channel ID to upload to.",
                },
                "content": {
                    "type": "string",
                    "description": "Text content of the file.",
                },
                "filename": {
                    "type": "string",
                    "description": "Filename (e.g. 'report.txt').",
                },
                "title": {
                    "type": "string",
                    "description": "Title for the file (optional).",
                },
            },
            "required": ["channels", "content", "filename"],
        },
    },
]


async def handle_slack_tool(
    service: SlackService,
    name: str,
    args: dict[str, Any],
) -> str:
    """Route an internal Slack tool call to the correct SlackService method.

    Returns:
        JSON string result, or an error string starting with ``[error]``.
    """
    try:
        if name == "slack_send_message":
            result = await service.send_message(
                channel=args["channel"],
                text=args["text"],
                thread_ts=args.get("thread_ts"),
            )
        elif name == "slack_get_channel_history":
            result = await service.get_channel_history(
                channel=args["channel"],
                limit=args.get("limit", 20),
            )
        elif name == "slack_search_messages":
            result = await service.search_messages(
                query=args["query"],
                count=args.get("count", 10),
            )
        elif name == "slack_list_channels":
            result = await service.list_channels(
                limit=args.get("limit", 100),
            )
        elif name == "slack_get_thread_replies":
            result = await service.get_thread_replies(
                channel=args["channel"],
                thread_ts=args["thread_ts"],
            )
        elif name == "slack_add_reaction":
            result = await service.add_reaction(
                channel=args["channel"],
                timestamp=args["timestamp"],
                name=args["name"],
            )
        elif name == "slack_get_user_info":
            result = await service.get_user_info(user_id=args["user_id"])
        elif name == "slack_upload_file":
            result = await service.upload_file(
                channels=args["channels"],
                content=args["content"],
                filename=args["filename"],
                title=args.get("title", ""),
            )
        else:
            return f"[error] Unknown Slack tool: {name}"

        return json.dumps(result, indent=2, default=str)
    except Exception as exc:
        # Provide actionable error messages for common Slack API errors
        err_str = str(exc)
        if "channel_not_found" in err_str:
            return (
                "[error] Channel not found. "
                "Use slack_list_channels to find the correct channel ID."
            )
        if "not_in_channel" in err_str:
            return (
                "[error] Bot is not in this channel. "
                "Ask the user to invite the bot first."
            )
        if "ratelimited" in err_str or "rate_limited" in err_str:
            return (
                "[error] Slack rate limit hit. "
                "Wait 60 seconds before retrying."
            )
        if "invalid_auth" in err_str or "token_revoked" in err_str:
            return "[error] Slack authentication failed. Check bot token."
        return f"[error] Slack tool '{name}' failed: {exc}"
