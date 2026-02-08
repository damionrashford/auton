"""FastMCP server layer.

Re-exports the public API for convenience:
  - mcp: The FastMCP server instance
  - agent_lifespan: Composable lifespan for standalone/mounted use
"""

from fast_mcp_agent.mcp.server import agent_lifespan, mcp

__all__ = ["agent_lifespan", "mcp"]
