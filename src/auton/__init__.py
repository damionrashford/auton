"""Auton -- autonomous research assistant.

Bridges RivalSearchMCP, Playwright MCP, Google Workspace MCP,
Slack (via slack-sdk), and Cron scheduling (via APScheduler).
Powered by OpenRouter LLM with Neon Postgres persistence.
"""

__version__ = "0.1.0"

from auton.storage.conversations import NeonConversationStore

__all__ = ["NeonConversationStore"]
