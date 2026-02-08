"""Multi-agent orchestration system.

Re-exports the public API for the agent role system:
  - AgentRole: Enum of specialist agent roles
  - AgentConfig: Configuration for a single agent run
  - AgentRegistry: Maps roles to tool subsets and prompts
"""

from fast_mcp_agent.agents.registry import AgentRegistry
from fast_mcp_agent.agents.roles import (
    AgentConfig,
    AgentRole,
    DelegationResult,
    DelegationTask,
)

__all__ = [
    "AgentConfig",
    "AgentRegistry",
    "AgentRole",
    "DelegationResult",
    "DelegationTask",
]
