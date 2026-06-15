"""FastMCP server instance and lifespan management.

The lifespan creates and tears down the asyncpg pool. Tools acquire the pool
through CockroachConnectionPool (singleton) for simplicity.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import asyncpg
from mcp.server.fastmcp import FastMCP

from src.common.connection import CockroachConnectionPool
from src.common.logging_config import get_logger

log = get_logger("server")


@dataclass
class AppContext:
    """Per-server context, passed to tools via FastMCP lifespan."""

    pool: asyncpg.Pool


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    log.info("CockroachDB MCP server starting up")
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        yield AppContext(pool=pool)
    finally:
        log.info("CockroachDB MCP server shutting down")
        await CockroachConnectionPool.close()


mcp = FastMCP("CockroachDB MCP Server", lifespan=app_lifespan, json_response=True)
