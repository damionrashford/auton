"""FastAPI + FastMCP ASGI composition.

This is the application entry-point for uvicorn deployments.  It:
  1. Creates a FastAPI app with custom HTTP endpoints (health, status).
  2. Mounts the FastMCP server (single chat tool) at ``/mcp``.
  3. Uses combine_lifespans (FastMCP 3.0) to merge the FastAPI and MCP
     server lifespans so Playwright, MCPBridge, LLM, Neon, and Redis
     all start.

The MCP server owns its lifecycle (via ``agent_lifespan`` in mcp/server.py),
so it also works standalone with ``fastmcp run``.

Playwright and Redis are required -- the agent will not start without them.
Neon Postgres and Slack Bolt are optional (graceful degradation).

Run with:
    uv run uvicorn fast_mcp_agent.app:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastmcp.utilities.lifespan import combine_lifespans

from fast_mcp_agent.mcp import mcp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

# ── Build the MCP ASGI sub-app (path="/" because we mount at /mcp) ─

mcp_app = mcp.http_app(path="/")


# ── FastAPI-specific lifespan ────────────────────────────────────────


@asynccontextmanager
async def app_lifespan(application: FastAPI) -> AsyncIterator[None]:
    """FastAPI-specific startup/shutdown (logging only for now)."""
    logger.info("FastAPI application starting.")
    yield
    logger.info("FastAPI application stopping.")


# ── Build the ASGI app ──────────────────────────────────────────────

app = FastAPI(
    title="FastMCP AI Agent",
    version="0.1.0",
    lifespan=combine_lifespans(app_lifespan, mcp_app.lifespan),
)

# Mount MCP server at /mcp
app.mount("/mcp", mcp_app)


# ── Custom HTTP endpoints ───────────────────────────────────────────


@app.get("/health")
async def health() -> JSONResponse:
    """Liveness probe."""
    return JSONResponse({"status": "ok"})


@app.get("/api/status")
async def api_status() -> JSONResponse:
    """Rich status endpoint for monitoring."""
    from fast_mcp_agent.mcp.dependencies import (
        get_bridge,
        get_db_pool,
        get_settings_dep,
        get_store,
    )

    try:
        bridge = get_bridge()
        settings = get_settings_dep()
        store = get_store()

        # Check Neon pool health
        neon_connected = False
        try:
            pool = get_db_pool()
            neon_connected = pool is not None and not pool._closed
        except RuntimeError:
            pass

        # Conversation count (async)
        try:
            conv_ids = await store.list_ids()
            conversation_count = len(conv_ids)
        except Exception:
            conversation_count = 0

        return JSONResponse(
            {
                "status": "ok",
                "connected_servers": bridge.connected_servers,
                "available_tools": len(bridge.list_tool_names()),
                "model": settings.xai_model,
                "conversations": conversation_count,
                "neon_connected": neon_connected,
                "slack_connected": "slack" in bridge.internal_tool_sources,
            }
        )
    except RuntimeError:
        return JSONResponse({"status": "starting"}, status_code=503)
