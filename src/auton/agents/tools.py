"""Internal delegation tools for the orchestrator agent.

These tools are registered on the MCPBridge and are ONLY visible to
the orchestrator (filtered out for all other roles by the AgentRegistry).
Each tool spawns a specialist agent via ``OrchestratorAgent.execute_single_task``.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from auton.agents.roles import AgentRole, DelegationTask

if TYPE_CHECKING:
    from auton.agents.orchestrator import OrchestratorAgent

logger = logging.getLogger(__name__)


# Tool schemas in OpenAI function-calling format
DELEGATION_TOOLS: list[dict[str, Any]] = [
    {
        "name": "delegate_to_research",
        "description": (
            "Delegate a research task to the Research Agent. "
            "It can search the web and read pages (read-only)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "instruction": {
                    "type": "string",
                    "description": "Clear, self-contained instruction for the research task.",
                },
                "context": {
                    "type": "object",
                    "description": "Additional context (keywords, URLs, constraints).",
                    "default": {},
                },
            },
            "required": ["instruction"],
        },
    },
    {
        "name": "delegate_to_browser",
        "description": (
            "Delegate an interactive web task to the Browser Agent. "
            "It can click, type, fill forms, and navigate pages."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "instruction": {
                    "type": "string",
                    "description": "Clear instruction for the browser interaction task.",
                },
                "context": {
                    "type": "object",
                    "description": "Additional context (target URL, form fields).",
                    "default": {},
                },
            },
            "required": ["instruction"],
        },
    },
    {
        "name": "delegate_to_communication",
        "description": (
            "Delegate a messaging task to the Communication Agent. "
            "It can send Slack messages and emails."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "instruction": {
                    "type": "string",
                    "description": "Clear instruction for the messaging task.",
                },
                "context": {
                    "type": "object",
                    "description": "Additional context (channel, recipients).",
                    "default": {},
                },
            },
            "required": ["instruction"],
        },
    },
    {
        "name": "delegate_to_workspace",
        "description": (
            "Delegate a Google Workspace task to the Workspace Agent. "
            "It can manage Drive, Calendar, Sheets, Docs, Gmail."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "instruction": {
                    "type": "string",
                    "description": "Clear instruction for the workspace task.",
                },
                "context": {
                    "type": "object",
                    "description": "Additional context (file IDs, folders).",
                    "default": {},
                },
            },
            "required": ["instruction"],
        },
    },
    {
        "name": "delegate_to_blockchain",
        "description": (
            "Delegate a blockchain/crypto task to the Blockchain Agent. "
            "It can manage wallets, transfer tokens, swap, DeFi (Aave), "
            "mint NFTs, stream payments, and more via Coinbase AgentKit."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "instruction": {
                    "type": "string",
                    "description": "Clear instruction for the blockchain task.",
                },
                "context": {
                    "type": "object",
                    "description": "Additional context (addresses, amounts, tokens).",
                    "default": {},
                },
            },
            "required": ["instruction"],
        },
    },
]


# Mapping from tool name to target role
_ROLE_MAP: dict[str, AgentRole] = {
    "delegate_to_research": AgentRole.RESEARCH,
    "delegate_to_browser": AgentRole.BROWSER,
    "delegate_to_communication": AgentRole.COMMUNICATION,
    "delegate_to_workspace": AgentRole.WORKSPACE,
    "delegate_to_blockchain": AgentRole.BLOCKCHAIN,
}


def make_delegation_handler(
    orchestrator: OrchestratorAgent,
    parent_conversation_id_ref: list[str],
) -> Any:
    """Build a handler closure that routes delegation tool calls.

    ``parent_conversation_id_ref`` is a mutable single-element list so
    the conversation ID can be updated at call time.
    """

    async def _handle(name: str, args: dict[str, Any]) -> str:
        target_role = _ROLE_MAP.get(name)
        if target_role is None:
            return f"[error] Unknown delegation tool: {name}"

        task = DelegationTask(
            task_id=uuid.uuid4().hex[:8],
            target_role=target_role,
            instruction=args.get("instruction", ""),
            context=args.get("context", {}),
            parent_conversation_id=(
                parent_conversation_id_ref[0]
                if parent_conversation_id_ref
                else ""
            ),
            max_iterations=args.get("max_iterations", 10),
        )

        result = await orchestrator.execute_single_task(task)

        if result.success:
            return result.result
        return f"[error] Delegation to {target_role.value} failed: {result.error}"

    return _handle
