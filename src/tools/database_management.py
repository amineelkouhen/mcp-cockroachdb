from mcp.server.fastmcp import Context
from typing import Dict, Any
from src.common.server import mcp
from src.common.connection import CockroachConnectionPool

@mcp.tool()
async def connect(ctx: Context) -> Dict[str, Any]:
    """Connect to the default CockroachDB database and create a connection pool.

    Returns:
        A success message or an error message.
    """
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        # Test connection
        async with pool.acquire() as conn:
            version = await conn.fetchval("SELECT version()")
            database = await conn.fetchval("SELECT current_database()")

        ctx.request_context.lifespan_context.current_database = database
        return {
            "success": True,
            "message": f"Connected to CockroachDB with DSN: {CockroachConnectionPool.dsn}",
            "server_version": version,
            "current_database": database
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()
async def connect_database(ctx: Context, host: str, database: str, port: int, username: str, password: str, 
                                sslmode: str, sslcert: str, sslkey: str, sslrootcert: str) -> Dict[str, Any]:
    """Connect to a CockroachDB database and create a connection pool.

    Args:
        host (str): CockroachDB host.
        port (int): CockroachDB port (default: 26257).
        database (str): Database name (default: "defaultdb").
        username (str): Username (default: "root").
        password (str): Password.
        sslmode (str): SSL mode (default: disable - Possible values: allow, prefer, require, verify-ca, verify-full).
        sslcert (str): Path to user certificate file.
        sslkey (str): Path to user key file.
        sslrootcert (str): Path to CA certificate file.

    Returns:
        A success message or an error message.
    """
    try:
        pool = await CockroachConnectionPool.refresh_connection_pool(
            host=host,
            port=port or 26257,
            database=database or 'defaultdb',
            username=username or 'root',
            password=password,
            sslmode=sslmode or 'disable',
            sslcert=sslcert,
            sslkey=sslkey,
            sslrootcert=sslrootcert
        )
        # Test connection
        async with pool.acquire() as conn:
            version = await conn.fetchval("SELECT version()")
            database = await conn.fetchval("SELECT current_database()")

        ctx.request_context.lifespan_context.current_database = database
        return {
            "success": True,
            "message": f"Connected to CockroachDB with DSN: {CockroachConnectionPool.dsn}",
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

    pool = await CockroachConnectionPool.get_connection_pool()
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

    pool = await CockroachConnectionPool.get_connection_pool()
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
    pool = await CockroachConnectionPool.get_connection_pool()
    if not pool:
        raise Exception("Not connected to database")

    try:
        # Close current pool
        pool.terminate()

        # Create new pool with different database
        # Extract connection info from current pool
        dsn_parts = str(CockroachConnectionPool.dsn).split('/')
        base_dsn = '/'.join(dsn_parts[:-1])
        new_dsn = f"{base_dsn}/{database}"

        pool = await CockroachConnectionPool.create_connection_pool(new_dsn)
        ctx.request_context.lifespan_context.current_database = database

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
    pool = await CockroachConnectionPool.get_connection_pool()
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
    pool = await CockroachConnectionPool.get_connection_pool()
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
    pool = await CockroachConnectionPool.get_connection_pool()
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
    current_database: str = ctx.request_context.lifespan_context.current_database
    if(database_name == 'defaultdb'):
        return {"success": False, "error": "Cannot drop the default database."}
    if(database_name.lower() == current_database.lower()):
        await switch_database(ctx, 'defaultdb')

    pool = await CockroachConnectionPool.get_connection_pool()
    if not pool:
        raise Exception("Not connected to database")
    try:
        async with pool.acquire() as conn:
            await conn.execute(f'DROP DATABASE IF EXISTS "{database_name.lower()}" CASCADE')
        return {"success": True, "message": f"Database '{database_name.lower()}' dropped."}
    except Exception as e:
        return {"success": False, "error": str(e)}