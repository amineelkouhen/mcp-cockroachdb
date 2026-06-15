"""BACKUP and RESTORE tools."""

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
    validate_backup_uri,
)
from src.common.tool_result import err, ok

log = get_logger("backup_restore")


def _require_writes_allowed() -> dict[str, Any] | None:
    if get_flags().read_only:
        return err("Server is in read-only mode; backup tools are disabled")
    return None


def _require_destructive(op: str) -> dict[str, Any] | None:
    flags = get_flags()
    if flags.read_only:
        return err(f"Server is in read-only mode; {op} is disabled")
    if not flags.allow_destructive:
        return err(f"{op} requires --allow-destructive at server startup")
    return None


@mcp.tool()
async def create_backup(
    ctx: Context,
    destination_uri: str,
    target: str = "",
    target_name: str = "",
    revision_history: bool = True,
) -> dict[str, Any]:
    """Take a backup of the cluster, a database, or a table.

    Args:
        destination_uri: Storage URI. Allowed schemes: s3, gs, azure, azure-blob,
            nodelocal, userfile, external.
        target: Optional scope. One of '' (cluster), 'DATABASE', 'TABLE'.
        target_name: When target is DATABASE or TABLE, the identifier to back up.
        revision_history: Include revision history. Default True.
    """
    if block := _require_writes_allowed():
        return block
    try:
        validate_backup_uri(destination_uri)
    except UnsafeIdentifierError as exc:
        return err(exc)
    scope = (target or "").upper()
    if scope not in ("", "DATABASE", "TABLE"):
        return err("target must be '' (cluster), 'DATABASE', or 'TABLE'")
    sql_target = ""
    if scope:
        if not target_name:
            return err(f"target_name is required when target is {scope}")
        try:
            ident = quote_identifier(target_name, kind=scope.lower())
        except UnsafeIdentifierError as exc:
            return err(exc)
        sql_target = f"{scope} {ident} "
    options = " WITH revision_history" if revision_history else ""
    sql = f"BACKUP {sql_target}INTO $1{options}"
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, destination_uri)
        return ok(
            message=f"BACKUP submitted to {destination_uri}",
            results=[serialize_row(dict(r)) for r in rows],
        )
    except Exception as exc:
        log.exception("create_backup failed")
        return err(exc)


@mcp.tool()
async def list_backups(ctx: Context, location_uri: str) -> dict[str, Any]:
    """List backups in a storage location.

    Args:
        location_uri: Storage URI to scan.
    """
    try:
        validate_backup_uri(location_uri)
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SHOW BACKUPS IN $1", location_uri)
        return ok(backups=[dict(r) for r in rows], count=len(rows))
    except Exception as exc:
        log.exception("list_backups failed")
        return err(exc)


@mcp.tool()
async def restore_backup(
    ctx: Context,
    source_uri: str,
    target: str = "",
    target_name: str = "",
    new_db_name: str = "",
    confirm: bool = False,
) -> dict[str, Any]:
    """Restore from a backup. Destructive: can overwrite existing data.

    Args:
        source_uri: Backup location URI.
        target: '' (full cluster), 'DATABASE', 'TABLE'.
        target_name: For DATABASE/TABLE.
        new_db_name: For database restores, an optional rename.
        confirm: Must be True.
    """
    if block := _require_destructive("restore_backup"):
        return block
    if not confirm:
        return err("Refusing to restore: pass confirm=True to proceed")
    try:
        validate_backup_uri(source_uri)
    except UnsafeIdentifierError as exc:
        return err(exc)
    scope = (target or "").upper()
    if scope not in ("", "DATABASE", "TABLE"):
        return err("target must be '' (cluster), 'DATABASE', or 'TABLE'")
    sql_target = ""
    options = ""
    if scope:
        if not target_name:
            return err(f"target_name is required when target is {scope}")
        try:
            ident = quote_identifier(target_name, kind=scope.lower())
        except UnsafeIdentifierError as exc:
            return err(exc)
        sql_target = f"{scope} {ident} "
        if scope == "DATABASE" and new_db_name:
            try:
                new_ident = quote_identifier(new_db_name, kind="database")
            except UnsafeIdentifierError as exc:
                return err(exc)
            options = f" WITH new_db_name = {new_ident}"
    sql = f"RESTORE {sql_target}FROM LATEST IN $1{options}"
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, source_uri)
        return ok(
            message=f"RESTORE submitted from {source_uri}",
            results=[serialize_row(dict(r)) for r in rows],
        )
    except Exception as exc:
        log.exception("restore_backup failed")
        return err(exc)


@mcp.tool()
async def list_scheduled_backups(ctx: Context) -> dict[str, Any]:
    """List all scheduled backups."""
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SHOW SCHEDULES")
        return ok(schedules=[serialize_row(dict(r)) for r in rows], count=len(rows))
    except Exception as exc:
        log.exception("list_scheduled_backups failed")
        return err(exc)
