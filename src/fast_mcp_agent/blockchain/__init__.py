"""Coinbase AgentKit blockchain integration.

Wraps the ``coinbase-agentkit`` Python SDK as internal tools registered
on the MCPBridge, giving the Blockchain Agent access to wallets, DeFi,
token operations, NFTs, and more.
"""

from fast_mcp_agent.blockchain.client import BlockchainService
from fast_mcp_agent.blockchain.tools import BLOCKCHAIN_TOOLS, handle_blockchain_tool

__all__ = ["BlockchainService", "BLOCKCHAIN_TOOLS", "handle_blockchain_tool"]
