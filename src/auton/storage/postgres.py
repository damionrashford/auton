"""Async PostgreSQL connection pool and schema migration for Neon.

Manages the asyncpg connection pool lifecycle and applies the DDL
schema on startup to ensure tables exist.
"""

from __future__ import annotations

import logging
from importlib import resources as importlib_resources
from typing import TYPE_CHECKING

import asyncpg

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


async def create_pool(
    dsn: str,
    *,
    min_size: int = 2,
    max_size: int = 10,
) -> asyncpg.Pool:
    """Create and return an asyncpg connection pool.

    Parameters
    ----------
    dsn:
        PostgreSQL connection string (e.g. ``postgresql://user:pass@host/db``).
    min_size:
        Minimum number of connections in the pool.
    max_size:
        Maximum number of connections in the pool.

    Returns
    -------
    asyncpg.Pool ready for use.

    Raises
    ------
    asyncpg.PostgresError:
        If the connection cannot be established.
    """
    logger.info("Creating asyncpg pool: %s (min=%d, max=%d)", _mask_dsn(dsn), min_size, max_size)
    pool: asyncpg.Pool = await asyncpg.create_pool(
        dsn,
        min_size=min_size,
        max_size=max_size,
        command_timeout=30,
    )
    logger.info("asyncpg pool created successfully.")
    return pool


async def run_migrations(pool: asyncpg.Pool) -> None:
    """Apply the schema DDL to the database.

    Reads ``schema.sql`` from this package and executes it inside a
    transaction.  All statements use ``IF NOT EXISTS`` so re-running
    is safe (idempotent).
    """
    schema_text = (
        importlib_resources.files("auton.storage")
        .joinpath("schema.sql")
        .read_text(encoding="utf-8")
    )

    async with pool.acquire() as conn:
        await conn.execute(schema_text)

    logger.info("Database migrations applied successfully.")


def _mask_dsn(dsn: str) -> str:
    """Mask password in DSN for safe logging."""
    try:
        # Hide everything between :password@ in the DSN
        at_idx = dsn.index("@")
        colon_idx = dsn.index(":", dsn.index("://") + 3)
        return dsn[: colon_idx + 1] + "***@" + dsn[at_idx + 1 :]
    except (ValueError, IndexError):
        return "***"
