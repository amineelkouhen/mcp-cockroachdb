import asyncpg
from mcp.server.fastmcp import Context
from typing import Dict, Any, Optional
from src.common.server import mcp

@mcp.tool()
async def connect_database(ctx: Context, host: str, port: int = 26257, database: str = "defaultdb",
                        user: str = "root", password: Optional[str] = None,
                        sslmode: Optional[str] = None, sslcert: Optional[str] = None,
                        sslkey: Optional[str] = None, sslrootcert: Optional[str] = None) -> Dict[str, Any]:
    """Connect to a CockroachDB database and create a connection pool.

    Args:
        host (str): CockroachDB host.
        port (int): CockroachDB port (default: 26257).
        database (str): Database name (default: "defaultdb").
        user (str): Username (default: "root").
        password (str, optional): Password.
        sslmode (str): SSL mode (default: disable - Possible values: require, verify-ca, verify-full).
        sslcert (str, optional): Path to user certificate file.
        sslkey (str, optional): Path to user key file.
        sslrootcert (str, optional): Path to CA certificate file.

    Returns:
        A success message or an error message.
    """
    
    try:
        # Build connection string
        dsn = f"postgresql://{user}"
        if password:
            dsn += f":{password}"
        dsn += f"@{host}:{port}/{database}"

        # SSL configuration
        ssl_context = None
        if sslmode:
            import ssl as ssl_module
            ssl_context = ssl_module.create_default_context()

            if sslcert and sslkey:
                ssl_context.load_cert_chain(sslcert, sslkey)
            if sslrootcert:
                ssl_context.load_verify_locations(sslrootcert)
            else:
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl_module.CERT_NONE

        # Create connection pool
        pool = await asyncpg.create_pool(
            dsn,
            ssl=ssl_context,
            min_size=5,
            max_size=20,
            command_timeout=60
        )
        ctx.request_context.lifespan_context.pool = pool
        ctx.request_context.lifespan_context.dsn = dsn
        ctx.request_context.lifespan_context.current_database = database

        # Test connection
        async with pool.acquire() as conn:
            version = await conn.fetchval("SELECT version()")

        #self.server.current_database = database

        return {
            "success": True,
            "message": f"Connected to CockroachDB at {host}:{port}/{database}",
            "server_version": version,
            "current_database": database
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()
async def list_databases(ctx: Context) -> Dict[str, Any]:
    """List all databases in the CockroachDB cluster.

    Returns:
        A list of databases with row count or an error message.
    """

    pool = ctx.request_context.lifespan_context.pool
    if not pool:
        raise Exception("Not connected to database")

    query = """
    SELECT 
        database_name,
        owner,
        primary_region,
        regions,
        survival_goal
    FROM [SHOW DATABASES]
    ORDER BY database_name
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query)

    return {
        "databases": [dict(row) for row in rows],
        "count": len(rows)
    }

@mcp.tool()
async def get_connection_status(ctx: Context) -> Dict[str, Any]:
    """Get the current connection status and details.

    Returns:
        The connection status or an error message.
    """

    pool = ctx.request_context.lifespan_context.pool
    if not pool:
        return {"connected": False}

    try:
        async with pool.acquire() as conn:
            result = await conn.fetchrow("""
            SELECT 
                current_database() as database,
                current_user() as user,
                pg_backend_pid() as backend_pid
            """)

        return {
            "connected": True,
            "details": dict(result),
            "pool_stats": {
                "size": pool.get_size(),
                "min_size": pool.get_min_size(),
                "max_size": pool.get_max_size()
            }
        }

    except Exception as e:
        return {
            "connected": False,
            "error": str(e)
        }

@mcp.tool()
async def switch_database(ctx: Context, database: str) -> Dict[str, Any]:
    """Switch the connection to a different database.

    Args:
        database (str): Name of the database to switch to.

    Returns:
        A success message or an error message.
    """

    pool = ctx.request_context.lifespan_context.pool
    dns = ctx.request_context.lifespan_context.dns
    if not pool:
        raise Exception("Not connected to database")

    try:
        # Close current pool
        pool.terminate()

        # Create new pool with different database
        # Extract connection info from current pool
        dsn_parts = str(dns).split('/')
        base_dsn = '/'.join(dsn_parts[:-1])
        new_dsn = f"{base_dsn}/{database}"

        ctx.request_context.lifespan_context.pool = await asyncpg.create_pool(
            new_dsn,
            min_size=5,
            max_size=20,
            command_timeout=60
        )

        ctx.request_context.lifespan_context.database = database
        ctx.request_context.lifespan_context.dns = new_dsn

        return {
            "success": True,
            "message": f"Switched to database: {database}",
            "current_database": database
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()
async def get_active_connections(ctx: Context) -> Dict[str, Any]:
    """List active connections/sessions to the current database.

    Returns:
        Active sessions on the cluster.
    """
    pool = ctx.request_context.lifespan_context.pool
    if not pool:
        raise Exception("Not connected to database")
    try:
        query = """
        SELECT
            session_id,
            user_name,
            client_address,
            application_name,
            active_query_start,
            last_active_query,
            session_start,
            status
        FROM [SHOW SESSIONS]
        ORDER BY session_start DESC
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(query)
        return {
            "connections": [dict(row) for row in rows],
            "count": len(rows)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool()
async def get_database_settings(ctx: Context) -> Dict[str, Any]:
    """Retrieve current database or cluster settings.

    Returns:
        All cluster settings.
    """
    pool = ctx.request_context.lifespan_context.pool
    if not pool:
        raise Exception("Not connected to database")
    try:
        query = "SHOW ALL CLUSTER SETTINGS"
        async with pool.acquire() as conn:
            rows = await conn.fetch(query)
        return {
            "settings": [dict(row) for row in rows],
            "count": len(rows)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    
@mcp.tool()    
async def create_database(ctx: Context, database_name: str) -> Dict[str, Any]:
    """Enable the creation of new databases. 
    
    Args:
        database_name (str): Name of the database to create.
    
    Returns:
        A success message or an error message.
    """
    pool = ctx.request_context.lifespan_context.pool
    if not pool:
        raise Exception("Not connected to database")
    try:
        async with pool.acquire() as conn:
            await conn.execute(f'CREATE DATABASE IF NOT EXISTS "{database_name}"')
        return {"success": True, "message": f"Database '{database_name}' created."}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool()
async def drop_database(ctx: Context, database_name: str) -> Dict[str, Any]:
    """Drop an existing database.
    
    Args:
        database_name (str): Name of the database to drop.
    
    Returns:
        A success message or an error message.
    """
    pool = ctx.request_context.lifespan_context.pool
    if not pool:
        raise Exception("Not connected to database")
    try:
        async with pool.acquire() as conn:
            await conn.execute(f'DROP DATABASE "{database_name}" CASCADE')
        return {"success": True, "message": f"Database '{database_name}' dropped."}
    except Exception as e:
        return {"success": False, "error": str(e)}