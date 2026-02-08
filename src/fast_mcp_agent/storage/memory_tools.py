"""Internal tools for long-term semantic memory.

Exposes three tools to the LLM:
  - memory_store: Save a fact/preference/finding for future reference.
  - memory_recall: Semantically search memories by natural language query.
  - memory_forget: Remove a memory by ID.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Tool schemas in OpenAI function-calling format
MEMORY_TOOLS: list[dict[str, Any]] = [
    {
        "name": "memory_store",
        "description": (
            "Save information to long-term memory for future reference. "
            "Use this to remember facts, user preferences, important findings, "
            "or insights that should persist across conversations."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The information to remember (plain text).",
                },
                "category": {
                    "type": "string",
                    "description": (
                        "Memory category: 'preference', 'fact', 'finding', "
                        "'insight', 'general'. Defaults to 'general'."
                    ),
                },
                "metadata": {
                    "type": "object",
                    "description": "Optional structured metadata (JSON object).",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "memory_recall",
        "description": (
            "Search long-term memory using a natural language query. "
            "Returns the top K most semantically similar memories."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (default 5, max 20).",
                },
                "category": {
                    "type": "string",
                    "description": "Optional category filter.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "memory_forget",
        "description": "Delete a specific memory by its ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "memory_id": {
                    "type": "integer",
                    "description": "The ID of the memory to delete.",
                },
            },
            "required": ["memory_id"],
        },
    },
]


async def handle_memory_tool(
    memory_store: Any,  # MemoryStore instance
    conversation_id: str | None,
    tool_name: str,
    args: dict[str, Any],
) -> str:
    """Route a memory tool call to the correct MemoryStore method.

    Args:
        memory_store: MemoryStore instance.
        conversation_id: Current conversation ID (for source tracking).
        tool_name: Tool name (memory_store, memory_recall, memory_forget).
        args: Tool arguments.

    Returns:
        Result text (formatted for LLM consumption).
    """
    try:
        if tool_name == "memory_store":
            content = args.get("content", "")
            category = args.get("category", "general")
            metadata = args.get("metadata")

            if not content:
                return "[error] memory_store: 'content' is required."

            memory_id = await memory_store.store(
                content=content,
                category=category,
                metadata=metadata,
                conversation_id=conversation_id,
            )

            return (
                f"✓ Memory stored successfully.\n"
                f"  ID: {memory_id}\n"
                f"  Category: {category}\n"
                f"  Content: {content[:100]}{'...' if len(content) > 100 else ''}"
            )

        if tool_name == "memory_recall":
            query = args.get("query", "")
            top_k = args.get("top_k", 5)
            category = args.get("category")

            if not query:
                return "[error] memory_recall: 'query' is required."

            # Clamp top_k
            top_k = max(1, min(top_k, 20))

            results = await memory_store.recall(
                query=query, top_k=top_k, category=category
            )

            if not results:
                return f"No memories found for query: '{query}'"

            # Format results
            lines = [f"Found {len(results)} relevant memories:\n"]
            for i, mem in enumerate(results, 1):
                similarity = mem.get("similarity", 0.0)
                lines.append(
                    f"{i}. [ID: {mem['id']}, Similarity: {similarity:.2f}] "
                    f"{mem['category']}: {mem['content'][:150]}"
                    f"{'...' if len(mem['content']) > 150 else ''}"
                )
                if mem.get("metadata"):
                    lines.append(f"   Metadata: {json.dumps(mem['metadata'])}")

            return "\n".join(lines)

        if tool_name == "memory_forget":
            memory_id = args.get("memory_id")

            if memory_id is None:
                return "[error] memory_forget: 'memory_id' is required."

            deleted = await memory_store.forget(memory_id)

            if deleted:
                return f"✓ Memory {memory_id} deleted successfully."
            return f"[error] Memory {memory_id} not found."

        return f"[error] Unknown memory tool: {tool_name}"

    except Exception as exc:
        logger.exception("Memory tool call failed: %s", tool_name)
        return f"[error] Memory tool '{tool_name}' failed: {exc}"
