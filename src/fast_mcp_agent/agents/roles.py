"""Agent role definitions and configuration models for the multi-agent system.

Every ``run_agent()`` call requires an ``AgentConfig`` that determines which
tools the agent can access, its system prompt, and iteration limits.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Async callback: (tool_name, args) -> bool (True = approved)
ConfirmationCallback = Callable[[str, dict[str, Any]], Awaitable[bool]]


class AgentRole(StrEnum):
    """Roles in the orchestrator-worker multi-agent system."""

    ORCHESTRATOR = "orchestrator"
    RESEARCH = "research"
    BROWSER = "browser"
    COMMUNICATION = "communication"
    WORKSPACE = "workspace"
    BLOCKCHAIN = "blockchain"


class AgentConfig(BaseModel):
    """Configuration for a single agent run."""

    role: AgentRole

    # Tool access control (glob-style patterns, e.g. "pw_*", "slack_*")
    allowed_tool_patterns: list[str] = Field(
        default_factory=list,
        description="Tool name patterns this agent can access.",
    )
    denied_tool_patterns: list[str] = Field(
        default_factory=list,
        description="Tool patterns to explicitly deny (overrides allowed).",
    )

    # Overrides
    system_prompt_override: str | None = Field(
        default=None,
        description="Custom system prompt. If None, uses role-specific default.",
    )
    max_iterations_override: int | None = Field(
        default=None,
        description="Override max_iterations for this agent role.",
    )
    require_confirmation_override: bool | None = Field(
        default=None,
        description="Override require_confirmation setting.",
    )

    # Slack-native confirmation (used when ctx is None)
    confirmation_callback: ConfirmationCallback | None = Field(
        default=None,
        description="Async callback for write-op approval when not in MCP context.",
        exclude=True,
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Delegation context
    parent_conversation_id: str | None = Field(
        default=None,
        description="Parent conversation ID when this agent is delegated to.",
    )
    delegation_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context passed from orchestrator.",
    )


class DelegationTask(BaseModel):
    """A task delegated from orchestrator to a worker agent."""

    task_id: str
    target_role: AgentRole
    instruction: str
    context: dict[str, Any] = Field(default_factory=dict)
    parent_conversation_id: str
    max_iterations: int = 10
    timeout: float = 180.0
    parallel: bool = True


class DelegationResult(BaseModel):
    """Result from a delegated task execution."""

    task_id: str
    target_role: AgentRole
    success: bool
    result: str
    conversation_id: str
    iterations_used: int = 0
    tools_called: list[str] = Field(default_factory=list)
    cost: float = 0.0
    error: str | None = None
