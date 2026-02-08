"""Internal webhook tool definitions and handler.

These are registered on the MCPBridge with ``webhook_`` prefix so the
Communication Agent can send/receive HTTP webhooks.  Write operations
(send, create, delete) require user confirmation.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from auton.webhooks.client import WebhookService

logger = logging.getLogger(__name__)

# ── Tool schemas (OpenAI function-calling format) ────────────────

WEBHOOK_TOOLS: list[dict[str, Any]] = [
    # ── Outbound ───────────────────────────────────────────────
    {
        "name": "webhook_send",
        "description": (
            "Send an HTTP webhook to an external URL. "
            "Supports POST, PUT, PATCH with JSON payload. "
            "Automatic retry and delivery tracking."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Target URL for the webhook.",
                },
                "payload": {
                    "type": "object",
                    "description": "JSON payload to send.",
                },
                "method": {
                    "type": "string",
                    "enum": ["POST", "PUT", "PATCH"],
                    "default": "POST",
                    "description": "HTTP method (default: POST).",
                },
                "headers": {
                    "type": "object",
                    "description": "Optional custom headers.",
                },
            },
            "required": ["url", "payload"],
        },
    },
    {
        "name": "webhook_get",
        "description": "Perform a GET request to fetch data from a URL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Target URL to fetch from.",
                },
                "params": {
                    "type": "object",
                    "description": "Query parameters as key-value pairs.",
                },
                "headers": {
                    "type": "object",
                    "description": "Optional custom headers.",
                },
            },
            "required": ["url"],
        },
    },
    # ── Subscription management ────────────────────────────────
    {
        "name": "webhook_create_subscription",
        "description": (
            "Register a new inbound webhook endpoint. "
            "Returns a webhook_id and URL path that external "
            "services can POST to with HMAC-SHA256 signatures."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "webhook_url": {
                    "type": "string",
                    "description": "Descriptive URL path for this webhook.",
                },
                "description": {
                    "type": "string",
                    "description": "Human-readable description.",
                },
                "signing_secret": {
                    "type": "string",
                    "description": "HMAC signing secret for verification.",
                },
                "agent_role": {
                    "type": "string",
                    "enum": [
                        "research",
                        "browser",
                        "communication",
                        "workspace",
                        "blockchain",
                    ],
                    "default": "research",
                    "description": "Agent role to handle inbound events.",
                },
            },
            "required": ["webhook_url", "description", "signing_secret"],
        },
    },
    {
        "name": "webhook_delete_subscription",
        "description": "Delete an inbound webhook subscription.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "webhook_id": {
                    "type": "string",
                    "description": "Webhook subscription ID to delete.",
                },
            },
            "required": ["webhook_id"],
        },
    },
    {
        "name": "webhook_list_subscriptions",
        "description": "List all registered inbound webhook subscriptions.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "webhook_list_deliveries",
        "description": "List recent outbound webhook deliveries with status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Filter by conversation (optional).",
                },
                "limit": {
                    "type": "integer",
                    "default": 20,
                    "description": "Max deliveries to return.",
                },
            },
            "required": [],
        },
    },
]


async def handle_webhook_tool(
    service: WebhookService,
    name: str,
    args: dict[str, Any],
) -> str:
    """Route a webhook tool call to the correct WebhookService method."""
    try:
        if name == "webhook_send":
            result = await service.send_webhook(
                url=args["url"],
                payload=args["payload"],
                method=args.get("method", "POST"),
                headers=args.get("headers"),
            )
        elif name == "webhook_get":
            result = await service.get_webhook(
                url=args["url"],
                params=args.get("params"),
                headers=args.get("headers"),
            )
        elif name == "webhook_create_subscription":
            result = await service.create_subscription(
                webhook_url=args["webhook_url"],
                description=args["description"],
                signing_secret=args["signing_secret"],
                agent_role=args.get("agent_role", "research"),
                metadata=args.get("metadata"),
            )
        elif name == "webhook_delete_subscription":
            result = await service.delete_subscription(
                webhook_id=args["webhook_id"],
            )
        elif name == "webhook_list_subscriptions":
            result = await service.list_subscriptions()
        elif name == "webhook_list_deliveries":
            result = await service.list_deliveries(
                conversation_id=args.get("conversation_id"),
                limit=args.get("limit", 20),
            )
        else:
            return f"[error] Unknown webhook tool: {name}"

        return json.dumps(result, indent=2, default=str)
    except Exception as exc:
        logger.exception("Webhook tool '%s' failed", name)
        return f"[error] Webhook tool '{name}' failed: {exc}"
