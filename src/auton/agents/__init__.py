"""Multi-agent orchestration system.

Re-exports the public API for the agent role system:
  - AgentRole: Enum of specialist agent roles
  - AgentConfig: Configuration for a single agent run
  - AgentRegistry: Maps roles to tool subsets and prompts
"""

from auton.agents.registry import AgentRegistry
from auton.agents.roles import (
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
