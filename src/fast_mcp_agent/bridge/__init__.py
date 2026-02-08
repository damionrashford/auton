"""External MCP connections.

Re-exports the public API for convenience:
  - MCPBridge: Dual-client bridge to RivalSearchMCP and Playwright MCP
  - PlaywrightProcess: Playwright MCP subprocess manager
"""

from fast_mcp_agent.bridge.manager import MCPBridge
from fast_mcp_agent.bridge.playwright import PlaywrightProcess

__all__ = ["MCPBridge", "PlaywrightProcess"]
