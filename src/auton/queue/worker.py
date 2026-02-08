"""arq-based task queue for agent execution with bounded concurrency.

Provides an ``AgentQueue`` wrapper that enqueues agent tasks into Redis
via arq and processes them with a configurable concurrency limit.

The queue can be used in two modes:

1. **In-process** (default): Uses ``asyncio.Semaphore`` for concurrency
   control within the same event loop.  No separate worker process needed.

2. **Standalone worker** (future): Run ``arq auton.queue.worker.WorkerSettings``
   as a separate process for true job isolation.

In-process mode is simpler and avoids the complexity of serializing
confirmation callbacks across process boundaries.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from auton.models import ChatResponse

if TYPE_CHECKING:
    from auton.agents.orchestrator import OrchestratorAgent
    from auton.config import Settings

logger = logging.getLogger(__name__)


class AgentQueue:
    """In-process bounded concurrency queue for agent runs.

    Uses ``asyncio.Semaphore`` to limit concurrent ``orchestrator.run()``
    calls across all sources (Slack, cron, MCP chat tool).
    """

    def __init__(
        self,
        orchestrator: OrchestratorAgent,
        settings: Settings,
    ) -> None:
        self._orchestrator = orchestrator
        self._settings = settings
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_agent_runs)
        self._active_jobs = 0
        self._total_jobs = 0
        self._lock = asyncio.Lock()

    @property
    def active_jobs(self) -> int:
        return self._active_jobs

    @property
    def max_concurrent(self) -> int:
        return self._settings.max_concurrent_agent_runs

    async def enqueue(
        self,
        user_message: str,
        conversation_id: str | None = None,
        ctx: Any | None = None,
        memory_store: Any | None = None,
        confirmation_callback: Any | None = None,
        source: str = "unknown",
    ) -> ChatResponse:
        """Execute an agent task within the bounded concurrency semaphore.

        Blocks until a slot is available (up to ``max_concurrent_agent_runs``
        concurrent runs).  This is NOT a fire-and-forget enqueue — it awaits
        the full agent response.

        Args:
            user_message: The user's query.
            conversation_id: Optional conversation ID for continuity.
            ctx: FastMCP context (None for Slack/cron).
            memory_store: Memory store instance.
            confirmation_callback: Async callback for write-op approval.
            source: Origin label for logging (``slack``, ``cron``, ``mcp``).

        Returns:
            The ChatResponse from the orchestrator.
        """
        async with self._lock:
            self._total_jobs += 1
            job_num = self._total_jobs

        logger.info(
            "Queue: job #%d from %s waiting for slot (%d/%d active).",
            job_num,
            source,
            self._active_jobs,
            self.max_concurrent,
        )

        async with self._semaphore:
            async with self._lock:
                self._active_jobs += 1

            try:
                logger.info(
                    "Queue: job #%d from %s started (%d/%d active).",
                    job_num,
                    source,
                    self._active_jobs,
                    self.max_concurrent,
                )
                return await self._orchestrator.run(
                    user_message=user_message,
                    conversation_id=conversation_id,
                    ctx=ctx,
                    memory_store=memory_store,
                    confirmation_callback=confirmation_callback,
                )
            finally:
                async with self._lock:
                    self._active_jobs -= 1
                logger.info(
                    "Queue: job #%d from %s finished (%d/%d active).",
                    job_num,
                    source,
                    self._active_jobs,
                    self.max_concurrent,
                )


def _parse_redis_settings(url: str) -> dict[str, Any]:
    """Parse a Redis URL into arq RedisSettings kwargs.

    Supports: ``redis://host:port/db`` format.
    """
    parsed = urlparse(url)
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 6379,
        "database": int(parsed.path.lstrip("/") or "0"),
        "password": parsed.password,
    }
