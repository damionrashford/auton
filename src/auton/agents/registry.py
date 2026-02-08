"""Registry mapping agent roles to their configurations and capabilities.

The ``AgentRegistry`` is the single source of truth for which tools each
agent role can access.  Tool filtering uses glob-style patterns (``*``
wildcards) with denied patterns taking priority over allowed ones.

RivalSearchMCP tools (no prefix, first priority in MCPBridge routing):
  web_search, map_website, content_operations, research_topic,
  research_agent, scientific_research, social_search, news_aggregation,
  github_search, document_analysis

Playwright MCP tools (``pw_`` prefix on collision):
  pw_navigate, pw_snapshot, pw_screenshot, pw_click, pw_type, pw_fill,
  pw_scroll_down, pw_tab_new, pw_tab_close, pw_pdf_save, ...

Google Workspace tools (``gw_`` prefix):
  gw_send_email, gw_list_emails, gw_read_email, gw_create_file, ...

Internal tools:
  slack_*, cron_*, memory_*, delegate_to_*
"""

from __future__ import annotations

import logging
import re

from auton.agents.roles import AgentConfig, AgentRole
from auton.config import Settings

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Central registry for agent role configurations."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._configs: dict[AgentRole, AgentConfig] = {}
        self._initialize_default_configs()

    def _initialize_default_configs(self) -> None:
        """Build default configs for every role from settings."""
        s = self._settings

        # ── ORCHESTRATOR ─────────────────────────────────────────
        # Only sees delegation tools + memory recall for context
        self._configs[AgentRole.ORCHESTRATOR] = AgentConfig(
            role=AgentRole.ORCHESTRATOR,
            allowed_tool_patterns=[
                "delegate_to_*",
                "memory_recall",
            ],
            max_iterations_override=s.multi_agent_orchestrator_max_iterations,
        )

        # ── RESEARCH ─────────────────────────────────────────────
        # All RivalSearchMCP tools + read-only Playwright + memory
        self._configs[AgentRole.RESEARCH] = AgentConfig(
            role=AgentRole.RESEARCH,
            allowed_tool_patterns=[
                # RivalSearchMCP (10 tools, no prefix)
                "web_search",
                "social_search",
                "news_aggregation",
                "github_search",
                "scientific_research",
                "content_operations",
                "map_website",
                "document_analysis",
                "research_topic",
                "research_agent",
                # Playwright read-only (pw_ prefix)
                "pw_navigate",
                "pw_snapshot",
                "pw_screenshot",
                # Playwright read-only (browser_ prefix — unprefixed)
                "browser_navigate",
                "browser_snapshot",
                "browser_screenshot",
                # Memory
                "memory_store",
                "memory_recall",
            ],
            denied_tool_patterns=[
                # Block interactive Playwright
                "pw_click",
                "pw_type",
                "pw_fill",
                # Block everything else
                "slack_*",
                "gw_*",
                "cron_*",
                "delegate_to_*",
            ],
            max_iterations_override=s.multi_agent_research_max_iterations,
        )

        # ── BROWSER ──────────────────────────────────────────────
        # All Playwright tools (interactive) + memory
        self._configs[AgentRole.BROWSER] = AgentConfig(
            role=AgentRole.BROWSER,
            allowed_tool_patterns=[
                "pw_*",
                "browser_*",
                "memory_store",
            ],
            denied_tool_patterns=[
                # Block all RivalSearch tools
                "web_search",
                "social_search",
                "news_aggregation",
                "github_search",
                "scientific_research",
                "content_operations",
                "map_website",
                "document_analysis",
                "research_topic",
                "research_agent",
                # Block comms/workspace/cron/delegation
                "slack_*",
                "gw_*",
                "cron_*",
                "delegate_to_*",
            ],
            max_iterations_override=s.multi_agent_browser_max_iterations,
            require_confirmation_override=True,
        )

        # ── COMMUNICATION ────────────────────────────────────────
        # Slack + email tools + memory
        self._configs[AgentRole.COMMUNICATION] = AgentConfig(
            role=AgentRole.COMMUNICATION,
            allowed_tool_patterns=[
                "slack_*",
                "webhook_*",
                # Gmail tools (gw_ prefix from workspace-mcp)
                "gw_send_gmail_message",
                "gw_draft_gmail_message",
                "gw_search_gmail_messages",
                "gw_get_gmail_message_content",
                "gw_get_gmail_messages_content_batch",
                "gw_get_gmail_thread_content",
                # Google Chat
                "gw_send_message",
                "gw_get_messages",
                "gw_search_messages",
                "gw_list_spaces",
                # Memory
                "memory_recall",
                "memory_store",
            ],
            denied_tool_patterns=[
                "pw_*",
                "browser_*",
                "web_search",
                "social_search",
                "news_aggregation",
                "github_search",
                "scientific_research",
                "content_operations",
                "map_website",
                "document_analysis",
                "research_topic",
                "research_agent",
                "cron_*",
                "delegate_to_*",
            ],
            max_iterations_override=s.multi_agent_communication_max_iterations,
            require_confirmation_override=True,
        )

        # ── WORKSPACE ────────────────────────────────────────────
        # All Google Workspace tools + memory
        self._configs[AgentRole.WORKSPACE] = AgentConfig(
            role=AgentRole.WORKSPACE,
            allowed_tool_patterns=[
                "gw_*",
                "memory_recall",
                "memory_store",
            ],
            denied_tool_patterns=[
                "pw_*",
                "browser_*",
                "web_search",
                "social_search",
                "news_aggregation",
                "github_search",
                "scientific_research",
                "content_operations",
                "map_website",
                "document_analysis",
                "research_topic",
                "research_agent",
                "slack_*",
                "cron_*",
                "delegate_to_*",
            ],
            max_iterations_override=s.multi_agent_workspace_max_iterations,
            require_confirmation_override=True,
        )

        # ── BLOCKCHAIN ──────────────────────────────────────────
        # Coinbase AgentKit: wallets, DeFi, tokens, NFTs, swaps
        self._configs[AgentRole.BLOCKCHAIN] = AgentConfig(
            role=AgentRole.BLOCKCHAIN,
            allowed_tool_patterns=[
                "cb_*",
                "memory_recall",
                "memory_store",
            ],
            denied_tool_patterns=[
                "pw_*",
                "browser_*",
                "web_search",
                "social_search",
                "news_aggregation",
                "github_search",
                "scientific_research",
                "content_operations",
                "map_website",
                "document_analysis",
                "research_topic",
                "research_agent",
                "slack_*",
                "gw_*",
                "cron_*",
                "delegate_to_*",
            ],
            max_iterations_override=s.multi_agent_blockchain_max_iterations,
            require_confirmation_override=True,
        )

    # ── public API ──────────────────────────────────────────────────

    def get_config(self, role: AgentRole) -> AgentConfig:
        """Return a *copy* of the default config for *role*."""
        return self._configs[role].model_copy()

    def get_allowed_tools(
        self,
        role: AgentRole,
        all_tool_names: list[str],
    ) -> list[str]:
        """Filter *all_tool_names* to only those permitted for *role*.

        Denied patterns always take priority over allowed patterns.
        """
        config = self._configs[role]
        allowed: list[str] = []

        for name in all_tool_names:
            if _any_pattern_matches(name, config.denied_tool_patterns):
                continue
            if _any_pattern_matches(name, config.allowed_tool_patterns):
                allowed.append(name)

        return allowed

    def list_roles(self) -> list[AgentRole]:
        """Return all registered roles."""
        return list(self._configs.keys())


# ── helpers ─────────────────────────────────────────────────────────


def _any_pattern_matches(name: str, patterns: list[str]) -> bool:
    """Check if *name* matches any glob-style pattern in *patterns*."""
    for pattern in patterns:
        regex = re.escape(pattern).replace(r"\*", ".*")
        if re.fullmatch(regex, name):
            return True
    return False
