"""Multi-region tools: regions, survival goals, locality, zone config."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context

from src.common.config import get_flags
from src.common.connection import CockroachConnectionPool
from src.common.logging_config import get_logger
from src.common.serializers import serialize_row
from src.common.server import mcp
from src.common.sql_safety import (
    UnsafeIdentifierError,
    quote_identifier,
    validate_locality,
    validate_survival_goal,
)
from src.common.tool_result import err, ok

log = get_logger("multi_region")


def _require_writes_allowed() -> dict[str, Any] | None:
    if get_flags().read_only:
        return err("Server is in read-only mode; multi-region writes disabled")
    return None


@mcp.tool()
async def show_regions(ctx: Context) -> dict[str, Any]:
    """Show all regions available in the cluster."""
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SHOW REGIONS FROM CLUSTER")
        return ok(regions=[serialize_row(dict(r)) for r in rows], count=len(rows))
    except Exception as exc:
        log.exception("show_regions failed")
        return err(exc)


@mcp.tool()
async def show_database_regions(ctx: Context, database_name: str) -> dict[str, Any]:
    """Show regions configured for a database."""
    try:
        ident = quote_identifier(database_name, kind="database")
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(f"SHOW REGIONS FROM DATABASE {ident}")
        return ok(regions=[serialize_row(dict(r)) for r in rows], count=len(rows))
    except Exception as exc:
        log.exception("show_database_regions failed")
        return err(exc)


@mcp.tool()
async def add_database_region(ctx: Context, database_name: str, region_name: str) -> dict[str, Any]:
    """Add a region to a multi-region database.

    Args:
        database_name: Database to alter.
        region_name: Region (e.g. 'us-east1', 'europe-west1').
    """
    if block := _require_writes_allowed():
        return block
    try:
        db_ident = quote_identifier(database_name, kind="database")
        # Region names commonly have hyphens; allow but quote.
        if not all(c.isalnum() or c in "-_" for c in region_name) or len(region_name) > 64:
            raise UnsafeIdentifierError(f"Invalid region {region_name!r}")
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"ALTER DATABASE {db_ident} ADD REGION $1", region_name)
        return ok(message=f"Region {region_name!r} added to {database_name!r}.")
    except Exception as exc:
        log.exception("add_database_region failed")
        return err(exc)


@mcp.tool()
async def drop_database_region(
    ctx: Context, database_name: str, region_name: str, confirm: bool = False
) -> dict[str, Any]:
    """Drop a region from a multi-region database.

    Args:
        database_name: Database to alter.
        region_name: Region to remove.
        confirm: Must be True.
    """
    flags = get_flags()
    if flags.read_only:
        return err("Server is in read-only mode; drop_database_region disabled")
    if not flags.allow_destructive:
        return err("drop_database_region requires --allow-destructive")
    if not confirm:
        return err("Refusing to drop region: pass confirm=True to proceed")
    try:
        db_ident = quote_identifier(database_name, kind="database")
        if not all(c.isalnum() or c in "-_" for c in region_name) or len(region_name) > 64:
            raise UnsafeIdentifierError(f"Invalid region {region_name!r}")
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"ALTER DATABASE {db_ident} DROP REGION $1", region_name)
        return ok(message=f"Region {region_name!r} dropped from {database_name!r}.")
    except Exception as exc:
        log.exception("drop_database_region failed")
        return err(exc)


@mcp.tool()
async def set_survival_goal(ctx: Context, database_name: str, survival_goal: str) -> dict[str, Any]:
    """Set the survival goal for a multi-region database.

    Args:
        database_name: Database to alter.
        survival_goal: 'ZONE' or 'REGION'.
    """
    if block := _require_writes_allowed():
        return block
    try:
        db_ident = quote_identifier(database_name, kind="database")
        goal = validate_survival_goal(survival_goal)
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"ALTER DATABASE {db_ident} SURVIVE {goal} FAILURE")
        return ok(message=f"Survival goal for {database_name!r} set to {goal}.")
    except Exception as exc:
        log.exception("set_survival_goal failed")
        return err(exc)


@mcp.tool()
async def set_table_locality(
    ctx: Context, table_name: str, locality: str, region: str = ""
) -> dict[str, Any]:
    """Set a table's locality (REGIONAL, REGIONAL_BY_ROW, REGIONAL_BY_TABLE, GLOBAL).

    Args:
        table_name: Table to alter.
        locality: One of REGIONAL, REGIONAL_BY_ROW, REGIONAL_BY_TABLE, GLOBAL.
        region: For REGIONAL_BY_TABLE, the region to pin the table to.
    """
    if block := _require_writes_allowed():
        return block
    try:
        t_ident = quote_identifier(table_name, kind="table")
        loc = validate_locality(locality)
    except UnsafeIdentifierError as exc:
        return err(exc)
    if loc == "REGIONAL_BY_TABLE":
        if not region:
            return err("region is required when locality is REGIONAL_BY_TABLE")
        if not all(c.isalnum() or c in "-_" for c in region) or len(region) > 64:
            return err(f"Invalid region {region!r}")
        sql = f"ALTER TABLE {t_ident} SET LOCALITY REGIONAL BY TABLE IN $1"
        args: list[Any] = [region]
    elif loc == "REGIONAL_BY_ROW":
        sql = f"ALTER TABLE {t_ident} SET LOCALITY REGIONAL BY ROW"
        args = []
    elif loc == "REGIONAL":
        sql = f"ALTER TABLE {t_ident} SET LOCALITY REGIONAL"
        args = []
    else:  # GLOBAL
        sql = f"ALTER TABLE {t_ident} SET LOCALITY GLOBAL"
        args = []
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(sql, *args)
        return ok(message=f"Locality of {table_name!r} set to {loc.replace('_', ' ')}.")
    except Exception as exc:
        log.exception("set_table_locality failed")
        return err(exc)


@mcp.tool()
async def show_zone_config(ctx: Context, target_type: str, target_name: str) -> dict[str, Any]:
    """Show zone configuration for a database, table, or index.

    Args:
        target_type: 'DATABASE', 'TABLE', or 'INDEX'.
        target_name: Object name.
    """
    up = (target_type or "").upper()
    if up not in ("DATABASE", "TABLE", "INDEX"):
        return err("target_type must be DATABASE, TABLE, or INDEX")
    try:
        if "@" in target_name and up == "INDEX":
            t, i = target_name.split("@", 1)
            ident = f"{quote_identifier(t, kind='table')}@{quote_identifier(i, kind='index')}"
        else:
            ident = quote_identifier(target_name, kind=up.lower())
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(f"SHOW ZONE CONFIGURATION FROM {up} {ident}")
        return ok(zone_config=[serialize_row(dict(r)) for r in rows])
    except Exception as exc:
        log.exception("show_zone_config failed")
        return err(exc)
