"""Internal cron tool definitions and handler.

These tools are registered with the MCPBridge as internal tools,
so the LLM can call them the same way it calls external MCP tools.
"""

from __future__ import annotations

import json
from typing import Any

from auton.scheduler.service import CronSchedulerService

# ── Tool schemas (OpenAI function-calling format) ────────────────

CRON_TOOLS: list[dict[str, Any]] = [
    {
        "name": "cron_create_job",
        "description": (
            "Schedule a recurring task with a cron expression. "
            "Standard 5-field cron format: minute hour day month day_of_week. "
            "Examples: '0 9 * * 1-5' = weekdays at 9am, "
            "'*/30 * * * *' = every 30 minutes, "
            "'0 0 1 * *' = first day of each month at midnight."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cron_expr": {
                    "type": "string",
                    "description": "5-field cron expression (e.g. '0 9 * * 1-5').",
                },
                "action_type": {
                    "type": "string",
                    "description": (
                        "Action to execute: 'search' (web search), "
                        "'slack_message' (send Slack msg), 'email' (send email), "
                        "'report' (generate report), or custom type."
                    ),
                },
                "params": {
                    "type": "object",
                    "description": (
                        "Action-specific parameters. For 'search': {query}. "
                        "For 'slack_message': {channel, text}. "
                        "For 'email': {to, subject, body}."
                    ),
                },
                "description": {
                    "type": "string",
                    "description": "Human-readable description of what this job does.",
                },
            },
            "required": ["cron_expr", "action_type", "params"],
        },
    },
    {
        "name": "cron_list_jobs",
        "description": "List all scheduled cron jobs with their details and next run times.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "cron_delete_job",
        "description": "Delete a scheduled cron job by its ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "The unique job ID (e.g. 'cron_a1b2c3d4').",
                },
            },
            "required": ["job_id"],
        },
    },
]


async def handle_cron_tool(
    service: CronSchedulerService,
    name: str,
    args: dict[str, Any],
) -> str:
    """Route an internal cron tool call to the correct CronSchedulerService method.

    Returns:
        JSON string result, or an error string starting with ``[error]``.
    """
    try:
        if name == "cron_create_job":
            result = await service.create_job(
                cron_expr=args["cron_expr"],
                action_type=args["action_type"],
                params=args.get("params", {}),
                description=args.get("description", ""),
            )
        elif name == "cron_list_jobs":
            result = await service.list_jobs()
        elif name == "cron_delete_job":
            deleted = await service.delete_job(job_id=args["job_id"])
            result = {"deleted": deleted, "job_id": args["job_id"]}
        else:
            return f"[error] Unknown cron tool: {name}"

        return json.dumps(result, indent=2, default=str)
    except Exception as exc:
        return f"[error] Cron tool '{name}' failed: {exc}"
