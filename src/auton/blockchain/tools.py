"""Internal blockchain tool definitions and handler.

These are registered on the MCPBridge with ``cb_`` prefix so the
Blockchain Agent can call them like any other tool.  All tools
require user confirmation (every action is a transaction).
"""

from __future__ import annotations

import json
from typing import Any

from auton.blockchain.client import BlockchainService

# ── Tool schemas (OpenAI function-calling format) ────────────────

BLOCKCHAIN_TOOLS: list[dict[str, Any]] = [
    # ── Wallet ────────────────────────────────────────────────
    {
        "name": "cb_get_wallet_details",
        "description": "Get wallet address, network, and balances.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "cb_get_balance",
        "description": "Get balance of native currency or a token.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "asset_id": {
                    "type": "string",
                    "description": "Token symbol or 'eth' for native.",
                    "default": "eth",
                },
            },
            "required": [],
        },
    },
    {
        "name": "cb_native_transfer",
        "description": "Send native tokens (ETH, etc.) to an address.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient address (0x...).",
                },
                "amount": {
                    "type": "string",
                    "description": "Amount to send (in ETH).",
                },
            },
            "required": ["to", "amount"],
        },
    },
    # ── ERC-20 Tokens ─────────────────────────────────────────
    {
        "name": "cb_erc20_transfer",
        "description": "Transfer ERC-20 tokens to a recipient.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "contract_address": {
                    "type": "string",
                    "description": "Token contract address.",
                },
                "to": {
                    "type": "string",
                    "description": "Recipient address.",
                },
                "amount": {
                    "type": "string",
                    "description": "Amount to transfer.",
                },
            },
            "required": ["contract_address", "to", "amount"],
        },
    },
    {
        "name": "cb_erc20_balance",
        "description": "Check ERC-20 token balance for an address.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "contract_address": {
                    "type": "string",
                    "description": "Token contract address.",
                },
                "address": {
                    "type": "string",
                    "description": "Address to check (default: own wallet).",
                    "default": "",
                },
            },
            "required": ["contract_address"],
        },
    },
    # ── Token Swap ────────────────────────────────────────────
    {
        "name": "cb_get_swap_price",
        "description": "Get a swap price quote (no execution).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_token": {
                    "type": "string",
                    "description": "Token to sell (symbol or address).",
                },
                "to_token": {
                    "type": "string",
                    "description": "Token to buy (symbol or address).",
                },
                "amount": {
                    "type": "string",
                    "description": "Amount of from_token to swap.",
                },
            },
            "required": ["from_token", "to_token", "amount"],
        },
    },
    {
        "name": "cb_swap",
        "description": "Execute a token swap.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_token": {"type": "string"},
                "to_token": {"type": "string"},
                "amount": {"type": "string"},
            },
            "required": ["from_token", "to_token", "amount"],
        },
    },
    # ── DeFi: Aave ────────────────────────────────────────────
    {
        "name": "cb_aave_supply",
        "description": "Supply assets to Aave V3 as collateral.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "asset": {"type": "string", "description": "Token symbol."},
                "amount": {"type": "string", "description": "Amount."},
            },
            "required": ["asset", "amount"],
        },
    },
    {
        "name": "cb_aave_borrow",
        "description": "Borrow against Aave V3 collateral.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "asset": {"type": "string"},
                "amount": {"type": "string"},
            },
            "required": ["asset", "amount"],
        },
    },
    {
        "name": "cb_aave_repay",
        "description": "Repay borrowed Aave V3 debt.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "asset": {"type": "string"},
                "amount": {"type": "string"},
            },
            "required": ["asset", "amount"],
        },
    },
    {
        "name": "cb_aave_portfolio",
        "description": (
            "View Aave V3 portfolio: supplied, borrowed, health factor."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # ── NFT ───────────────────────────────────────────────────
    {
        "name": "cb_nft_mint",
        "description": "Mint a new ERC-721 NFT.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "contract_address": {"type": "string"},
                "to": {
                    "type": "string",
                    "description": "Recipient (default: own wallet).",
                    "default": "",
                },
            },
            "required": ["contract_address"],
        },
    },
    {
        "name": "cb_nft_transfer",
        "description": "Transfer an NFT to another address.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "contract_address": {"type": "string"},
                "token_id": {"type": "string"},
                "to": {"type": "string"},
            },
            "required": ["contract_address", "token_id", "to"],
        },
    },
    # ── Superfluid Streaming ──────────────────────────────────
    {
        "name": "cb_create_flow",
        "description": "Start streaming tokens to a recipient.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "token": {"type": "string"},
                "receiver": {"type": "string"},
                "flow_rate": {
                    "type": "string",
                    "description": "Tokens per second.",
                },
            },
            "required": ["token", "receiver", "flow_rate"],
        },
    },
    {
        "name": "cb_delete_flow",
        "description": "Stop a token stream.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "token": {"type": "string"},
                "receiver": {"type": "string"},
            },
            "required": ["token", "receiver"],
        },
    },
    # ── Identity ──────────────────────────────────────────────
    {
        "name": "cb_register_basename",
        "description": "Register a .base.eth domain name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name to register (without .base.eth).",
                },
            },
            "required": ["name"],
        },
    },
    # ── Faucet (testnet) ──────────────────────────────────────
    {
        "name": "cb_request_faucet",
        "description": "Request testnet funds (ETH, USDC, etc.).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "asset_id": {
                    "type": "string",
                    "description": "Asset to request (eth, usdc).",
                    "default": "eth",
                },
            },
            "required": [],
        },
    },
    # ── WETH ──────────────────────────────────────────────────
    {
        "name": "cb_wrap_eth",
        "description": "Wrap ETH into WETH.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "amount": {"type": "string", "description": "ETH amount."},
            },
            "required": ["amount"],
        },
    },
    # ── Price Oracle ──────────────────────────────────────────
    {
        "name": "cb_fetch_price",
        "description": "Get current price from Pyth oracle.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Token symbol (BTC, ETH, SOL, etc.).",
                },
            },
            "required": ["symbol"],
        },
    },
]


# Map tool names to AgentKit action names
_ACTION_MAP: dict[str, str] = {
    "cb_get_wallet_details": "get_wallet_details",
    "cb_get_balance": "get_balance",
    "cb_native_transfer": "native_transfer",
    "cb_erc20_transfer": "transfer",
    "cb_erc20_balance": "get_balance",
    "cb_get_swap_price": "get_swap_price",
    "cb_swap": "swap",
    "cb_aave_supply": "supply",
    "cb_aave_borrow": "borrow",
    "cb_aave_repay": "repay",
    "cb_aave_portfolio": "get_portfolio",
    "cb_nft_mint": "mint",
    "cb_nft_transfer": "transfer",
    "cb_create_flow": "create_flow",
    "cb_delete_flow": "delete_flow",
    "cb_register_basename": "register_basename",
    "cb_request_faucet": "request_faucet_funds",
    "cb_wrap_eth": "wrap_eth",
    "cb_fetch_price": "fetch_price",
}


async def handle_blockchain_tool(
    service: BlockchainService,
    name: str,
    args: dict[str, Any],
) -> str:
    """Route a blockchain tool call to the AgentKit action."""
    action_name = _ACTION_MAP.get(name)
    if action_name is None:
        return f"[error] Unknown blockchain tool: {name}"

    try:
        result = await service.execute_action(action_name, args)
        if isinstance(result, dict):
            return json.dumps(result, indent=2, default=str)
        return str(result)
    except Exception as exc:
        return f"[error] Blockchain tool '{name}' failed: {exc}"
