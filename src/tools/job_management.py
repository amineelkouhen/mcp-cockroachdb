"""Job management tools: list, status, pause, resume, cancel."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context

from src.common.config import get_flags
from src.common.connection import CockroachConnectionPool
from src.common.logging_config import get_logger
from src.common.serializers import serialize_row
from src.common.server import mcp
from src.common.sql_safety import UnsafeIdentifierError, validate_job_id
from src.common.tool_result import err, ok

log = get_logger("job_management")

ALLOWED_JOB_STATUSES = frozenset(
    {
        "pending",
        "running",
        "paused",
        "pause-requested",
        "cancel-requested",
        "succeeded",
        "failed",
        "canceled",
        "reverting",
        "retry-running",
    }
)


@mcp.tool()
async def list_jobs(
    ctx: Context, status: str = "", job_type: str = "", limit: int = 50
) -> dict[str, Any]:
    """List jobs from the cluster.

    Args:
        status: Optional status filter (e.g. 'running', 'succeeded').
        job_type: Optional type filter (e.g. 'BACKUP', 'CHANGEFEED', 'SCHEMA CHANGE').
        limit: Max rows (1..1000).
    """
    if not isinstance(limit, int) or limit < 1 or limit > 1000:
        return err("limit must be an integer 1..1000")
    if status and status.lower() not in ALLOWED_JOB_STATUSES:
        return err(f"status must be one of {sorted(ALLOWED_JOB_STATUSES)}")
    if job_type:
        try:
            # Job type is uppercased SQL keyword - allow letters and spaces
            if not all(c.isalpha() or c in " _" for c in job_type) or len(job_type) > 40:
                raise UnsafeIdentifierError(f"Invalid job_type {job_type!r}")
        except UnsafeIdentifierError as exc:
            return err(exc)
    conds: list[str] = []
    args: list[Any] = []
    if status:
        conds.append(f"status = ${len(args) + 1}")
        args.append(status.lower())
    if job_type:
        conds.append(f"job_type = ${len(args) + 1}")
        args.append(job_type.upper())
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    sql = (
        "SELECT job_id, job_type, description, statement, user_name, status, "
        "running_status, created, started, finished, modified, fraction_completed, "
        "error, coordinator_id "
        f"FROM [SHOW JOBS]{where} "
        f"ORDER BY created DESC LIMIT {int(limit)}"
    )
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
        return ok(jobs=[serialize_row(dict(r)) for r in rows], count=len(rows))
    except Exception as exc:
        log.exception("list_jobs failed")
        return err(exc)


@mcp.tool()
async def get_job_status(ctx: Context, job_id: int) -> dict[str, Any]:
    """Get the status of a single job by id."""
    try:
        jid = validate_job_id(job_id)
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM [SHOW JOB $1]"
                if False
                else "SELECT * FROM crdb_internal.jobs WHERE job_id = $1",
                jid,
            )
        return ok(job=serialize_row(dict(row)) if row else None)
    except Exception as exc:
        log.exception("get_job_status failed")
        return err(exc)


def _require_destructive(op: str) -> dict[str, Any] | None:
    flags = get_flags()
    if flags.read_only:
        return err(f"Server is in read-only mode; {op} is disabled")
    if not flags.allow_destructive:
        return err(f"{op} requires --allow-destructive at server startup")
    return None


@mcp.tool()
async def pause_job(ctx: Context, job_id: int) -> dict[str, Any]:
    """Pause a running job. Reversible via resume_job."""
    if get_flags().read_only:
        return err("Server is in read-only mode; pause_job is disabled")
    try:
        jid = validate_job_id(job_id)
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"PAUSE JOB {jid}")
        return ok(message=f"Job {jid} paused.")
    except Exception as exc:
        log.exception("pause_job failed")
        return err(exc)


@mcp.tool()
async def resume_job(ctx: Context, job_id: int) -> dict[str, Any]:
    """Resume a paused job."""
    if get_flags().read_only:
        return err("Server is in read-only mode; resume_job is disabled")
    try:
        jid = validate_job_id(job_id)
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"RESUME JOB {jid}")
        return ok(message=f"Job {jid} resumed.")
    except Exception as exc:
        log.exception("resume_job failed")
        return err(exc)


@mcp.tool()
async def cancel_job(ctx: Context, job_id: int, confirm: bool = False) -> dict[str, Any]:
    """Cancel a running or paused job. Cannot be undone.

    Args:
        job_id: Job id.
        confirm: Must be True.
    """
    if block := _require_destructive("cancel_job"):
        return block
    if not confirm:
        return err(f"Refusing to cancel job {job_id}: pass confirm=True")
    try:
        jid = validate_job_id(job_id)
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"CANCEL JOB {jid}")
        return ok(message=f"Job {jid} canceled.")
    except Exception as exc:
        log.exception("cancel_job failed")
        return err(exc)
