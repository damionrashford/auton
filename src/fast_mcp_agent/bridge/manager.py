"""MCP Bridge -- manages FastMCP Client connections to external servers.

Provides a unified interface for:
  - RivalSearchMCP    (remote HTTP)
  - Playwright MCP    (local HTTP subprocess)
  - Google Workspace  (Streamable HTTP, optional)

Also supports internal Python tool routing for:
  - Slack Bolt tools
  - Cron scheduler tools

Handles tool discovery, name-collision avoidance, schema conversion to
the OpenAI function-calling format, and tool call routing.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastmcp import Client
from fastmcp.client.messages import MessageHandler

from fast_mcp_agent.config import Settings
from fast_mcp_agent.models import FunctionSchema, ToolSchema

logger = logging.getLogger(__name__)

# Prefixes applied to tools from each server when a name collision is detected.
_PW_PREFIX = "pw_"
_GW_PREFIX = "gw_"

# Type alias for internal tool handlers
InternalToolHandler = Callable[[str, dict[str, Any]], Awaitable[str]]


class BridgeNotificationHandler(MessageHandler):
    """Auto-refresh tool caches when connected MCP servers change their tools."""

    def __init__(self, bridge: MCPBridge, source: str) -> None:
        self._bridge = bridge
        self._source = source

    async def on_tool_list_changed(self, notification: Any) -> None:
        """Handle tool list change notifications from MCP servers."""
        client = self._bridge._get_client(self._source)
        if client:
            new_tools = await self._bridge._discover_tools(client, self._source)
            if self._source == "rival":
                self._bridge._rival_tools = new_tools
            elif self._source == "pw":
                self._bridge._pw_tools = new_tools
            elif self._source == "gw":
                self._bridge._gw_tools = new_tools
            self._bridge._build_routing()
            logger.info(
                "Tool list refreshed for %s (%d tools).", self._source, len(new_tools)
            )


class MCPBridge:
    """Multi-client bridge to external MCP servers and internal Python tools."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

        # FastMCP clients -- created lazily, connected during ``connect()``.
        self._rival_client: Client | None = None
        self._pw_client: Client | None = None
        self._gw_client: Client | None = None

        # Tool registries populated after connect.
        self._rival_tools: dict[str, dict[str, Any]] = {}
        self._pw_tools: dict[str, dict[str, Any]] = {}
        self._gw_tools: dict[str, dict[str, Any]] = {}

        # Internal Python tools (Slack Bolt, Cron, Memory, etc.)
        self._internal_tools: dict[str, dict[str, Any]] = {}
        self._internal_handlers: dict[str, InternalToolHandler] = {}
        self._internal_tool_source_map: dict[str, str] = {}  # tool_name -> source label

        # Unified name -> ("rival" | "pw" | "gw" | "internal", original_name) mapping.
        self._routing: dict[str, tuple[str, str]] = {}

    # ── lifecycle ───────────────────────────────────────────────────

    async def connect(self) -> None:
        """Open connections to all MCP servers and discover tools."""
        # RivalSearchMCP (required)
        self._rival_client = Client(
            self._settings.rival_search_url,
            message_handler=BridgeNotificationHandler(self, "rival"),
        )
        await self._rival_client.__aenter__()
        self._rival_tools = await self._discover_tools(
            self._rival_client, source="rival"
        )
        logger.info(
            "RivalSearchMCP: %d tools discovered.", len(self._rival_tools)
        )

        # Playwright MCP (required)
        self._pw_client = Client(
            self._settings.playwright_mcp_url,
            message_handler=BridgeNotificationHandler(self, "pw"),
        )
        await self._pw_client.__aenter__()
        self._pw_tools = await self._discover_tools(
            self._pw_client, source="pw"
        )
        logger.info(
            "Playwright MCP: %d tools discovered.", len(self._pw_tools)
        )

        # Google Workspace MCP (optional -- graceful degradation)
        if (
            self._settings.google_workspace_mcp_enabled
            and self._settings.google_workspace_mcp_url
        ):
            try:
                self._gw_client = Client(
                    self._settings.google_workspace_mcp_url,
                    message_handler=BridgeNotificationHandler(self, "gw"),
                )
                await self._gw_client.__aenter__()
                self._gw_tools = await self._discover_tools(
                    self._gw_client, source="gw"
                )
                logger.info(
                    "Google Workspace MCP: %d tools discovered.",
                    len(self._gw_tools),
                )
            except Exception:
                logger.warning(
                    "Google Workspace MCP connection failed (url=%s). "
                    "Continuing without Google Workspace tools.",
                    self._settings.google_workspace_mcp_url,
                    exc_info=True,
                )
                self._gw_client = None
                self._gw_tools = {}
        else:
            logger.info("Google Workspace MCP: skipped (not configured or disabled).")

        self._build_routing()

    async def disconnect(self) -> None:
        """Cleanly close all client sessions."""
        for label, client in [
            ("RivalSearchMCP", self._rival_client),
            ("PlaywrightMCP", self._pw_client),
            ("GoogleWorkspaceMCP", self._gw_client),
        ]:
            if client is not None:
                try:
                    await client.__aexit__(None, None, None)
                except Exception:
                    logger.exception("Error closing %s client.", label)
        self._rival_client = None
        self._pw_client = None
        self._gw_client = None

    # ── internal tool registration ──────────────────────────────────

    def register_internal_tools(
        self,
        tools: list[dict[str, Any]],
        handler: InternalToolHandler,
        source: str,
    ) -> None:
        """Register internal Python tool definitions and their handler.

        Args:
            tools: List of tool schema dicts (OpenAI function-calling format).
            handler: Async callable(name, args) -> str that handles tool calls.
            source: Label for logging (e.g. "slack", "cron").
        """
        for tool in tools:
            name = tool["name"]
            self._internal_tools[name] = tool
            self._internal_handlers[name] = handler
            self._internal_tool_source_map[name] = source

        # Rebuild routing to include new internal tools
        self._build_routing()

        logger.info(
            "Registered %d internal %s tools: %s",
            len(tools),
            source,
            [t["name"] for t in tools],
        )

    # ── tool discovery ──────────────────────────────────────────────

    async def _discover_tools(
        self, client: Client, source: str
    ) -> dict[str, dict[str, Any]]:
        """List tools from *client* and return {name: raw_schema}."""
        tools_list = await client.list_tools()
        result: dict[str, dict[str, Any]] = {}
        for t in tools_list:
            schema: dict[str, Any] = {
                "name": t.name,
                "description": t.description or "",
                "inputSchema": (
                    t.inputSchema if hasattr(t, "inputSchema") else {}
                ),
            }
            result[t.name] = schema
        return result

    def _build_routing(self) -> None:
        """Build the unified routing table, prefixing on collision.

        Priority order (no prefix given to the first):
          1. RivalSearch tools       (no prefix)
          2. Playwright tools        (pw_ prefix on collision)
          3. Google Workspace tools  (gw_ prefix on collision)
          4. Internal tools          (already have unique prefixes like slack_, cron_)
        """
        self._routing.clear()

        # Rival tools go in first (no prefix).
        for name in self._rival_tools:
            self._routing[name] = ("rival", name)

        # Playwright tools -- ALWAYS prefix with pw_ for predictable routing.
        for name in self._pw_tools:
            exposed_name = f"{_PW_PREFIX}{name}" if not name.startswith(_PW_PREFIX) else name
            self._routing[exposed_name] = ("pw", name)

        # Google Workspace tools -- ALWAYS prefix with gw_ for predictable routing.
        for name in self._gw_tools:
            exposed_name = f"{_GW_PREFIX}{name}" if not name.startswith(_GW_PREFIX) else name
            self._routing[exposed_name] = ("gw", name)

        # Internal tools -- use their names directly (already prefixed).
        for name in self._internal_tools:
            if name not in self._routing:
                self._routing[name] = ("internal", name)
            else:
                logger.warning(
                    "Internal tool name collision: '%s' already exists — skipping.",
                    name,
                )

    # ── public API ──────────────────────────────────────────────────

    def _get_tool_registry(self, source: str) -> dict[str, dict[str, Any]]:
        """Return the tool registry for a given source key."""
        if source == "rival":
            return self._rival_tools
        if source == "pw":
            return self._pw_tools
        if source == "gw":
            return self._gw_tools
        if source == "internal":
            return self._internal_tools
        return {}

    def _get_client(self, source: str) -> Client | None:
        """Return the client for a given source key."""
        if source == "rival":
            return self._rival_client
        if source == "pw":
            return self._pw_client
        if source == "gw":
            return self._gw_client
        return None

    def get_openai_tools(self) -> list[dict[str, Any]]:
        """Return tool schemas in the OpenAI function-calling format."""
        schemas: list[dict[str, Any]] = []
        for exposed_name, (source, original) in self._routing.items():
            registry = self._get_tool_registry(source)
            raw = registry.get(original)
            if raw is None:
                continue
            input_schema = raw.get("inputSchema", {})
            # Ensure we have a proper JSON-schema object
            params: dict[str, Any] = (
                input_schema if isinstance(input_schema, dict) else {}
            )
            ts = ToolSchema(
                function=FunctionSchema(
                    name=exposed_name,
                    description=raw.get("description", ""),
                    parameters=params,
                )
            )
            schemas.append(ts.model_dump())
        return schemas

    def list_tool_names(self) -> list[str]:
        """Return all exposed tool names."""
        return list(self._routing.keys())

    def get_openai_tools_filtered(
        self, allowed_tool_names: list[str]
    ) -> list[dict[str, Any]]:
        """Return tool schemas filtered to only the given tool names."""
        allowed_set = set(allowed_tool_names)
        return [
            s
            for s in self.get_openai_tools()
            if s["function"]["name"] in allowed_set
        ]

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> str:
        """Route a tool call to the correct MCP server or internal handler."""
        if tool_name not in self._routing:
            return f"[error] Unknown tool: {tool_name}"

        source, original_name = self._routing[tool_name]

        # Internal tools are handled by Python callables
        if source == "internal":
            handler = self._internal_handlers.get(tool_name)
            if handler is None:
                return f"[error] No handler for internal tool: {tool_name}"
            try:
                return await handler(tool_name, arguments)
            except Exception as exc:
                logger.exception("Internal tool call failed: %s", tool_name)
                return f"[error] Internal tool '{tool_name}' failed: {exc}"

        # External MCP tools
        client = self._get_client(source)
        if client is None:
            return f"[error] {source} client is not connected."

        try:
            result = await client.call_tool(original_name, arguments)
            return self._extract_text(result)
        except Exception as exc:
            logger.exception("Tool call failed: %s", tool_name)
            return f"[error] Tool '{tool_name}' failed: {exc}"

    @property
    def connected_servers(self) -> list[str]:
        """Names of currently connected servers."""
        servers: list[str] = []
        if self._rival_client is not None:
            servers.append("RivalSearchMCP")
        if self._pw_client is not None:
            servers.append("PlaywrightMCP")
        if self._gw_client is not None:
            servers.append("GoogleWorkspaceMCP")
        return servers

    @property
    def internal_tool_sources(self) -> list[str]:
        """Labels of registered internal tool sources."""
        return sorted(set(self._internal_tool_source_map.values()))

    # ── prompt access (RivalSearchMCP) ────────────────────────────

    async def list_prompts(self) -> list[dict[str, Any]]:
        """List prompts from RivalSearchMCP."""
        if self._rival_client is None:
            return []
        try:
            prompts = await self._rival_client.list_prompts()
            return [
                {
                    "name": p.name,
                    "description": p.description or "",
                    "arguments": [
                        {"name": a.name, "required": a.required}
                        for a in (p.arguments or [])
                    ],
                }
                for p in prompts
            ]
        except Exception:
            logger.warning("Failed to list prompts", exc_info=True)
            return []

    async def get_prompt(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> str:
        """Fetch a rendered prompt from RivalSearchMCP.

        Returns the concatenated message texts, or an error string.
        """
        if self._rival_client is None:
            return "[error] RivalSearchMCP not connected."
        try:
            result = await self._rival_client.get_prompt(
                name, arguments or {}
            )
            parts: list[str] = []
            for msg in result.messages:
                content = msg.content
                if hasattr(content, "text"):
                    parts.append(content.text)
                else:
                    parts.append(str(content))
            return "\n\n".join(parts)
        except Exception as exc:
            logger.warning("Failed to get prompt %s: %s", name, exc)
            return f"[error] Prompt '{name}' failed: {exc}"

    # ── helpers ─────────────────────────────────────────────────────

    def _extract_text(self, result: Any) -> str:
        """Best-effort extraction of text content from a CallToolResult."""
        max_len = self._settings.max_tool_result_length

        # result may be a CallToolResult with .content list
        content_items = getattr(result, "content", None)
        if content_items is None and isinstance(result, list):
            content_items = result

        if content_items is None:
            text = str(result)
        else:
            parts: list[str] = []
            for item in content_items:
                if hasattr(item, "text"):
                    parts.append(item.text)
                elif hasattr(item, "data"):
                    parts.append("[binary content]")
                else:
                    parts.append(str(item))
            text = "\n".join(parts)

        if len(text) > max_len:
            text = text[:max_len] + f"\n...[truncated at {max_len} chars]"

        return text
