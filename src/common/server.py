import asyncpg
from src.common.connection import CockroachConnectionPool
from dataclasses import dataclass
from typing import Dict, List
from typing import AsyncIterator
from dataclasses import dataclass
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP

@dataclass
class AppContext:
    pool: asyncpg.Pool

@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    # Initialize on startup
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        yield AppContext(pool=pool)
    finally:
        await CockroachConnectionPool.close()

# Initialize FastMCP server if pool is not None
mcp = FastMCP("CockroachDB MCP Server", lifespan=app_lifespan, json_response=True)
