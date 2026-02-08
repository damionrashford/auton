"""In-memory conversation state management.

Stores chat histories keyed by conversation ID so that multi-turn
sessions work correctly across MCP tool invocations.
"""

from __future__ import annotations

import uuid
from collections import OrderedDict

from fast_mcp_agent.core.prompts import SYSTEM_PROMPT
from fast_mcp_agent.models import ChatMessage, ChatRole

# Maximum number of concurrent conversations held in memory.
_MAX_CONVERSATIONS = 200


class ConversationStore:
    """Thread-safe, LRU-bounded conversation history store."""

    def __init__(self, max_size: int = _MAX_CONVERSATIONS) -> None:
        self._store: OrderedDict[str, list[ChatMessage]] = OrderedDict()
        self._max_size = max_size

    # ── public API ──────────────────────────────────────────────────

    def get_or_create(
        self,
        conversation_id: str | None = None,
    ) -> tuple[str, list[ChatMessage]]:
        """Return an existing conversation or bootstrap a new one.

        Returns:
            (conversation_id, messages) tuple.
        """
        if conversation_id and conversation_id in self._store:
            # Move to end (most-recently-used)
            self._store.move_to_end(conversation_id)
            return conversation_id, self._store[conversation_id]

        cid = conversation_id or uuid.uuid4().hex[:12]
        messages: list[ChatMessage] = [
            ChatMessage(role=ChatRole.SYSTEM, content=SYSTEM_PROMPT),
        ]
        self._store[cid] = messages
        self._evict()
        return cid, messages

    def append(self, conversation_id: str, message: ChatMessage) -> None:
        """Append a message to the specified conversation."""
        if conversation_id in self._store:
            self._store[conversation_id].append(message)

    def clear(self, conversation_id: str) -> bool:
        """Delete a conversation.  Returns True if it existed."""
        return self._store.pop(conversation_id, None) is not None

    def clear_all(self) -> int:
        """Delete every conversation.  Returns the count removed."""
        count = len(self._store)
        self._store.clear()
        return count

    def list_ids(self) -> list[str]:
        """Return all active conversation IDs."""
        return list(self._store.keys())

    # ── internals ───────────────────────────────────────────────────

    def _evict(self) -> None:
        """Remove the oldest conversations when the store exceeds capacity."""
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)
