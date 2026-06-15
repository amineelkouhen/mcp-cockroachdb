"""Changefeed (CDC) tools."""

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
    validate_changefeed_sink,
    validate_job_id,
)
from src.common.tool_result import err, ok

log = get_logger("changefeeds")


def _require_writes_allowed() -> dict[str, Any] | None:
    if get_flags().read_only:
        return err("Server is in read-only mode; changefeed writes disabled")
    return None


def _require_destructive(op: str) -> dict[str, Any] | None:
    flags = get_flags()
    if flags.read_only:
        return err(f"Server is in read-only mode; {op} is disabled")
    if not flags.allow_destructive:
        return err(f"{op} requires --allow-destructive at server startup")
    return None


@mcp.tool()
async def create_changefeed(
    ctx: Context,
    tables: list[str],
    sink_uri: str,
    format: str = "json",
    envelope: str = "wrapped",
    full_table_name: bool = True,
) -> dict[str, Any]:
    """Create a changefeed that emits row changes from tables to a sink.

    Args:
        tables: One or more table names to watch.
        sink_uri: Sink URI. Allowed schemes: kafka, webhook-http(s), s3, gs,
            azure-blob, experimental-sql, external, null.
        format: 'json' or 'avro'. Default 'json'.
        envelope: 'wrapped' (default), 'key_only', 'row', 'bare'.
        full_table_name: Include database.schema.table in the topic. Default True.
    """
    if block := _require_writes_allowed():
        return block
    try:
        if not tables:
            return err("tables list is empty")
        idents = ", ".join(quote_identifier(t, kind="table") for t in tables)
        validate_changefeed_sink(sink_uri)
    except UnsafeIdentifierError as exc:
        return err(exc)
    if format not in ("json", "avro"):
        return err("format must be 'json' or 'avro'")
    if envelope not in ("wrapped", "key_only", "row", "bare"):
        return err("envelope must be one of wrapped, key_only, row, bare")
    opts = [f"format = '{format}'", f"envelope = '{envelope}'"]
    if full_table_name:
        opts.append("full_table_name")
    opts_sql = ", ".join(opts)
    sql = f"CREATE CHANGEFEED FOR {idents} INTO $1 WITH {opts_sql}"
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, sink_uri)
        return ok(
            message=f"Changefeed created for {len(tables)} table(s)",
            results=[serialize_row(dict(r)) for r in rows],
        )
    except Exception as exc:
        log.exception("create_changefeed failed")
        return err(exc)


@mcp.tool()
async def list_changefeeds(ctx: Context, limit: int = 50) -> dict[str, Any]:
    """List CHANGEFEED jobs."""
    if not isinstance(limit, int) or limit < 1 or limit > 1000:
        return err("limit must be 1..1000")
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT job_id, description, user_name, status, created, started, "
                "finished, high_water_timestamp, error "
                "FROM [SHOW CHANGEFEED JOBS] "
                f"ORDER BY created DESC LIMIT {int(limit)}"
            )
        return ok(changefeeds=[serialize_row(dict(r)) for r in rows], count=len(rows))
    except Exception as exc:
        log.exception("list_changefeeds failed")
        return err(exc)


@mcp.tool()
async def pause_changefeed(ctx: Context, job_id: int) -> dict[str, Any]:
    """Pause a changefeed."""
    if get_flags().read_only:
        return err("Server is in read-only mode; pause_changefeed disabled")
    try:
        jid = validate_job_id(job_id)
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"PAUSE JOB {jid}")
        return ok(message=f"Changefeed job {jid} paused.")
    except Exception as exc:
        log.exception("pause_changefeed failed")
        return err(exc)


@mcp.tool()
async def resume_changefeed(ctx: Context, job_id: int) -> dict[str, Any]:
    """Resume a paused changefeed."""
    if get_flags().read_only:
        return err("Server is in read-only mode; resume_changefeed disabled")
    try:
        jid = validate_job_id(job_id)
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"RESUME JOB {jid}")
        return ok(message=f"Changefeed job {jid} resumed.")
    except Exception as exc:
        log.exception("resume_changefeed failed")
        return err(exc)


@mcp.tool()
async def cancel_changefeed(ctx: Context, job_id: int, confirm: bool = False) -> dict[str, Any]:
    """Cancel a changefeed.

    Args:
        job_id: Job id.
        confirm: Must be True.
    """
    if block := _require_destructive("cancel_changefeed"):
        return block
    if not confirm:
        return err(f"Refusing to cancel changefeed {job_id}: pass confirm=True")
    try:
        jid = validate_job_id(job_id)
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"CANCEL JOB {jid}")
        return ok(message=f"Changefeed job {jid} canceled.")
    except Exception as exc:
        log.exception("cancel_changefeed failed")
        return err(exc)
