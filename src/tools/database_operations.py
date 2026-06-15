"""Database-level MCP tools: connect, list/create/drop/switch databases, sessions."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context

from src.common.config import get_flags
from src.common.connection import (
    CockroachConnectionPool,
    replace_database_in_url,
)
from src.common.logging_config import get_logger
from src.common.server import mcp
from src.common.sql_safety import (
    UnsafeIdentifierError,
    quote_identifier,
    redact_dsn,
    validate_ssl_mode,
)
from src.common.tool_result import err, ok

log = get_logger("database_operations")


@mcp.tool()
async def connect(ctx: Context) -> dict[str, Any]:
    """Connect to the default CockroachDB database and create a connection pool.

    Returns a success object with the redacted DSN, server version, and current
    database, or an error.
    """
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            version = await conn.fetchval("SELECT version()")
            database = await conn.fetchval("SELECT current_database()")
        return ok(
            message=f"Connected to CockroachDB at {redact_dsn(CockroachConnectionPool.database_url)}",
            server_version=version,
            current_database=database,
        )
    except Exception as exc:
        log.exception("connect failed")
        return err(exc)


@mcp.tool()
async def connect_database(
    ctx: Context,
    host: str,
    database: str,
    port: int,
    username: str,
    password: str,
    sslmode: str,
    sslcert: str,
    sslkey: str,
    sslrootcert: str,
) -> dict[str, Any]:
    """Connect to a different CockroachDB database and create a connection pool.

    Args:
        host: CockroachDB host.
        port: CockroachDB port (default: 26257).
        database: Database name (default: "defaultdb").
        username: Username (default: "root").
        password: Password.
        sslmode: SSL mode. One of: disable, allow, prefer, require, verify-ca, verify-full.
        sslcert: Path to client certificate file.
        sslkey: Path to client key file.
        sslrootcert: Path to CA certificate file.
    """
    try:
        sslmode = validate_ssl_mode(sslmode or "disable")
        await CockroachConnectionPool.refresh_connection_pool(
            host=host,
            port=port or 26257,
            database=database or "defaultdb",
            username=username or "root",
            password=password,
            sslmode=sslmode,
            sslcert=sslcert,
            sslkey=sslkey,
            sslrootcert=sslrootcert,
        )
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            version = await conn.fetchval("SELECT version()")
            current_db = await conn.fetchval("SELECT current_database()")
        return ok(
            message=f"Connected to CockroachDB at {redact_dsn(CockroachConnectionPool.database_url)}",
            server_version=version,
            current_database=current_db,
        )
    except Exception as exc:
        log.exception("connect_database failed")
        return err(exc)


@mcp.tool()
async def list_databases(ctx: Context) -> dict[str, Any]:
    """List all databases visible to the connected user."""
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    database_name,
                    owner,
                    primary_region,
                    regions,
                    survival_goal
                FROM [SHOW DATABASES]
                ORDER BY database_name
                """
            )
        return ok(databases=[dict(r) for r in rows], count=len(rows))
    except Exception as exc:
        log.exception("list_databases failed")
        return err(exc)


@mcp.tool()
async def get_connection_status(ctx: Context) -> dict[str, Any]:
    """Get the current connection status, pool stats, and active user/db."""
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    current_database() as database,
                    current_user() as "user",
                    pg_backend_pid() as backend_pid
                """
            )
        return ok(
            connected=True,
            details=dict(row),
            pool_stats={
                "size": pool.get_size(),
                "min_size": pool.get_min_size(),
                "max_size": pool.get_max_size(),
            },
        )
    except Exception as exc:
        log.exception("get_connection_status failed")
        return err(exc, connected=False)


@mcp.tool()
async def switch_database(ctx: Context, database: str) -> dict[str, Any]:
    """Switch the connection pool to a different database.

    Args:
        database: Name of the database to switch to. Must be a valid SQL identifier.
    """
    try:
        # Validate the identifier even though we're using it as the path of a
        # DSN (not interpolated into SQL). This guards against arbitrary text
        # like 'foo?param=x' that would corrupt the new DSN.
        quote_identifier(database, kind="database")
    except UnsafeIdentifierError as exc:
        return err(exc)

    try:
        old_database = CockroachConnectionPool.current_database
        new_dsn = replace_database_in_url(CockroachConnectionPool.database_url, database)
        await CockroachConnectionPool.create_connection_pool(new_dsn)
        return ok(
            message=f"Switched from {old_database!r} to {CockroachConnectionPool.current_database!r}",
            current_database=CockroachConnectionPool.current_database,
        )
    except Exception as exc:
        log.exception("switch_database failed")
        return err(exc)


@mcp.tool()
async def get_active_connections(ctx: Context) -> dict[str, Any]:
    """List active sessions on the cluster."""
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
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
            )
        return ok(connections=[dict(r) for r in rows], count=len(rows))
    except Exception as exc:
        log.exception("get_active_connections failed")
        return err(exc)


@mcp.tool()
async def get_database_settings(ctx: Context) -> dict[str, Any]:
    """Retrieve cluster settings (SHOW ALL CLUSTER SETTINGS)."""
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SHOW ALL CLUSTER SETTINGS")
        return ok(settings=[dict(r) for r in rows], count=len(rows))
    except Exception as exc:
        log.exception("get_database_settings failed")
        return err(exc)


@mcp.tool()
async def create_database(ctx: Context, database_name: str) -> dict[str, Any]:
    """Create a new database.

    Args:
        database_name: Name of the database. Must be a valid SQL identifier.

    Refused when the server runs in --read-only mode.
    """
    flags = get_flags()
    if flags.read_only:
        return err("Server is in read-only mode; create_database is disabled")
    try:
        ident = quote_identifier(database_name, kind="database")
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"CREATE DATABASE IF NOT EXISTS {ident}")
        return ok(message=f"Database {database_name!r} created.")
    except Exception as exc:
        log.exception("create_database failed")
        return err(exc)


@mcp.tool()
async def drop_database(ctx: Context, database_name: str, confirm: bool = False) -> dict[str, Any]:
    """Drop a database.

    Args:
        database_name: Name of the database. Must be a valid SQL identifier.
        confirm: Must be set to True. Tools refuse to execute destructive
            operations without explicit confirmation, even when the server
            runs in --allow-destructive mode.

    Refused when the server runs in --read-only mode or without
    --allow-destructive.
    """
    flags = get_flags()
    if flags.read_only:
        return err("Server is in read-only mode; drop_database is disabled")
    if not flags.allow_destructive:
        return err("Destructive operations require --allow-destructive at server startup")
    if not confirm:
        return err(f"Refusing to drop database {database_name!r}: pass confirm=True to proceed")
    if database_name.lower() == "defaultdb":
        return err("Cannot drop the default database.")
    try:
        ident = quote_identifier(database_name, kind="database")
    except UnsafeIdentifierError as exc:
        return err(exc)
    # If we're dropping the currently active database, switch away first.
    if database_name.lower() == CockroachConnectionPool.current_database.lower():
        switch_result = await switch_database(ctx, "defaultdb")
        if not switch_result.get("success", False):
            return switch_result
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"DROP DATABASE IF EXISTS {ident} CASCADE")
        return ok(message=f"Database {database_name!r} dropped.")
    except Exception as exc:
        log.exception("drop_database failed")
        return err(exc)
