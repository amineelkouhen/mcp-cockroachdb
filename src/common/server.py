from dataclasses import dataclass
from typing import Dict, List
from typing import AsyncIterator
from dataclasses import dataclass
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP

@dataclass
class AppContext:
    current_database: str
    query_history: List[Dict]

@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    yield AppContext(current_database="defaultdb", query_history=[])

# Initialize FastMCP server if pool is not None
mcp = FastMCP("CockroachDB MCP Server", lifespan=app_lifespan, json_response=True)
