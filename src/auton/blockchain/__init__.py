"""Coinbase AgentKit blockchain integration.

Wraps the ``coinbase-agentkit`` Python SDK as internal tools registered
on the MCPBridge, giving the Blockchain Agent access to wallets, DeFi,
token operations, NFTs, and more.
"""

from auton.blockchain.client import BlockchainService
from auton.blockchain.tools import BLOCKCHAIN_TOOLS, handle_blockchain_tool

__all__ = ["BlockchainService", "BLOCKCHAIN_TOOLS", "handle_blockchain_tool"]
