import asyncpg
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional
from typing import AsyncIterator
from dataclasses import dataclass
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP
from src.common.config import CRDB_CONFIG

@dataclass
class AppContext:
    pool: Optional[asyncpg.Pool]
    database: str
    dns: str
    query_history: List[Dict]


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:

    database_url = f'''postgresql://{CRDB_CONFIG["username"]}'''    
    if CRDB_CONFIG["password"]:
        database_url += f''':{CRDB_CONFIG["password"]}@{CRDB_CONFIG["host"]}:{CRDB_CONFIG["port"]}/{CRDB_CONFIG["db"]}?sslmode={CRDB_CONFIG["ssl_mode"]}'''
    else:
        database_url += f'''@{CRDB_CONFIG["host"]}:{CRDB_CONFIG["port"]}/{CRDB_CONFIG["db"]}?sslmode={CRDB_CONFIG["ssl_mode"]}'''

    if CRDB_CONFIG["ssl_mode"] != 'disable':
        database_url += f'''&sslrootcert={CRDB_CONFIG["ssl_ca_cert"]}&sslcert={CRDB_CONFIG["ssl_cert"]}&sslkey={CRDB_CONFIG["ssl_key"]}'''
    
    print("Connecting to database...", file=sys.stderr)
    try:
        # Create connection pool
        pool = await asyncpg.create_pool(
            database_url,
            min_size=5,
            max_size=20,
            command_timeout=60
        )    
    except Exception as e:
        print(f"Cannot create connection pool: {e}", file=sys.stderr)
        # Yield context with pool=None so tools can handle it
        yield AppContext(pool=None, database="", dns=database_url, query_history=[])
        return

    try:
        async with pool.acquire() as conn:
            version = await conn.fetchval("SELECT version()")
            database =  await conn.fetchval("SELECT current_database()")
            print("Connected to CRDB v." + version + " - Database:" + database, file=sys.stderr)
            yield AppContext(pool=pool, database=database, dns=database_url, query_history=[])
    finally:
        print("Closing database connection...", file=sys.stderr)
        if pool:
            await pool.close()

# Initialize FastMCP server if pool is not None
mcp = FastMCP("CockroachDB MCP Server", lifespan=app_lifespan, json_response=True)