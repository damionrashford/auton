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
    uv run uvicorn auton.app:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastmcp.utilities.lifespan import combine_lifespans

from auton.mcp import mcp

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
    title="Auton",
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
    from auton.mcp.dependencies import (
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


# ── Inbound webhook receiver ─────────────────────────────────────────


@app.post("/webhooks/{webhook_id}")
async def webhook_receiver(webhook_id: str, request: Request) -> JSONResponse:
    """Receive inbound webhooks with HMAC-SHA256 signature verification.

    External services POST to ``/webhooks/{webhook_id}`` with header
    ``X-Webhook-Signature: sha256=<hex_digest>`` for authentication.
    Returns 202 and processes the event asynchronously via the agent loop.
    """
    from auton.mcp.dependencies import get_db_pool
    from auton.webhooks.client import WebhookService

    try:
        pool = get_db_pool()
        if not pool:
            return JSONResponse({"error": "Database unavailable"}, status_code=503)

        # 1. Fetch subscription
        async with pool.acquire() as conn:
            sub = await conn.fetchrow(
                "SELECT id, webhook_url, signing_secret, agent_role, enabled "
                "FROM webhook_subscriptions WHERE id = $1",
                webhook_id,
            )

        if not sub:
            return JSONResponse({"error": "Not found"}, status_code=404)
        if not sub["enabled"]:
            return JSONResponse({"error": "Disabled"}, status_code=403)

        # 2. Verify signature
        body = await request.body()
        signature = request.headers.get("X-Webhook-Signature", "")
        sig_valid = WebhookService.verify_signature(body, signature, sub["signing_secret"])

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {"raw": body.decode("utf-8", errors="replace")}

        # 3. Log event
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO webhook_events "
                "(webhook_id, payload, headers, signature_valid, processed) "
                "VALUES ($1, $2, $3, $4, FALSE) RETURNING id",
                webhook_id,
                json.dumps(payload),
                json.dumps(dict(request.headers)),
                sig_valid,
            )
            event_id = row["id"] if row else 0

        if not sig_valid:
            logger.warning("Webhook signature invalid: %s event=%d", webhook_id, event_id)
            return JSONResponse({"error": "Invalid signature"}, status_code=401)

        # 4. Process asynchronously
        asyncio.create_task(
            _process_webhook_event(event_id, webhook_id, payload, sub["agent_role"])
        )

        return JSONResponse(
            {"status": "accepted", "event_id": event_id},
            status_code=202,
        )
    except RuntimeError:
        return JSONResponse({"error": "Not ready"}, status_code=503)
    except Exception:
        logger.exception("Webhook receiver error")
        return JSONResponse({"error": "Internal error"}, status_code=500)


async def _process_webhook_event(
    event_id: int,
    webhook_id: str,
    payload: dict[str, Any],
    agent_role: str,
) -> None:
    """Process an inbound webhook event via the agent loop (background task).

    Follows the same re-entry pattern as ``scheduler/service.py:_execute_job``.
    """
    from auton.agents.roles import AgentConfig, AgentRole
    from auton.core.agent import run_agent
    from auton.mcp.dependencies import (
        get_bridge,
        get_db_pool,
        get_llm,
        get_settings_dep,
        get_store,
    )

    conv_id = ""
    error_text = ""
    success = False

    try:
        bridge = get_bridge()
        llm = get_llm()
        store = get_store()
        settings = get_settings_dep()

        user_message = (
            f"Inbound webhook event received (webhook_id={webhook_id}):\n\n"
            + json.dumps(payload, indent=2)
        )

        config = AgentConfig(role=AgentRole(agent_role))
        resp = await run_agent(
            user_message=user_message,
            bridge=bridge,
            llm=llm,
            store=store,
            settings=settings,
            agent_config=config,
            conversation_id=f"webhook_{webhook_id}_{event_id}",
            ctx=None,
            headless=True,
        )
        success = True
        conv_id = resp.conversation_id
        logger.info("Webhook event processed: event=%d conv=%s", event_id, conv_id)
    except Exception as exc:
        error_text = str(exc)[:500]
        logger.exception("Webhook event processing failed: event=%d", event_id)

    # Update event status
    try:
        pool = get_db_pool()
        if pool:
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE webhook_events "
                    "SET processed=$1, agent_conversation_id=$2, error=$3, "
                    "processed_at=NOW() WHERE id=$4",
                    success,
                    conv_id if success else None,
                    error_text if not success else None,
                    event_id,
                )
    except Exception:
        logger.exception("Failed to update webhook event status")
