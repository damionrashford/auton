"""Pydantic data models shared across the application."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ── OpenAI-compatible chat completion types ────────────────────────


class ChatRole(StrEnum):
    """Roles in an OpenAI-style chat conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ChatMessage(BaseModel):
    """A single message in the conversation history."""

    role: ChatRole
    content: str | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCallPayload] | None = None
    reasoning: str | None = None  # OpenRouter reasoning tokens


class FunctionPayload(BaseModel):
    """The function portion of an OpenAI tool-call."""

    name: str
    arguments: str  # JSON-encoded string


class ToolCallPayload(BaseModel):
    """A single tool call returned by the LLM."""

    id: str
    type: str = "function"
    function: FunctionPayload


# ── OpenAI function-calling schema ─────────────────────────────────


class FunctionSchema(BaseModel):
    """Schema for a single function in the OpenAI tools array."""

    name: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


class ToolSchema(BaseModel):
    """Wrapper matching the OpenAI ``tools`` array element."""

    type: str = "function"
    function: FunctionSchema


# ── OpenRouter usage accounting ────────────────────────────────────


class UsageStats(BaseModel):
    """Token usage and cost information from an OpenRouter response.

    Fields map directly to the ``usage`` object in the OpenRouter API
    response.  All fields are optional because some providers omit them.
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float | None = None
    reasoning_tokens: int = 0
    cached_tokens: int = 0
    cache_write_tokens: int = 0

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> UsageStats:
        """Extract usage stats from a raw OpenRouter response dict."""
        usage = data.get("usage")
        if not usage:
            return cls()

        completion_details = usage.get("completion_tokens_details") or {}
        prompt_details = usage.get("prompt_tokens_details") or {}

        return cls(
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            cost=usage.get("cost"),
            reasoning_tokens=completion_details.get("reasoning_tokens", 0),
            cached_tokens=prompt_details.get("cached_tokens", 0),
            cache_write_tokens=prompt_details.get("cache_write_tokens", 0),
        )


# ── Agent status ───────────────────────────────────────────────────


class AgentStatus(BaseModel):
    """Runtime status of the AI agent."""

    connected_servers: list[str] = Field(default_factory=list)
    available_tools: int = 0
    model: str = ""
    max_iterations: int = 25
    playwright_running: bool = False
    neon_connected: bool = False
    slack_connected: bool = False
    google_workspace_connected: bool = False
    cron_enabled: bool = False
    internal_tool_sources: list[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    """Incoming chat request from an MCP client."""

    message: str
    conversation_id: str | None = None


class DelegationSummary(BaseModel):
    """Summary of a single delegation from orchestrator to specialist."""

    task_id: str
    target_role: str
    instruction: str
    success: bool
    iterations_used: int = 0
    tools_called: list[str] = Field(default_factory=list)
    cost: float = 0.0


class ChatResponse(BaseModel):
    """Response returned by the chat tool."""

    reply: str
    conversation_id: str
    iterations_used: int = 0
    tools_called: list[str] = Field(default_factory=list)
    model_used: str = ""
    usage: UsageStats = Field(default_factory=UsageStats)
    # Multi-agent fields
    delegations: list[DelegationSummary] = Field(default_factory=list)
    agent_role: str = ""


# Forward-ref resolution (ChatMessage references ToolCallPayload)
ChatMessage.model_rebuild()
