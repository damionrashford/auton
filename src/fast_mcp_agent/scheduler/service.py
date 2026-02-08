"""Cron job scheduler service using APScheduler.

Jobs are persisted in Neon Postgres for durability across restarts.
Uses APScheduler's AsyncIOScheduler with CronTrigger for flexible
cron-expression-based scheduling.  cron-descriptor provides
human-readable descriptions of each schedule.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# SQL for the cron_jobs table (also added to schema.sql for migrations)
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS cron_jobs (
    id          TEXT PRIMARY KEY,
    cron_expr   TEXT NOT NULL,
    action_type TEXT NOT NULL,
    params      JSONB NOT NULL DEFAULT '{}',
    description TEXT NOT NULL DEFAULT '',
    human_desc  TEXT NOT NULL DEFAULT '',
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_run_at TIMESTAMPTZ
);
"""


class CronSchedulerService:
    """Manages cron jobs using APScheduler, persisted in Neon Postgres."""

    def __init__(
        self,
        pool: Any | None = None,
        timezone: str = "UTC",
    ) -> None:
        self._pool = pool
        self._timezone = timezone
        self._scheduler: Any = None
        self._started = False
        self._jobs: dict[str, dict[str, Any]] = {}
        # Dependencies for agent loop re-entry (injected via set_job_dependencies)
        self._bridge: Any = None
        self._llm: Any = None
        self._store: Any = None
        self._settings: Any = None
        self._slack_client: Any = None  # For posting cron results to Slack

    def set_job_dependencies(
        self,
        *,
        bridge: Any,
        llm: Any,
        store: Any,
        settings: Any,
        slack_client: Any = None,
    ) -> None:
        """Inject dependencies needed for agent loop re-entry during job execution."""
        self._bridge = bridge
        self._llm = llm
        self._store = store
        self._settings = settings
        self._slack_client = slack_client
        logger.info("Cron job dependencies injected for agent loop execution.")

    @property
    def is_running(self) -> bool:
        return self._started

    async def start(self) -> None:
        """Initialize APScheduler, create table, and load existing jobs."""
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler

            self._scheduler = AsyncIOScheduler(timezone=self._timezone)
        except ImportError:
            logger.warning(
                "APScheduler not installed. Cron scheduling disabled. "
                "Install with: pip install apscheduler"
            )
            return

        # Create table if we have a DB pool
        if self._pool is not None:
            async with self._pool.acquire() as conn:
                await conn.execute(_CREATE_TABLE_SQL)
            await self._load_jobs_from_db()

        self._scheduler.start()
        self._started = True
        logger.info(
            "Cron scheduler started (timezone=%s, jobs=%d).",
            self._timezone,
            len(self._jobs),
        )

    async def stop(self) -> None:
        """Shut down the scheduler."""
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
        self._started = False
        logger.info("Cron scheduler stopped.")

    async def create_job(
        self,
        cron_expr: str,
        action_type: str,
        params: dict[str, Any],
        description: str = "",
    ) -> dict[str, Any]:
        """Create a new cron job, persist to Neon, schedule in APScheduler.

        Args:
            cron_expr: Standard cron expression (e.g. "0 9 * * 1-5").
            action_type: Action category (search, slack_message, email, etc.).
            params: Action-specific parameters as a dict.
            description: Human description of what this job does.

        Returns:
            Dict with job details including id, cron, human_desc, etc.
        """
        # Generate human-readable description
        human_desc = self._describe_cron(cron_expr)

        job_id = f"cron_{uuid.uuid4().hex[:8]}"

        job_data: dict[str, Any] = {
            "id": job_id,
            "cron_expr": cron_expr,
            "action_type": action_type,
            "params": params,
            "description": description,
            "human_desc": human_desc,
            "enabled": True,
            "created_at": datetime.now(UTC).isoformat(),
        }

        # Persist to database
        if self._pool is not None:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO cron_jobs
                        (id, cron_expr, action_type, params, description, human_desc)
                    VALUES ($1, $2, $3, $4::jsonb, $5, $6)
                    """,
                    job_id,
                    cron_expr,
                    action_type,
                    json.dumps(params),
                    description,
                    human_desc,
                )

        # Schedule in APScheduler
        self._schedule_job(job_data)

        # Store in memory
        self._jobs[job_id] = job_data

        logger.info(
            "Cron job created: id=%s, cron='%s' (%s), action=%s",
            job_id,
            cron_expr,
            human_desc,
            action_type,
        )

        return job_data

    async def list_jobs(self) -> list[dict[str, Any]]:
        """List all cron jobs."""
        if self._pool is not None:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM cron_jobs ORDER BY created_at DESC"
                )
                return [
                    {
                        "id": row["id"],
                        "cron_expr": row["cron_expr"],
                        "action_type": row["action_type"],
                        "params": json.loads(row["params"]) if row["params"] else {},
                        "description": row["description"],
                        "human_desc": row["human_desc"],
                        "enabled": row["enabled"],
                        "created_at": str(row["created_at"]),
                        "last_run_at": str(row["last_run_at"]) if row["last_run_at"] else None,
                    }
                    for row in rows
                ]

        return list(self._jobs.values())

    async def delete_job(self, job_id: str) -> bool:
        """Delete a cron job from Neon and APScheduler.

        Returns True if the job existed and was deleted.
        """
        # Remove from APScheduler
        if self._scheduler is not None:
            try:
                self._scheduler.remove_job(job_id)
            except Exception:
                pass

        # Remove from database
        deleted = False
        if self._pool is not None:
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM cron_jobs WHERE id = $1", job_id
                )
                deleted = result == "DELETE 1"

        # Remove from memory
        if job_id in self._jobs:
            del self._jobs[job_id]
            deleted = True

        if deleted:
            logger.info("Cron job deleted: %s", job_id)

        return deleted

    # ── internal helpers ─────────────────────────────────────────

    def _describe_cron(self, cron_expr: str) -> str:
        """Generate a human-readable description of a cron expression."""
        try:
            from cron_descriptor import get_description

            return get_description(cron_expr)
        except Exception:
            return cron_expr

    def _schedule_job(self, job_data: dict[str, Any]) -> None:
        """Add a job to APScheduler using CronTrigger."""
        if self._scheduler is None:
            return

        try:
            from apscheduler.triggers.cron import CronTrigger

            parts = job_data["cron_expr"].split()
            if len(parts) != 5:
                logger.warning(
                    "Invalid cron expression '%s' for job %s — skipping.",
                    job_data["cron_expr"],
                    job_data["id"],
                )
                return

            trigger = CronTrigger(
                minute=parts[0],
                hour=parts[1],
                day=parts[2],
                month=parts[3],
                day_of_week=parts[4],
                timezone=self._timezone,
            )

            self._scheduler.add_job(
                self._execute_job,
                trigger=trigger,
                id=job_data["id"],
                args=[job_data],
                replace_existing=True,
            )
        except Exception:
            logger.warning(
                "Failed to schedule cron job %s", job_data["id"], exc_info=True
            )

    async def _execute_job(self, job_data: dict[str, Any]) -> None:
        """Execute a scheduled cron job by re-entering the agent loop.

        This is the callback invoked by APScheduler when a job fires.
        Constructs a user message from the action type and params, then
        runs the agent loop headlessly (no ctx, no progress reporting).
        """
        job_id = job_data["id"]
        action = job_data["action_type"]
        params = job_data["params"]

        logger.info(
            "Cron job firing: id=%s, action=%s, params=%s",
            job_id,
            action,
            params,
        )

        started_at = datetime.now(UTC)
        success = False
        result_text = ""
        error_text = ""

        # Update last_run_at in database
        if self._pool is not None:
            try:
                async with self._pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE cron_jobs SET last_run_at = NOW() WHERE id = $1",
                        job_id,
                    )
            except Exception:
                logger.warning("Failed to update last_run_at for %s", job_id)

        # Execute job via agent loop if dependencies are available
        if (
            self._bridge is None
            or self._llm is None
            or self._store is None
            or self._settings is None
        ):
            error_text = "Cron job dependencies not injected — cannot execute agent loop."
            logger.error("%s (job_id=%s)", error_text, job_id)
        else:
            try:
                # Construct user message from action type and params
                user_message = self._build_user_message(action, params)

                # Import agent here to avoid circular dependency
                from fast_mcp_agent.agents.roles import AgentConfig, AgentRole
                from fast_mcp_agent.core.agent import run_agent

                # Build agent config from job data (default: research agent)
                cron_role = AgentRole(job_data.get("agent_role", "research"))
                cron_config = AgentConfig(
                    role=cron_role,
                    allowed_tool_patterns=["search", "pw_*", "browser_*", "memory_*"],
                )

                # Run agent loop (headless: no ctx, no confirmations)
                resp = await run_agent(
                    user_message=user_message,
                    bridge=self._bridge,
                    llm=self._llm,
                    store=self._store,
                    settings=self._settings,
                    agent_config=cron_config,
                    conversation_id=f"cron_{job_id}",
                    ctx=None,
                    headless=True,
                )
                success = True
                result_text = resp.reply[:500]  # Truncate for storage
                logger.info(
                    "Cron job completed: id=%s, iterations=%d, tools=%d",
                    job_id,
                    resp.iterations_used,
                    len(resp.tools_called),
                )
            except Exception as exc:
                error_text = str(exc)[:500]
                logger.exception("Cron job execution failed: id=%s", job_id)

        # Log execution to cron_job_runs table
        if self._pool is not None:
            try:
                async with self._pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO cron_job_runs
                            (job_id, started_at, finished_at,
                             success, result, error)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        job_id,
                        started_at,
                        datetime.now(UTC),
                        success,
                        result_text if success else None,
                        error_text if not success else None,
                    )
            except Exception:
                logger.warning(
                    "Failed to log cron job run for %s",
                    job_id,
                    exc_info=True,
                )

        # Post results to Slack notification channel (if configured)
        notify_channel = job_data.get("notification_channel", "")
        if notify_channel and self._slack_client is not None:
            try:
                emoji = ":white_check_mark:" if success else ":x:"
                desc = job_data.get("description", job_id)
                snippet = (result_text or error_text)[:300]
                await self._slack_client.chat_postMessage(
                    channel=notify_channel,
                    text=(
                        f"{emoji} *Scheduled Job: {desc}*\n"
                        f"Status: {'Success' if success else 'Failed'}\n"
                        f"```{snippet}```"
                    ),
                )
            except Exception:
                logger.warning(
                    "Failed to post cron result to Slack for %s",
                    job_id,
                    exc_info=True,
                )

    def _build_user_message(self, action_type: str, params: dict[str, Any]) -> str:
        """Construct a user message from action type and params."""
        # Default: JSON dump
        if action_type == "search":
            query = params.get("query", "")
            return f"Search for: {query}"
        if action_type == "slack_message":
            channel = params.get("channel", "")
            text = params.get("text", "")
            return f"Send Slack message to {channel}: {text}"
        if action_type == "email":
            to = params.get("to", "")
            subject = params.get("subject", "")
            return f"Send email to {to} with subject: {subject}"
        # Generic fallback
        return f"Execute scheduled task: {action_type} with params: {json.dumps(params)}"

    async def _load_jobs_from_db(self) -> None:
        """Reload all enabled jobs from Postgres and schedule them."""
        if self._pool is None:
            return

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM cron_jobs WHERE enabled = TRUE"
            )

        for row in rows:
            job_data = {
                "id": row["id"],
                "cron_expr": row["cron_expr"],
                "action_type": row["action_type"],
                "params": json.loads(row["params"]) if row["params"] else {},
                "description": row["description"],
                "human_desc": row["human_desc"],
                "enabled": row["enabled"],
            }
            self._jobs[row["id"]] = job_data
            self._schedule_job(job_data)
