"""Diagnostics tools: tracing, statement bundles."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context

from src.common.connection import CockroachConnectionPool
from src.common.logging_config import get_logger
from src.common.serializers import serialize_row
from src.common.server import mcp
from src.common.sql_safety import UnsafeIdentifierError, validate_node_id
from src.common.tool_result import err, ok

log = get_logger("diagnostics")


@mcp.tool()
async def get_recent_traces(
    ctx: Context, limit: int = 20, node_id: int | None = None
) -> dict[str, Any]:
    """Return recent tracing spans from the cluster.

    Args:
        limit: Max rows (1..1000). Default 20.
        node_id: Optional node id filter.
    """
    if not isinstance(limit, int) or limit < 1 or limit > 1000:
        return err("limit must be 1..1000")
    args: list[Any] = []
    sql = (
        "SELECT trace_id, node_id, root_op_name, num_spans, duration "
        "FROM crdb_internal.cluster_inflight_traces"
    )
    if node_id is not None:
        try:
            args.append(validate_node_id(node_id))
            sql += f" WHERE node_id = ${len(args)}"
        except UnsafeIdentifierError as exc:
            return err(exc)
    sql += f" ORDER BY duration DESC LIMIT {int(limit)}"
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
        return ok(traces=[serialize_row(dict(r)) for r in rows], count=len(rows))
    except Exception as exc:
        log.exception("get_recent_traces failed")
        return err(exc)


@mcp.tool()
async def list_statement_diagnostics_requests(ctx: Context, limit: int = 20) -> dict[str, Any]:
    """List pending or completed statement-diagnostic bundle requests."""
    if not isinstance(limit, int) or limit < 1 or limit > 1000:
        return err("limit must be 1..1000")
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, statement_fingerprint, requested_at, completed, "
                "statement_diagnostics_id, expires_at "
                "FROM system.statement_diagnostics_requests "
                f"ORDER BY requested_at DESC LIMIT {int(limit)}"
            )
        return ok(requests=[serialize_row(dict(r)) for r in rows], count=len(rows))
    except Exception as exc:
        log.exception("list_statement_diagnostics_requests failed")
        return err(exc)


@mcp.tool()
async def request_statement_diagnostics(ctx: Context, statement_fingerprint: str) -> dict[str, Any]:
    """Ask the cluster to collect a diagnostics bundle for a statement fingerprint.

    Args:
        statement_fingerprint: The statement fingerprint (text). The bundle is
            collected on the next execution of a matching statement.
    """
    if not isinstance(statement_fingerprint, str) or not statement_fingerprint:
        return err("statement_fingerprint must be a non-empty string")
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "SELECT crdb_internal.request_statement_bundle($1, 0, '0', '0')",
                statement_fingerprint,
            )
        return ok(
            message=f"Requested diagnostics bundle for fingerprint {statement_fingerprint!r}."
        )
    except Exception as exc:
        log.exception("request_statement_diagnostics failed")
        return err(exc)
