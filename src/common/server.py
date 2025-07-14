from dataclasses import dataclass
import sys
from typing import Dict, List, Optional
from typing import AsyncIterator
from dataclasses import dataclass
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP
from src.common.CockroachConnectionPool import CockroachConnectionPool

@dataclass
class AppContext:
    current_database: str
    query_history: List[Dict]

@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    try:
        yield AppContext(current_database="defaultdb", query_history=[])
    finally:
        print("Closing server connection...", file=sys.stderr)
        await CockroachConnectionPool.close()

# Initialize FastMCP server if pool is not None
mcp = FastMCP("CockroachDB MCP Server", lifespan=app_lifespan, json_response=True)
