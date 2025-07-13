import asyncpg
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional
from typing import AsyncIterator
from dataclasses import dataclass
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP
from src.common.config import CRDB_CONFIG, backfill_config

@dataclass
class AppContext:
    pool: Optional[asyncpg.Pool]
    database: str
    dns: str
    query_history: List[Dict]


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:

    backfill_config()
    database_url = CRDB_CONFIG['url']
    if not database_url:
        print("CRDB_URL is not set", file=sys.stderr)
        sys.exit(1)

    # Create connection pool
    pool = await asyncpg.create_pool(
        database_url,
        min_size=5,
        max_size=20,
        command_timeout=60
    )

    print("Connecting to database...", file=sys.stderr)
    try:
        async with pool.acquire() as conn:
            version = await conn.fetchval("SELECT version()")
            database =  await conn.fetchval("SELECT current_database()")
            print("Connected to CRDB v." + version + " - Database:" + database, file=sys.stderr)
            yield AppContext(pool=pool, database=database, dns=database_url, query_history=[])
    finally:
        print("Closing database connection...", file=sys.stderr)
        pool.close()

# Initialize FastMCP server
mcp = FastMCP("CockroachDB MCP Server", lifespan=app_lifespan, json_response=True)