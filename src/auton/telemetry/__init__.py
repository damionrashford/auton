"""OpenTelemetry instrumentation (optional).

Re-exports span helpers that gracefully no-op when the OTEL SDK
is not installed or configured.
"""

from auton.telemetry.spans import trace_llm_call, trace_tool_call

__all__ = ["trace_llm_call", "trace_tool_call"]
