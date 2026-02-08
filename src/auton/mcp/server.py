"""FastMCP server definition -- single chat tool with composable lifespan.

This module creates and configures the FastMCP server instance.  It exposes
exactly ONE tool to external MCP clients:

Tool
  chat -- send a message to the AI agent, which internally uses
         RivalSearchMCP, Playwright MCP, Google Workspace MCP,
         Slack Bolt, and Cron Scheduler to answer your question.

Everything else (web search, browser automation, Slack, Google Workspace,
cron scheduling, tool routing, conversation management) is internal to
the agent and never exposed through MCP.

The server carries its own lifespan (via FastMCP 3.0 composable @lifespan)
so it works both:
  - Standalone via ``fastmcp run`` / ``fastmcp dev``
  - Mounted inside a FastAPI app via ``app.py``

FastMCP 3.0 features used:
  - Composable @lifespan with yield context
  - CurrentContext() dependency injection
  - Depends() for runtime singletons
  - ctx.report_progress() for long-running progress updates
  - Tool timeout (foreground protection)
  - Session-scoped state (conversation persistence across requests)
  - Pagination (list_page_size=50)
  - Redis-backed session state store
  - ErrorHandlingMiddleware
  - OpenTelemetry tracing (via telemetry/)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastmcp import Context, FastMCP
from fastmcp.dependencies import CurrentContext, Depends
from fastmcp.server.lifespan import lifespan
from key_value.aio.stores.redis import RedisStore

from auton.bridge import MCPBridge, PlaywrightProcess
from auton.config import Settings, get_settings
from auton.core.llm import LLMClient
from auton.mcp.dependencies import (
    get_bridge,
    get_memory_store,
    get_settings_dep,
    set_singletons,
)
from auton.mcp.middleware import attach_middleware
from auton.models import AgentStatus
from auton.storage import NeonConversationStore, create_pool, run_migrations

logger = logging.getLogger(__name__)


# ── Composable lifespan (FastMCP 3.0) ──────────────────────────────


@lifespan
async def agent_lifespan(server: FastMCP):
    """Start Playwright, connect MCP bridge, start LLM client.

    This runs during server startup (both ``fastmcp run`` and FastAPI mount)
    and tears everything down on shutdown.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    settings = get_settings()
    logger.info("Configuration loaded: model=%s", settings.xai_model)

    # 0a. Check Redis connectivity (non-blocking).
    try:
        _redis_check = RedisStore(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
        )
        # Attempt a simple operation to verify connectivity
        await _redis_check.get(key="__health_check__")
        logger.info("Redis connected: %s:%d", settings.redis_host, settings.redis_port)
    except Exception as _redis_exc:
        logger.warning(
            "Redis health check failed (%s:%d): %s. "
            "Response caching and session state may not work.",
            settings.redis_host,
            settings.redis_port,
            _redis_exc,
        )

    # 0. Create Neon Postgres connection pool and run migrations.
    pool = None
    if settings.neon_database_url:
        pool = await create_pool(settings.neon_database_url)
        await run_migrations(pool)
        logger.info("Neon Postgres connected and schema migrated.")
    else:
        logger.warning(
            "NEON_DATABASE_URL not set. "
            "Conversations will NOT be persisted across restarts."
        )

    # 1. Start Playwright MCP subprocess (required).
    pw = PlaywrightProcess(settings)
    await pw.start()
    logger.info("Playwright MCP subprocess running (port %d).", settings.playwright_mcp_port)

    # 2. Start LLM client.
    llm = LLMClient(settings)
    await llm.start()

    # 3. Create Neon-backed conversation store.
    if pool is not None:
        store = NeonConversationStore(pool=pool)
    else:
        # Fallback: in-memory store if no Postgres URL configured.
        from auton.core.conversation import ConversationStore as _InMemStore

        store = _InMemoryShim(_InMemStore())  # type: ignore[assignment]
        logger.warning("Using in-memory conversation store (no Neon).")

    # 4. Connect MCP bridge to RivalSearchMCP + Playwright MCP + Google Workspace MCP.
    bridge = MCPBridge(settings)
    await bridge.connect()
    logger.info(
        "MCPBridge connected: servers=%s, tools=%d",
        bridge.connected_servers,
        len(bridge.list_tool_names()),
    )

    # 5. Initialize Slack Bolt (optional).
    slack_service = None
    if settings.slack_enabled and settings.slack_bot_token:
        try:
            from auton.slack.client import SlackService

            slack_service = SlackService(bot_token=settings.slack_bot_token)
            await slack_service.start()
            if slack_service.is_connected:
                from auton.slack.tools import SLACK_TOOLS, handle_slack_tool

                bridge.register_internal_tools(
                    SLACK_TOOLS,
                    handler=lambda name, args: handle_slack_tool(slack_service, name, args),
                    source="slack",
                )
                logger.info("Slack Bolt: %d tools registered.", len(SLACK_TOOLS))
            else:
                logger.warning("Slack Bolt: auth failed, continuing without Slack.")
                slack_service = None
        except ImportError:
            logger.warning(
                "slack-sdk not installed. Install with: pip install slack-sdk. "
                "Continuing without Slack."
            )
        except Exception:
            logger.warning("Slack Bolt initialization failed.", exc_info=True)
    else:
        logger.info("Slack Bolt: skipped (not configured or disabled).")

    # 6. Initialize Cron Scheduler (optional).
    cron_scheduler = None
    if settings.cron_enabled:
        try:
            from auton.scheduler.service import CronSchedulerService

            cron_scheduler = CronSchedulerService(
                pool=pool,
                timezone=settings.cron_timezone,
            )
            await cron_scheduler.start()

            if cron_scheduler.is_running:
                from auton.scheduler.tools import CRON_TOOLS, handle_cron_tool

                bridge.register_internal_tools(
                    CRON_TOOLS,
                    handler=lambda name, args: handle_cron_tool(cron_scheduler, name, args),
                    source="cron",
                )
                logger.info("Cron Scheduler: %d tools registered.", len(CRON_TOOLS))
            else:
                logger.warning("Cron Scheduler: failed to start (missing APScheduler?).")
                cron_scheduler = None
        except ImportError:
            logger.warning(
                "APScheduler not installed. Install with: pip install apscheduler. "
                "Continuing without cron."
            )
        except Exception:
            logger.warning("Cron Scheduler initialization failed.", exc_info=True)
    else:
        logger.info("Cron Scheduler: skipped (disabled).")

    # 7. Initialize Memory Store (requires Neon Postgres).
    memory_store = None
    if pool is not None:
        try:
            from auton.storage.memory import MemoryStore

            memory_store = MemoryStore(pool=pool, llm=llm)

            from auton.storage.memory_tools import MEMORY_TOOLS, handle_memory_tool

            # Memory tools need conversation_id, so we wrap the handler
            def memory_handler(name: str, args: dict) -> Any:
                # Extract conversation_id from current context if available
                # For now, pass None and let the handler deal with it
                return handle_memory_tool(memory_store, None, name, args)

            bridge.register_internal_tools(
                MEMORY_TOOLS,
                handler=memory_handler,
                source="memory",
            )
            logger.info("Memory Store: %d tools registered.", len(MEMORY_TOOLS))
        except Exception:
            logger.warning("Memory Store initialization failed.", exc_info=True)
    else:
        logger.info("Memory Store: skipped (requires Neon Postgres).")

    # 7b. Initialize Coinbase AgentKit blockchain tools (optional).
    if settings.blockchain_enabled and settings.cdp_api_key_id:
        try:
            from auton.blockchain import (
                BLOCKCHAIN_TOOLS,
                BlockchainService,
                handle_blockchain_tool,
            )

            blockchain_svc = BlockchainService(
                network=settings.blockchain_network,
                cdp_api_key_id=settings.cdp_api_key_id,
                cdp_api_key_secret=settings.cdp_api_key_secret,
                cdp_wallet_secret=settings.cdp_wallet_secret,
            )
            await blockchain_svc.start()
            if blockchain_svc.is_connected:
                bridge.register_internal_tools(
                    BLOCKCHAIN_TOOLS,
                    handler=lambda name, args: handle_blockchain_tool(
                        blockchain_svc, name, args
                    ),
                    source="blockchain",
                )
                logger.info(
                    "Blockchain: %d tools registered.",
                    len(BLOCKCHAIN_TOOLS),
                )
            else:
                logger.warning("Blockchain: AgentKit init failed.")
        except ImportError:
            logger.warning(
                "coinbase-agentkit not installed. "
                "Install with: pip install coinbase-agentkit"
            )
        except Exception:
            logger.warning(
                "Blockchain initialization failed.",
                exc_info=True,
            )
    else:
        logger.info("Blockchain: skipped (not configured).")

    # 8. Inject dependencies into cron scheduler for agent loop execution.
    if cron_scheduler is not None:
        # Pass Slack client for cron result notifications
        slack_web = (
            slack_service.web_client
            if slack_service and slack_service.is_connected
            else None
        )
        cron_scheduler.set_job_dependencies(
            bridge=bridge,
            llm=llm,
            store=store,
            settings=settings,
            slack_client=slack_web,
        )

    # 9. Initialize multi-agent orchestrator.
    from auton.agents.orchestrator import OrchestratorAgent
    from auton.agents.registry import AgentRegistry
    from auton.agents.tools import DELEGATION_TOOLS, make_delegation_handler

    registry = AgentRegistry(settings)

    # The parent_conversation_id is set dynamically per-request via mutable ref
    _parent_cid_ref: list[str] = [""]

    orchestrator = OrchestratorAgent(
        bridge=bridge,
        llm=llm,
        store=store,
        settings=settings,
        registry=registry,
    )

    # Register delegation tools on the bridge (orchestrator-only tools)
    delegation_handler = make_delegation_handler(orchestrator, _parent_cid_ref)
    bridge.register_internal_tools(
        DELEGATION_TOOLS,
        handler=delegation_handler,
        source="multi_agent",
    )
    logger.info(
        "Multi-agent orchestrator initialized: %d delegation tools.",
        len(DELEGATION_TOOLS),
    )

    # 10. Inject singletons for DI resolution.
    set_singletons(
        bridge=bridge,
        llm=llm,
        store=store,
        settings=settings,
        db_pool=pool,
        memory_store=memory_store,
        orchestrator=orchestrator,
        registry=registry,
    )

    # 11. Start Slack Bolt UI (Socket Mode) — makes Slack the primary interface.
    slack_bolt_ui = None
    if (
        settings.slack_enabled
        and settings.slack_bot_token
        and settings.slack_app_token
    ):
        try:
            from auton.slack.bolt_app import SlackBoltUI

            slack_bolt_ui = SlackBoltUI(
                bot_token=settings.slack_bot_token,
                app_token=settings.slack_app_token,
                orchestrator=orchestrator,
                memory_store=memory_store,
            )
            await slack_bolt_ui.start()
            if slack_bolt_ui.is_running:
                logger.info("Slack Bolt UI: listening via Socket Mode.")
            else:
                logger.warning("Slack Bolt UI: failed to start.")
                slack_bolt_ui = None
        except ImportError:
            logger.warning(
                "slack-bolt not installed. Install with: pip install slack-bolt. "
                "Slack UI will not be available."
            )
        except Exception:
            logger.warning("Slack Bolt UI initialization failed.", exc_info=True)
    else:
        if not settings.slack_app_token:
            logger.info(
                "Slack Bolt UI: skipped (SLACK_APP_TOKEN not set — "
                "needed for Socket Mode)."
            )
        else:
            logger.info("Slack Bolt UI: skipped (Slack not enabled).")

    logger.info(
        "Agent ready. Orchestrator-worker system active. "
        "Total tools available: %d (MCP: %d, internal: %s). "
        "Slack UI: %s.",
        len(bridge.list_tool_names()),
        len(bridge.list_tool_names()) - len(bridge._internal_tools),
        bridge.internal_tool_sources,
        "active" if slack_bolt_ui else "disabled",
    )

    yield {
        "settings": settings,
        "pw": pw,
        "llm": llm,
        "store": store,
        "bridge": bridge,
        "pool": pool,
        "slack_service": slack_service,
        "slack_bolt_ui": slack_bolt_ui,
        "cron_scheduler": cron_scheduler,
        "memory_store": memory_store,
        "orchestrator": orchestrator,
        "registry": registry,
    }

    # ── Shutdown ────────────────────────────────────────────────
    logger.info("Shutting down agent...")

    # Stop Slack Bolt UI
    if slack_bolt_ui is not None:
        await slack_bolt_ui.stop()

    # Stop cron scheduler
    if cron_scheduler is not None:
        await cron_scheduler.stop()

    # Stop Slack outbound service
    if slack_service is not None:
        await slack_service.stop()

    await bridge.disconnect()
    await llm.stop()
    await pw.stop()
    if pool is not None:
        await pool.close()
        logger.info("Neon Postgres pool closed.")
    logger.info("Shutdown complete.")


# ── In-memory shim (fallback when Neon is not configured) ──────────


class _InMemoryShim:
    """Async wrapper around the sync ConversationStore for fallback use."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def get_or_create(
        self,
        conversation_id: Any = None,
        **_kwargs: Any,
    ) -> Any:
        return self._inner.get_or_create(conversation_id)

    async def append(self, conversation_id: Any, message: Any) -> None:
        self._inner.append(conversation_id, message)

    async def clear(self, conversation_id: Any) -> Any:
        return self._inner.clear(conversation_id)

    async def clear_all(self) -> Any:
        return self._inner.clear_all()

    async def list_ids(self) -> Any:
        return self._inner.list_ids()

    async def log_tool_call(self, **kwargs: Any) -> None:
        pass  # no-op for in-memory store

    async def log_usage(self, **kwargs: Any) -> None:
        pass  # no-op for in-memory store

    async def log_decision(
        self,
        conversation_id: str,
        iteration: int,
        event_type: str,
        details: dict[str, Any],
    ) -> None:
        pass  # no-op for in-memory store

    async def get_daily_cost(self) -> float:
        return 0.0  # no-op for in-memory store

    async def get_conversation_cost(self, conversation_id: str) -> float:
        return 0.0  # no-op for in-memory store

    # Delegation tracking — no-ops for in-memory store
    async def log_delegation(self, **kwargs: Any) -> int:
        return -1

    async def update_delegation_result(self, **kwargs: Any) -> None:
        pass

    async def get_delegation_history(self, conversation_id: str) -> list[Any]:
        return []


# ── Lazy settings initialization ────────────────────────────────────

_init_settings: Settings | None = None


def _get_init_settings() -> Settings:
    """Lazy initialization of settings for server construction."""
    global _init_settings  # noqa: PLW0603
    if _init_settings is None:
        _init_settings = get_settings()
    return _init_settings


# ── Create the FastMCP server ───────────────────────────────────────

mcp = FastMCP(
    name="Auton",
    instructions=(
        "This server exposes a single 'chat' tool. Send any message and "
        "the agent will autonomously search the web (via RivalSearchMCP), "
        "browse pages (via Playwright MCP), interact with Google Workspace "
        "(Gmail, Drive, Calendar, Sheets, Docs), communicate via Slack, "
        "and manage scheduled tasks (cron) to answer your question. "
        "Use 'conversation_id' from a previous response to continue a "
        "multi-turn conversation."
    ),
    version="0.1.0",
    lifespan=agent_lifespan,
    list_page_size=50,
    session_state_store=RedisStore(
        host=_get_init_settings().redis_host,
        port=_get_init_settings().redis_port,
        db=_get_init_settings().redis_session_db,
    ),
)

# Wire up middleware (Error -> Timing -> Logging -> Redis-backed Caching).
attach_middleware(mcp)


# ═══════════════════════════════════════════════════════════════════
#  SINGLE EXPOSED TOOL — routes through multi-agent orchestrator
# ═══════════════════════════════════════════════════════════════════


@mcp.tool(
    timeout=float(_get_init_settings().multi_agent_orchestrator_timeout),
    tags={"agent", "chat", "multi-agent"},
    annotations={
        "title": "Chat with AI Agent",
        "readOnlyHint": False,
        "openWorldHint": True,
    },
)
async def chat(
    message: str,
    conversation_id: str | None = None,
    ctx: Context = CurrentContext(),
    memory_store: Any = Depends(get_memory_store),
) -> dict[str, Any]:
    """Send a message to the multi-agent AI system.

    The orchestrator decomposes your request and delegates subtasks to
    specialist agents (research, browser, communication, workspace).
    Results are synthesised into a single coherent response.

    Args:
        message: Your query or instruction.
        conversation_id: Optional ID to continue an existing conversation.

    Returns:
        A dict with 'reply', 'conversation_id', 'delegations', etc.
    """
    from auton.mcp.dependencies import get_orchestrator

    orchestrator = get_orchestrator()

    await ctx.info(f"Chat request: {message[:120]}")

    # Session-scoped conversation: if no ID given, resume session conversation.
    if conversation_id is None:
        conversation_id = await ctx.get_state("conversation_id")

    resp = await orchestrator.run(
        user_message=message,
        conversation_id=conversation_id,
        ctx=ctx,
        memory_store=memory_store,
    )

    # Persist conversation ID in session state for follow-up calls.
    await ctx.set_state("conversation_id", resp.conversation_id)

    return resp.model_dump()


# ═══════════════════════════════════════════════════════════════════
#  RESOURCES
# ═══════════════════════════════════════════════════════════════════


@mcp.resource(
    "agent://status",
    name="Agent Status",
    description="Live status of the AI agent including connections and model info.",
    mime_type="application/json",
    tags={"status"},
)
async def agent_status(
    ctx: Context = CurrentContext(),
    bridge: MCPBridge = Depends(get_bridge),
    settings: Settings = Depends(get_settings_dep),
) -> str:
    """Return the current agent status as JSON."""
    status = AgentStatus(
        connected_servers=bridge.connected_servers,
        available_tools=len(bridge.list_tool_names()),
        model=settings.xai_model,
        max_iterations=settings.max_iterations,
        playwright_running=True,
        neon_connected=bool(settings.neon_database_url),
        slack_connected="slack" in bridge.internal_tool_sources,
        google_workspace_connected="GoogleWorkspaceMCP" in bridge.connected_servers,
        cron_enabled="cron" in bridge.internal_tool_sources,
        internal_tool_sources=bridge.internal_tool_sources,
    )
    return status.model_dump_json(indent=2)


@mcp.resource(
    "agent://tools",
    name="Available Tools",
    description="List of all tool names accessible through the MCP bridge.",
    mime_type="application/json",
    tags={"tools"},
)
async def agent_tools(
    bridge: MCPBridge = Depends(get_bridge),
) -> str:
    """Return all available tool names as a JSON array."""
    names = bridge.list_tool_names()
    return json.dumps(names, indent=2)
