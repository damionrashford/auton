"""Async task queue for bounded, prioritized agent execution.

Uses ``arq`` (async Redis queue) to provide:
  - Bounded concurrency (``max_concurrent_agent_runs``)
  - Job timeout (matches orchestrator timeout)
  - Retry with backoff for transient failures
  - Result storage in Redis
"""

from auton.queue.worker import AgentQueue

__all__ = ["AgentQueue"]
