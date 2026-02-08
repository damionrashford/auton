"""Action classification and safety guardrails for autonomous agent.

Provides risk-level classification for tool calls to determine which actions
require human-in-the-loop confirmation before execution.
"""

from __future__ import annotations

from typing import Any

# Tools classified as WRITE operations (require confirmation by default)
WRITE_TOOLS = frozenset(
    {
        # Slack operations
        "slack_send_message",
        "slack_upload_file",
        "slack_add_reaction",
        "slack_set_channel_topic",
        "slack_invite_user",
        "slack_kick_user",
        "slack_archive_channel",
        # Cron operations
        "cron_create_job",
        "cron_delete_job",
        # Memory operations (forget is destructive)
        "memory_forget",
        # Webhook operations
        "webhook_send",
        "webhook_create_subscription",
        "webhook_delete_subscription",
        # Google Workspace write operations (pattern-matched)
        "gw_send_email",
        "gw_create_event",
        "gw_update_event",
        "gw_delete_event",
        "gw_create_file",
        "gw_delete_file",
        "gw_share_file",
        "gw_update_sheet",
        "gw_create_document",
        "gw_delete_document",
    }
)

# Keywords that indicate Google Workspace write operations
_GW_DANGEROUS_KEYWORDS = frozenset(
    {
        "create", "delete", "update", "send", "share",
        "move", "modify", "batch", "transfer", "remove",
        "import", "manage", "clear", "draft", "run",
        "set_publish",
    }
)

# Tools classified as READ operations (no confirmation needed)
READ_TOOLS = frozenset(
    {
        # Search and browse
        "search",
        "google_search",
        "browser_navigate",
        "browser_snapshot",
        "browser_screenshot",
        "pw_navigate",
        "pw_snapshot",
        "pw_screenshot",
        # Slack read operations
        "slack_get_channel_history",
        "slack_list_channels",
        "slack_search_messages",
        "slack_get_thread_replies",
        "slack_get_user_info",
        # Cron read operations
        "cron_list_jobs",
        # Memory read operations
        "memory_recall",
        "memory_store",  # Storing is safe
        # Google Workspace read operations
        "gw_list_emails",
        "gw_read_email",
        "gw_list_events",
        "gw_read_event",
        "gw_list_files",
        "gw_read_file",
        "gw_read_sheet",
    }
)


def requires_confirmation(
    tool_name: str,
    args: dict[str, Any],  # noqa: ARG001
    *,
    force_confirm: bool = False,
) -> bool:
    """Determine if a tool call needs user approval before execution.

    Args:
        tool_name: Name of the tool being called.
        args: Tool arguments (for context-aware classification).
        force_confirm: If True, require confirmation for all tools.

    Returns:
        True if the tool requires confirmation, False otherwise.
    """
    if force_confirm:
        return True

    # Explicit write operations
    if tool_name in WRITE_TOOLS:
        return True

    # Pattern-match Google Workspace tools (taylorwilsdon/google_workspace_mcp)
    if tool_name.startswith("gw_"):
        if any(keyword in tool_name for keyword in _GW_DANGEROUS_KEYWORDS):
            return True

    # ALL blockchain tools require confirmation (every action is a transaction)
    if tool_name.startswith("cb_"):
        return True

    # All other tools are considered safe
    return False


def classify_tool_risk(tool_name: str) -> str:
    """Classify tool risk level for observability.

    Args:
        tool_name: Name of the tool.

    Returns:
        Risk level: 'write', 'read', or 'unknown'.
    """
    if tool_name in WRITE_TOOLS:
        return "write"
    if tool_name in READ_TOOLS:
        return "read"
    if tool_name.startswith("gw_"):
        if any(keyword in tool_name for keyword in _GW_DANGEROUS_KEYWORDS):
            return "write"
        return "read"
    return "unknown"
