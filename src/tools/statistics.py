"""Table statistics tools for the CockroachDB optimizer."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context

from src.common.config import get_flags
from src.common.connection import CockroachConnectionPool
from src.common.logging_config import get_logger
from src.common.serializers import serialize_row
from src.common.server import mcp
from src.common.sql_safety import UnsafeIdentifierError, quote_identifier
from src.common.tool_result import err, ok

log = get_logger("statistics")


def _require_writes_allowed() -> dict[str, Any] | None:
    if get_flags().read_only:
        return err("Server is in read-only mode; statistics writes disabled")
    return None


@mcp.tool()
async def create_statistics(
    ctx: Context, table_name: str, stats_name: str = "auto_stats"
) -> dict[str, Any]:
    """Compute and store table statistics for the optimizer.

    Args:
        table_name: Target table.
        stats_name: Statistics name. Default 'auto_stats'.
    """
    if block := _require_writes_allowed():
        return block
    try:
        t_ident = quote_identifier(table_name, kind="table")
        s_ident = quote_identifier(stats_name, kind="statistics")
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"CREATE STATISTICS {s_ident} FROM {t_ident}")
        return ok(message=f"Statistics {stats_name!r} created for {table_name!r}.")
    except Exception as exc:
        log.exception("create_statistics failed")
        return err(exc)


@mcp.tool()
async def show_statistics(ctx: Context, table_name: str) -> dict[str, Any]:
    """Show statistics for a table.

    Args:
        table_name: Target table.
    """
    try:
        t_ident = quote_identifier(table_name, kind="table")
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(f"SHOW STATISTICS FOR TABLE {t_ident}")
        return ok(statistics=[serialize_row(dict(r)) for r in rows], count=len(rows))
    except Exception as exc:
        log.exception("show_statistics failed")
        return err(exc)
