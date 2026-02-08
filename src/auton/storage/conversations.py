"""Neon Postgres-backed conversation store.

Replaces the in-memory ConversationStore with durable persistence.
Maintains an LRU in-memory cache for hot conversations so repeated
reads within a single agentic loop don't hit the database.

All public methods are ``async`` — callers must ``await`` them.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections import OrderedDict
from typing import Any

import asyncpg

from auton.core.prompts import SYSTEM_PROMPT as _SYSTEM_PROMPT
from auton.models import ChatMessage, ChatRole, ToolCallPayload, UsageStats

logger = logging.getLogger(__name__)

# Maximum number of concurrent conversations held in the in-memory cache.
_MAX_CACHE = 200


class NeonConversationStore:
    """Async, Postgres-backed conversation store with in-memory LRU cache."""

    def __init__(self, pool: asyncpg.Pool, max_cache: int = _MAX_CACHE) -> None:
        self._pool = pool
        self._cache: OrderedDict[str, list[ChatMessage]] = OrderedDict()
        self._max_cache = max_cache

    # ── public API ──────────────────────────────────────────────────

    async def get_or_create(
        self,
        conversation_id: str | None = None,
        parent_conversation_id: str | None = None,
        agent_role: str | None = None,
        system_prompt_override: str | None = None,
    ) -> tuple[str, list[ChatMessage]]:
        """Return an existing conversation or bootstrap a new one.

        Checks the in-memory cache first, then Postgres, then creates new.

        Args:
            conversation_id: Optional existing conversation ID.
            parent_conversation_id: Parent conversation (for delegation chains).
            agent_role: Agent role for this conversation.
            system_prompt_override: Custom system prompt (for specialist agents).
        """
        # 1. Check in-memory cache
        if conversation_id and conversation_id in self._cache:
            self._cache.move_to_end(conversation_id)
            return conversation_id, self._cache[conversation_id]

        # 2. Check Postgres for existing conversation
        if conversation_id:
            messages = await self._load_from_db(conversation_id)
            if messages is not None:
                self._cache[conversation_id] = messages
                self._cache.move_to_end(conversation_id)
                self._evict_cache()
                return conversation_id, messages

        # 3. Create new conversation
        cid = conversation_id or uuid.uuid4().hex[:12]
        prompt = system_prompt_override or _SYSTEM_PROMPT
        messages = [ChatMessage(role=ChatRole.SYSTEM, content=prompt)]

        # Persist to Postgres
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO conversations (id, parent_conversation_id, agent_role)
                VALUES ($1, $2, $3)
                ON CONFLICT (id) DO NOTHING
                """,
                cid,
                parent_conversation_id,
                agent_role,
            )
            await self._insert_message(conn, cid, messages[0])

        self._cache[cid] = messages
        self._evict_cache()
        return cid, messages

    async def append(self, conversation_id: str, message: ChatMessage) -> None:
        """Append a message to the specified conversation.

        Writes to both Postgres and the in-memory cache.
        """
        # Persist to Postgres
        async with self._pool.acquire() as conn:
            await self._insert_message(conn, conversation_id, message)
            await conn.execute(
                "UPDATE conversations SET updated_at = NOW() WHERE id = $1",
                conversation_id,
            )

        # Update in-memory cache
        if conversation_id in self._cache:
            self._cache[conversation_id].append(message)

    async def clear(self, conversation_id: str) -> bool:
        """Delete a conversation. Returns True if it existed."""
        self._cache.pop(conversation_id, None)

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM conversations WHERE id = $1", conversation_id
            )
            return result == "DELETE 1"

    async def clear_all(self) -> int:
        """Delete every conversation. Returns the count removed."""
        self._cache.clear()

        async with self._pool.acquire() as conn:
            result = await conn.execute("DELETE FROM conversations")
            # result is like "DELETE 42"
            try:
                return int(result.split()[-1])
            except (ValueError, IndexError):
                return 0

    async def list_ids(self) -> list[str]:
        """Return all conversation IDs from Postgres."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id FROM conversations ORDER BY updated_at DESC"
            )
            return [row["id"] for row in rows]

    async def log_tool_call(
        self,
        conversation_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        result_text: str,
        duration_ms: int,
        success: bool = True,
    ) -> None:
        """Insert a tool call log entry for analytics and debugging."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO tool_call_logs
                    (conversation_id, tool_name, arguments, result_text, duration_ms, success)
                VALUES ($1, $2, $3::jsonb, $4, $5, $6)
                """,
                conversation_id,
                tool_name,
                json.dumps(arguments),
                result_text[:10_000] if result_text else None,  # cap stored text
                duration_ms,
                success,
            )

    async def log_usage(
        self,
        conversation_id: str,
        model: str,
        usage: UsageStats,
    ) -> None:
        """Insert a usage accounting entry (token counts + cost)."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO usage_logs
                    (conversation_id, model, prompt_tokens, completion_tokens,
                     total_tokens, reasoning_tokens, cached_tokens,
                     cache_write_tokens, cost)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                conversation_id,
                model,
                usage.prompt_tokens,
                usage.completion_tokens,
                usage.total_tokens,
                usage.reasoning_tokens,
                usage.cached_tokens,
                usage.cache_write_tokens,
                usage.cost,
            )

    async def get_daily_cost(self) -> float:
        """Sum cost from usage_logs for today (UTC)."""
        async with self._pool.acquire() as conn:
            result = await conn.fetchval(
                """
                SELECT COALESCE(SUM(cost), 0.0)
                FROM usage_logs
                WHERE created_at >= CURRENT_DATE
                """
            )
            return float(result) if result is not None else 0.0

    async def get_conversation_cost(self, conversation_id: str) -> float:
        """Sum cost from usage_logs for a specific conversation."""
        async with self._pool.acquire() as conn:
            result = await conn.fetchval(
                """
                SELECT COALESCE(SUM(cost), 0.0)
                FROM usage_logs
                WHERE conversation_id = $1
                """,
                conversation_id,
            )
            return float(result) if result is not None else 0.0

    async def log_decision(
        self,
        conversation_id: str,
        iteration: int,
        event_type: str,
        details: dict[str, Any],
    ) -> None:
        """Log an agent decision event for observability."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agent_decision_logs
                    (conversation_id, iteration, event_type, details)
                VALUES ($1, $2, $3, $4::jsonb)
                """,
                conversation_id,
                iteration,
                event_type,
                json.dumps(details),
            )

    # ── delegation tracking ──────────────────────────────────────

    async def log_delegation(
        self,
        parent_conversation_id: str,
        child_conversation_id: str,
        orchestrator_role: str,
        worker_role: str,
        task_instruction: str,
        task_context: dict[str, Any],
    ) -> int:
        """Log a delegation event. Returns delegation ID."""
        async with self._pool.acquire() as conn:
            delegation_id: int = await conn.fetchval(
                """
                INSERT INTO agent_delegations
                    (parent_conversation_id, child_conversation_id,
                     orchestrator_role, worker_role, task_instruction,
                     task_context, status, started_at)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, 'running', NOW())
                RETURNING id
                """,
                parent_conversation_id,
                child_conversation_id,
                orchestrator_role,
                worker_role,
                task_instruction,
                json.dumps(task_context),
            )
            return delegation_id

    async def update_delegation_result(
        self,
        delegation_id: int,
        status: str,
        result_summary: str | None,
        error_message: str | None,
        iterations_used: int,
        tools_called: list[str],
        cost: float,
    ) -> None:
        """Update delegation result after completion."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE agent_delegations
                SET status = $1,
                    result_summary = $2,
                    error_message = $3,
                    iterations_used = $4,
                    tools_called = $5::jsonb,
                    cost = $6,
                    completed_at = NOW()
                WHERE id = $7
                """,
                status,
                result_summary,
                error_message,
                iterations_used,
                json.dumps(tools_called),
                cost,
                delegation_id,
            )

    async def get_delegation_history(
        self,
        conversation_id: str,
    ) -> list[dict[str, Any]]:
        """Get all delegations for a conversation (parent or child)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM agent_delegations
                WHERE parent_conversation_id = $1
                   OR child_conversation_id = $1
                ORDER BY created_at ASC
                """,
                conversation_id,
            )
            return [dict(row) for row in rows]

    # ── internal helpers ───────────────────────────────────────────

    async def _load_from_db(
        self, conversation_id: str
    ) -> list[ChatMessage] | None:
        """Load a conversation's messages from Postgres.

        Returns None if the conversation doesn't exist.
        """
        async with self._pool.acquire() as conn:
            # Check conversation exists
            exists = await conn.fetchval(
                "SELECT 1 FROM conversations WHERE id = $1", conversation_id
            )
            if not exists:
                return None

            rows = await conn.fetch(
                """
                SELECT role, content, name, tool_call_id, tool_calls
                FROM messages
                WHERE conversation_id = $1
                ORDER BY created_at ASC, id ASC
                """,
                conversation_id,
            )

        messages: list[ChatMessage] = []
        for row in rows:
            tool_calls = None
            if row["tool_calls"]:
                raw_tc = json.loads(row["tool_calls"])
                tool_calls = [ToolCallPayload(**tc) for tc in raw_tc]

            messages.append(
                ChatMessage(
                    role=ChatRole(row["role"]),
                    content=row["content"],
                    name=row["name"],
                    tool_call_id=row["tool_call_id"],
                    tool_calls=tool_calls,
                )
            )

        return messages

    async def _insert_message(
        self,
        conn: asyncpg.Connection,
        conversation_id: str,
        message: ChatMessage,
    ) -> None:
        """INSERT a single message row."""
        tool_calls_json: str | None = None
        if message.tool_calls:
            tool_calls_json = json.dumps(
                [tc.model_dump() for tc in message.tool_calls]
            )

        await conn.execute(
            """
            INSERT INTO messages
                (conversation_id, role, content, name, tool_call_id, tool_calls)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
            """,
            conversation_id,
            message.role.value,
            message.content,
            message.name,
            message.tool_call_id,
            tool_calls_json,
        )

    def _evict_cache(self) -> None:
        """Remove the oldest cached conversations when over capacity."""
        while len(self._cache) > self._max_cache:
            self._cache.popitem(last=False)
