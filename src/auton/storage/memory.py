"""Long-term semantic memory using OpenRouter embeddings + pgvector.

Provides persistent memory storage with semantic search capability:
  - Store facts, preferences, findings with automatic embedding
  - Recall relevant memories via natural language queries
  - Forget specific memories by ID
"""

from __future__ import annotations

import json
import logging
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


class MemoryStore:
    """Manages long-term semantic memory in Neon Postgres with pgvector."""

    def __init__(
        self,
        pool: asyncpg.Pool | None,
        llm: Any,  # LLMClient (avoid circular import)
    ) -> None:
        self._pool = pool
        self._llm = llm

    async def store(
        self,
        content: str,
        category: str = "general",
        metadata: dict[str, Any] | None = None,
        conversation_id: str | None = None,
    ) -> int:
        """Embed content and store in pgvector.

        Args:
            content: Text to remember.
            category: Memory category (e.g. 'preference', 'fact', 'finding').
            metadata: Additional structured data.
            conversation_id: Source conversation ID.

        Returns:
            Memory ID (serial primary key).
        """
        if self._pool is None:
            logger.warning("MemoryStore: no pool — memory not persisted.")
            return -1

        # Generate embedding
        embeddings = await self._llm.embed([content])
        embedding_vec = embeddings[0]

        # Convert Python list to pgvector format
        embedding_str = "[" + ",".join(str(x) for x in embedding_vec) + "]"

        # Insert into agent_memory table
        row = await self._pool.fetchrow(
            """
            INSERT INTO agent_memory
                (content, category, embedding, metadata, source_conversation_id)
            VALUES ($1, $2, $3::vector, $4::jsonb, $5)
            RETURNING id
            """,
            content,
            category,
            embedding_str,
            json.dumps(metadata or {}),
            conversation_id,
        )

        memory_id: int = row["id"]  # type: ignore[index]
        logger.info(
            "Memory stored: id=%d, category=%s, content_len=%d",
            memory_id,
            category,
            len(content),
        )
        return memory_id

    async def recall(
        self,
        query: str,
        top_k: int = 5,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search: embed query, cosine similarity against stored memories.

        Args:
            query: Natural language query.
            top_k: Number of results to return.
            category: Optional category filter.

        Returns:
            List of memory dicts with keys: id, content, category, metadata,
            source_conversation_id, created_at, similarity.
        """
        if self._pool is None:
            logger.warning("MemoryStore: no pool — recall returns empty.")
            return []

        # Generate query embedding
        embeddings = await self._llm.embed([query])
        query_vec = embeddings[0]
        query_str = "[" + ",".join(str(x) for x in query_vec) + "]"

        # Build query with optional category filter
        if category:
            sql = """
                SELECT
                    id,
                    content,
                    category,
                    metadata,
                    source_conversation_id,
                    created_at,
                    1 - (embedding <=> $1::vector) AS similarity
                FROM agent_memory
                WHERE category = $2
                ORDER BY embedding <=> $1::vector
                LIMIT $3
            """
            rows = await self._pool.fetch(sql, query_str, category, top_k)
        else:
            sql = """
                SELECT
                    id,
                    content,
                    category,
                    metadata,
                    source_conversation_id,
                    created_at,
                    1 - (embedding <=> $1::vector) AS similarity
                FROM agent_memory
                ORDER BY embedding <=> $1::vector
                LIMIT $2
            """
            rows = await self._pool.fetch(sql, query_str, top_k)

        results = [dict(row) for row in rows]
        logger.info(
            "Memory recall: query_len=%d, category=%s, results=%d",
            len(query),
            category or "any",
            len(results),
        )
        return results

    async def forget(self, memory_id: int) -> bool:
        """Delete a specific memory by ID.

        Args:
            memory_id: Memory ID to delete.

        Returns:
            True if deleted, False if not found.
        """
        if self._pool is None:
            logger.warning("MemoryStore: no pool — forget no-op.")
            return False

        result = await self._pool.execute(
            "DELETE FROM agent_memory WHERE id = $1", memory_id
        )

        deleted = result == "DELETE 1"
        if deleted:
            logger.info("Memory forgotten: id=%d", memory_id)
        else:
            logger.warning("Memory not found for deletion: id=%d", memory_id)
        return deleted

    async def list_recent(
        self, limit: int = 20, category: str | None = None
    ) -> list[dict[str, Any]]:
        """List most recent memories.

        Args:
            limit: Number of memories to return.
            category: Optional category filter.

        Returns:
            List of memory dicts (same schema as recall).
        """
        if self._pool is None:
            logger.warning("MemoryStore: no pool — list returns empty.")
            return []

        if category:
            sql = """
                SELECT id, content, category, metadata, source_conversation_id, created_at
                FROM agent_memory
                WHERE category = $1
                ORDER BY created_at DESC
                LIMIT $2
            """
            rows = await self._pool.fetch(sql, category, limit)
        else:
            sql = """
                SELECT id, content, category, metadata, source_conversation_id, created_at
                FROM agent_memory
                ORDER BY created_at DESC
                LIMIT $1
            """
            rows = await self._pool.fetch(sql, limit)

        return [dict(row) for row in rows]
