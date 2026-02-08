"""Dependency injection factories for FastMCP tools.

Provides Depends()-compatible factories that resolve to the shared
singletons initialised during the server lifespan.  These are used
by ``@mcp.tool`` and ``@mcp.resource`` via ``Depends(get_bridge)`` etc.

Dependency parameters are automatically excluded from the MCP schema,
so clients never see them as callable parameters.
"""

from __future__ import annotations

from typing import Any

import asyncpg

from auton.bridge import MCPBridge
from auton.config import Settings
from auton.core.llm import LLMClient

# ── Module-level singletons (set once during lifespan startup) ─────

_bridge: MCPBridge | None = None
_llm: LLMClient | None = None
_store: Any | None = None  # NeonConversationStore or _InMemoryShim
_settings: Settings | None = None
_db_pool: asyncpg.Pool | None = None
_memory_store: Any | None = None  # MemoryStore
_orchestrator: Any | None = None  # OrchestratorAgent
_registry: Any | None = None  # AgentRegistry


def set_singletons(
    bridge: MCPBridge,
    llm: LLMClient,
    store: Any,
    settings: Settings,
    db_pool: asyncpg.Pool | None = None,
    memory_store: Any | None = None,
    orchestrator: Any | None = None,
    registry: Any | None = None,
) -> None:
    """Inject runtime singletons (called once during lifespan startup)."""
    global _bridge, _llm, _store, _settings, _db_pool, _memory_store  # noqa: PLW0603
    global _orchestrator, _registry  # noqa: PLW0603
    _bridge = bridge
    _llm = llm
    _store = store
    _settings = settings
    _db_pool = db_pool
    _memory_store = memory_store
    _orchestrator = orchestrator
    _registry = registry


# ── Depends() factories ───────────────────────────────────────────


def get_bridge() -> MCPBridge:
    """Return the connected MCPBridge instance."""
    if _bridge is None:
        raise RuntimeError("MCPBridge not initialised (server still starting?)")
    return _bridge


def get_llm() -> LLMClient:
    """Return the LLMClient instance."""
    if _llm is None:
        raise RuntimeError("LLMClient not initialised (server still starting?)")
    return _llm


def get_store() -> Any:
    """Return the conversation store instance (Neon or in-memory shim)."""
    if _store is None:
        raise RuntimeError("Conversation store not initialised (server still starting?)")
    return _store


def get_settings_dep() -> Settings:
    """Return the Settings instance."""
    if _settings is None:
        raise RuntimeError("Settings not initialised (server still starting?)")
    return _settings


def get_db_pool() -> asyncpg.Pool:
    """Return the asyncpg connection pool."""
    if _db_pool is None:
        raise RuntimeError("Database pool not initialised (server still starting?)")
    return _db_pool


def get_memory_store() -> Any | None:
    """Return the MemoryStore instance (may be None if not configured)."""
    return _memory_store


def get_orchestrator() -> Any:
    """Return the OrchestratorAgent instance."""
    if _orchestrator is None:
        raise RuntimeError("OrchestratorAgent not initialised (server still starting?)")
    return _orchestrator


def get_registry() -> Any:
    """Return the AgentRegistry instance."""
    if _registry is None:
        raise RuntimeError("AgentRegistry not initialised (server still starting?)")
    return _registry
