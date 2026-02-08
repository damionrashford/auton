"""FastMCP middleware configuration.

Wires up the built-in Timing, Logging, Error-Handling, and Response-Caching
middleware with Redis as the caching backend.

Uses FastMCP 3.0 middleware system.
"""

from __future__ import annotations

import logging

from fastmcp import FastMCP
from fastmcp.server.middleware.caching import CallToolSettings, ResponseCachingMiddleware
from fastmcp.server.middleware.error_handling import ErrorHandlingMiddleware
from fastmcp.server.middleware.logging import LoggingMiddleware
from fastmcp.server.middleware.timing import TimingMiddleware
from key_value.aio.stores.redis import RedisStore
from key_value.aio.wrappers.prefix_collections import PrefixCollectionsWrapper

from fast_mcp_agent.config import get_settings

logger = logging.getLogger(__name__)


def attach_middleware(mcp: FastMCP) -> None:
    """Register all standard middleware on *mcp*.

    Order matters -- middleware executes outermost-first:
      1. ErrorHandlingMiddleware (outermost -- catches all errors)
      2. TimingMiddleware        (captures total wall time)
      3. LoggingMiddleware       (logs request/response payloads)
      4. ResponseCachingMiddleware (innermost -- serves cached responses via Redis)
    """
    settings = get_settings()

    mcp.add_middleware(ErrorHandlingMiddleware())
    mcp.add_middleware(TimingMiddleware())
    mcp.add_middleware(
        LoggingMiddleware(
            include_payloads=True,
            max_payload_length=2000,
        )
    )

    # Redis-backed response caching
    redis_store = RedisStore(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
    )
    namespaced_store = PrefixCollectionsWrapper(
        key_value=redis_store,
        prefix="fast-mcp-agent",
    )
    mcp.add_middleware(
        ResponseCachingMiddleware(
            cache_storage=namespaced_store,
            call_tool_settings=CallToolSettings(
                excluded_tools=["chat"],
            ),
        )
    )

    logger.info(
        "Middleware attached: ErrorHandling + Timing + Logging + Redis Cache (%s:%d/%d)",
        settings.redis_host,
        settings.redis_port,
        settings.redis_db,
    )
