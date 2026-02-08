"""Coinbase AgentKit service wrapper.

Initialises the AgentKit wallet provider and exposes action providers
as callable methods.  Uses ``CdpEvmWalletProvider`` by default for
Base/Ethereum networks.

See: https://github.com/coinbase/agentkit/tree/main/python/coinbase-agentkit
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class BlockchainService:
    """Async-friendly wrapper around Coinbase AgentKit."""

    def __init__(
        self,
        network: str = "base-mainnet",
        cdp_api_key_id: str = "",
        cdp_api_key_secret: str = "",
        cdp_wallet_secret: str = "",
    ) -> None:
        self._network = network
        self._cdp_api_key_id = cdp_api_key_id
        self._cdp_api_key_secret = cdp_api_key_secret
        self._cdp_wallet_secret = cdp_wallet_secret
        self._agentkit: Any = None
        self._actions: dict[str, Any] = {}
        self._started = False

    @property
    def is_connected(self) -> bool:
        return self._started

    async def start(self) -> None:
        """Initialize wallet provider, action providers, and AgentKit."""
        try:
            from coinbase_agentkit import (
                AgentKit,
                AgentKitConfig,
                CdpEvmWalletProvider,
                CdpEvmWalletProviderConfig,
                cdp_api_action_provider,
                cdp_evm_wallet_action_provider,
                erc20_action_provider,
                erc721_action_provider,
                pyth_action_provider,
                wallet_action_provider,
                weth_action_provider,
            )

            wallet_provider = CdpEvmWalletProvider(
                CdpEvmWalletProviderConfig(
                    api_key_id=self._cdp_api_key_id,
                    api_key_secret=self._cdp_api_key_secret,
                    wallet_secret=self._cdp_wallet_secret,
                    network_id=self._network,
                )
            )

            self._agentkit = AgentKit(
                AgentKitConfig(
                    wallet_provider=wallet_provider,
                    action_providers=[
                        wallet_action_provider(),
                        erc20_action_provider(),
                        erc721_action_provider(),
                        cdp_api_action_provider(),
                        cdp_evm_wallet_action_provider(),
                        pyth_action_provider(),
                        weth_action_provider(),
                    ],
                )
            )

            # Collect all available actions by name
            for action in self._agentkit.get_actions():
                self._actions[action.name] = action

            self._started = True
            logger.info(
                "BlockchainService started: network=%s, actions=%d",
                self._network,
                len(self._actions),
            )
        except ImportError:
            logger.warning(
                "coinbase-agentkit not installed. "
                "Install with: pip install coinbase-agentkit. "
                "Blockchain tools will not be available."
            )
        except Exception:
            logger.warning(
                "BlockchainService initialization failed.",
                exc_info=True,
            )

    async def stop(self) -> None:
        """Clean up resources."""
        self._started = False
        self._actions.clear()
        logger.info("BlockchainService stopped.")

    def list_actions(self) -> list[str]:
        """Return names of all available actions."""
        return list(self._actions.keys())

    async def execute_action(
        self, action_name: str, args: dict[str, Any]
    ) -> str:
        """Execute a named AgentKit action.

        Returns the result string or an error message.
        """
        action = self._actions.get(action_name)
        if action is None:
            return f"[error] Unknown blockchain action: {action_name}"

        try:
            result = action.invoke(args)
            return str(result)
        except Exception as exc:
            logger.exception(
                "Blockchain action %s failed", action_name
            )
            return f"[error] {action_name} failed: {exc}"
