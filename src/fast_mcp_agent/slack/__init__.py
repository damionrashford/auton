"""Slack Bolt Python integration subpackage.

Provides:
  - SlackService: Async wrapper around Slack SDK's AsyncWebClient
  - SLACK_TOOLS: Internal tool definitions for the agent
  - handle_slack_tool: Tool call router
"""

from fast_mcp_agent.slack.client import SlackService
from fast_mcp_agent.slack.tools import SLACK_TOOLS, handle_slack_tool

__all__ = ["SlackService", "SLACK_TOOLS", "handle_slack_tool"]
