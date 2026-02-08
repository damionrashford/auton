"""Shopify GraphQL API service wrapper.

Provides async access to the Shopify Admin GraphQL API and Storefront
GraphQL API using ``httpx``.  Handles authentication, rate-limit tracking,
and automatic retry on 429 (throttled) responses.

Requires an admin-generated access token (``shpat_...``) from a custom
Shopify app installed on the target store.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ShopifyService:
    """Async wrapper around Shopify GraphQL APIs."""

    def __init__(
        self,
        store_domain: str,
        admin_token: str,
        storefront_token: str = "",
        api_version: str = "2026-01",
        timeout: float = 30.0,
    ) -> None:
        self._store_domain = store_domain.rstrip("/")
        self._admin_token = admin_token
        self._storefront_token = storefront_token
        self._api_version = api_version
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._started = False

    # ── Lifecycle ────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        return self._started

    @property
    def admin_url(self) -> str:
        return (
            f"https://{self._store_domain}/admin/api/"
            f"{self._api_version}/graphql.json"
        )

    @property
    def storefront_url(self) -> str:
        return (
            f"https://{self._store_domain}/api/"
            f"{self._api_version}/graphql.json"
        )

    async def start(self) -> None:
        """Create the HTTP client and verify connectivity."""
        try:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout),
                headers={"Content-Type": "application/json"},
            )
            # Verify admin token works with a lightweight query.
            result = await self.admin_graphql("{ shop { name } }")
            shop_name = (
                result.get("data", {}).get("shop", {}).get("name", "unknown")
            )
            self._started = True
            logger.info(
                "ShopifyService started: store=%s, shop=%s, version=%s",
                self._store_domain,
                shop_name,
                self._api_version,
            )
        except Exception:
            logger.warning(
                "ShopifyService: failed to connect to %s",
                self._store_domain,
                exc_info=True,
            )

    async def stop(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
        self._started = False
        logger.info("ShopifyService stopped.")

    # ── GraphQL execution ────────────────────────────────────────

    async def admin_graphql(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL query/mutation against the Admin API.

        Returns the parsed JSON response dict.  Raises on HTTP errors.
        """
        return await self._execute(
            url=self.admin_url,
            headers={"X-Shopify-Access-Token": self._admin_token},
            query=query,
            variables=variables,
        )

    async def storefront_graphql(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL query against the Storefront API."""
        if not self._storefront_token:
            return {"errors": [{"message": "Storefront API token not configured."}]}
        return await self._execute(
            url=self.storefront_url,
            headers={
                "X-Shopify-Storefront-Access-Token": self._storefront_token,
            },
            query=query,
            variables=variables,
        )

    # ── Internal ─────────────────────────────────────────────────

    async def _execute(
        self,
        url: str,
        headers: dict[str, str],
        query: str,
        variables: dict[str, Any] | None = None,
        *,
        _retry: int = 0,
    ) -> dict[str, Any]:
        """Send a GraphQL request with retry on throttle (429)."""
        if self._client is None:
            return {"errors": [{"message": "ShopifyService not started."}]}

        body: dict[str, Any] = {"query": query}
        if variables:
            body["variables"] = variables

        resp = await self._client.post(url, json=body, headers=headers)

        # Handle rate limiting with retry.
        if resp.status_code == 429 and _retry < 2:
            retry_after = float(resp.headers.get("Retry-After", "1.0"))
            logger.warning(
                "Shopify rate-limited (429). Retrying in %.1fs...",
                retry_after,
            )
            await asyncio.sleep(retry_after)
            return await self._execute(
                url, headers, query, variables, _retry=_retry + 1
            )

        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]
