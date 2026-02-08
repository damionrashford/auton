"""Webhook service for outbound HTTP requests and inbound subscription management.

Provides:
  - Outbound webhook delivery (POST/PUT/PATCH/GET) with retry logic
  - Inbound subscription CRUD operations
  - Delivery history tracking
  - HMAC-SHA256 signature verification for inbound webhooks
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import uuid
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class WebhookService:
    """Async webhook client with delivery tracking and retry logic."""

    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_backoff: float = 2.0,
        db_pool: Any = None,
    ) -> None:
        self._timeout = timeout
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff
        self._pool = db_pool
        self._client: httpx.AsyncClient | None = None
        self._started = False

    @property
    def is_connected(self) -> bool:
        return self._started

    async def start(self) -> None:
        """Initialize the HTTP client."""
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout, connect=10.0),
            follow_redirects=True,
        )
        self._started = True
        logger.info(
            "WebhookService started (timeout=%.1fs, retries=%d)",
            self._timeout,
            self._max_retries,
        )

    async def stop(self) -> None:
        """Shut down the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
        self._started = False
        logger.info("WebhookService stopped.")

    # ── Outbound ─────────────────────────────────────────────────

    async def send_webhook(
        self,
        url: str,
        payload: dict[str, Any],
        method: str = "POST",
        headers: dict[str, str] | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        """Send an outbound webhook with retry logic and delivery tracking."""
        if not self._client:
            return {"error": "WebhookService not started"}

        headers = headers or {}
        headers.setdefault("Content-Type", "application/json")

        delivery_id = await self._log_delivery(
            conversation_id=conversation_id,
            url=url,
            method=method,
            payload=payload,
            headers=headers,
            status="pending",
        )

        for attempt in range(1, self._max_retries + 1):
            try:
                resp = await self._do_request(method, url, payload, headers)

                await self._update_delivery(
                    delivery_id=delivery_id,
                    status="success",
                    status_code=resp.status_code,
                    response_body=resp.text[:1000],
                    attempt=attempt,
                )
                return {
                    "success": True,
                    "status_code": resp.status_code,
                    "response": resp.text[:1000],
                    "delivery_id": delivery_id,
                }

            except httpx.TimeoutException:
                error_msg = f"Timeout after {self._timeout}s"
            except httpx.HTTPError as exc:
                error_msg = str(exc)

            # Retry or fail
            if attempt == self._max_retries:
                await self._update_delivery(
                    delivery_id=delivery_id,
                    status="failed",
                    error=error_msg,
                    attempt=attempt,
                )
                return {
                    "success": False,
                    "error": error_msg,
                    "delivery_id": delivery_id,
                }

            await self._update_delivery(
                delivery_id=delivery_id,
                status="retrying",
                error=f"Attempt {attempt}: {error_msg}",
                attempt=attempt,
            )
            await asyncio.sleep(self._retry_backoff**attempt)

        return {"success": False, "error": "Max retries exceeded"}

    async def get_webhook(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """GET request (read-only, no retry or delivery tracking)."""
        if not self._client:
            return {"error": "WebhookService not started"}

        try:
            resp = await self._client.get(url, headers=headers, params=params)
            return {
                "success": True,
                "status_code": resp.status_code,
                "response": resp.text[:2000],
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _do_request(
        self,
        method: str,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> httpx.Response:
        """Execute an HTTP request (raises on network errors)."""
        assert self._client is not None  # noqa: S101
        m = method.upper()
        if m == "POST":
            return await self._client.post(url, headers=headers, json=payload)
        if m == "PUT":
            return await self._client.put(url, headers=headers, json=payload)
        if m == "PATCH":
            return await self._client.patch(url, headers=headers, json=payload)
        msg = f"Unsupported HTTP method: {method}"
        raise ValueError(msg)

    # ── Subscription management ──────────────────────────────────

    async def create_subscription(
        self,
        webhook_url: str,
        description: str,
        signing_secret: str,
        agent_role: str = "research",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Register a new inbound webhook endpoint."""
        if not self._pool:
            return {"error": "Database not available"}

        webhook_id = str(uuid.uuid4())
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO webhook_subscriptions
                        (id, webhook_url, description, signing_secret,
                         agent_role, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    webhook_id,
                    webhook_url,
                    description,
                    signing_secret,
                    agent_role,
                    json.dumps(metadata or {}),
                )
            return {
                "success": True,
                "webhook_id": webhook_id,
                "receive_url": f"/webhooks/{webhook_id}",
            }
        except Exception as exc:
            logger.exception("Failed to create webhook subscription")
            return {"error": str(exc)}

    async def delete_subscription(self, webhook_id: str) -> dict[str, Any]:
        """Delete an inbound webhook subscription."""
        if not self._pool:
            return {"error": "Database not available"}

        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM webhook_subscriptions WHERE id = $1",
                    webhook_id,
                )
                if result == "DELETE 0":
                    return {"error": f"Webhook not found: {webhook_id}"}
            return {"success": True, "webhook_id": webhook_id}
        except Exception as exc:
            logger.exception("Failed to delete webhook subscription")
            return {"error": str(exc)}

    async def list_subscriptions(self) -> list[dict[str, Any]]:
        """List all registered webhook subscriptions."""
        if not self._pool:
            return []

        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, webhook_url, description, agent_role,
                           enabled, created_at
                    FROM webhook_subscriptions
                    ORDER BY created_at DESC
                    """
                )
            return [
                {
                    "webhook_id": r["id"],
                    "webhook_url": r["webhook_url"],
                    "description": r["description"],
                    "agent_role": r["agent_role"],
                    "enabled": r["enabled"],
                    "created_at": r["created_at"].isoformat(),
                }
                for r in rows
            ]
        except Exception:
            logger.exception("Failed to list webhook subscriptions")
            return []

    async def list_deliveries(
        self,
        conversation_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List recent outbound webhook deliveries."""
        if not self._pool:
            return []

        try:
            async with self._pool.acquire() as conn:
                if conversation_id:
                    rows = await conn.fetch(
                        """
                        SELECT id, url, method, status, status_code,
                               created_at, delivered_at
                        FROM webhook_deliveries
                        WHERE conversation_id = $1
                        ORDER BY created_at DESC LIMIT $2
                        """,
                        conversation_id,
                        limit,
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT id, url, method, status, status_code,
                               created_at, delivered_at
                        FROM webhook_deliveries
                        ORDER BY created_at DESC LIMIT $1
                        """,
                        limit,
                    )
            return [
                {
                    "delivery_id": r["id"],
                    "url": r["url"],
                    "method": r["method"],
                    "status": r["status"],
                    "status_code": r["status_code"],
                    "created_at": r["created_at"].isoformat(),
                    "delivered_at": (
                        r["delivered_at"].isoformat()
                        if r["delivered_at"]
                        else None
                    ),
                }
                for r in rows
            ]
        except Exception:
            logger.exception("Failed to list webhook deliveries")
            return []

    # ── Signature verification ───────────────────────────────────

    @staticmethod
    def verify_signature(
        payload: bytes,
        signature: str,
        secret: str,
    ) -> bool:
        """Verify HMAC-SHA256 signature for inbound webhooks.

        Expects signature format: ``sha256=<hex_digest>``
        """
        if not signature.startswith("sha256="):
            return False

        expected = signature.split("=", 1)[1]
        computed = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(computed, expected)

    # ── Internal helpers ─────────────────────────────────────────

    async def _log_delivery(
        self,
        conversation_id: str | None,
        url: str,
        method: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        status: str,
    ) -> int:
        """Log an outbound delivery to Postgres. Returns delivery ID."""
        if not self._pool:
            return 0
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO webhook_deliveries
                        (conversation_id, url, method, payload, headers, status)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING id
                    """,
                    conversation_id,
                    url,
                    method,
                    json.dumps(payload),
                    json.dumps(headers),
                    status,
                )
            return row["id"] if row else 0
        except Exception:
            logger.exception("Failed to log webhook delivery")
            return 0

    async def _update_delivery(
        self,
        delivery_id: int,
        status: str,
        status_code: int | None = None,
        response_body: str | None = None,
        error: str | None = None,
        attempt: int = 1,
    ) -> None:
        """Update a delivery record in Postgres."""
        if not self._pool or delivery_id == 0:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE webhook_deliveries
                    SET status = $1, status_code = $2,
                        response_body = $3, error = $4, attempt = $5,
                        delivered_at = CASE
                            WHEN $1 IN ('success', 'failed') THEN NOW()
                            ELSE delivered_at END
                    WHERE id = $6
                    """,
                    status,
                    status_code,
                    response_body,
                    error,
                    attempt,
                    delivery_id,
                )
        except Exception:
            logger.exception("Failed to update webhook delivery")
