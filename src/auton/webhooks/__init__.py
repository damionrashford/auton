"""Webhook integration for outbound HTTP requests and inbound receivers.

Provides:
  - WebhookService: Async HTTP client with retry logic and delivery tracking
  - WEBHOOK_TOOLS: Internal tool definitions for the agent
  - handle_webhook_tool: Tool call router
"""

from auton.webhooks.client import WebhookService
from auton.webhooks.tools import WEBHOOK_TOOLS, handle_webhook_tool

__all__ = ["WebhookService", "WEBHOOK_TOOLS", "handle_webhook_tool"]
