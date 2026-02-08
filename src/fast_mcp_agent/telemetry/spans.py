"""Custom OpenTelemetry span helpers for agent operations.

Uses ``fastmcp.telemetry.get_tracer()`` which returns a no-op tracer when
no OpenTelemetry SDK is configured, so these are safe to call unconditionally.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

try:
    from fastmcp.telemetry import get_tracer

    _tracer = get_tracer(version="0.1.0")

    @contextmanager  # type: ignore[arg-type]
    def trace_llm_call(model: str, message_count: int):
        """Create an OTEL span around an LLM chat completion call."""
        with _tracer.start_as_current_span(
            "llm.chat_completion",
            attributes={
                "llm.model": model,
                "llm.message_count": message_count,
                "llm.provider": "xai",
            },
        ) as span:
            yield span

    @contextmanager  # type: ignore[arg-type]
    def trace_tool_call(tool_name: str, arguments: dict[str, Any]):
        """Create an OTEL span around an MCP tool call."""
        with _tracer.start_as_current_span(
            f"tool.call.{tool_name}",
            attributes={
                "tool.name": tool_name,
                "tool.arguments": str(arguments)[:500],
            },
        ) as span:
            yield span

except ImportError:
    # FastMCP telemetry or OTEL not available -- provide no-op fallbacks.

    @contextmanager  # type: ignore[arg-type]
    def trace_llm_call(model: str, message_count: int):
        """No-op span when OTEL is not installed."""
        yield None

    @contextmanager  # type: ignore[arg-type]
    def trace_tool_call(tool_name: str, arguments: dict[str, Any]):
        """No-op span when OTEL is not installed."""
        yield None
