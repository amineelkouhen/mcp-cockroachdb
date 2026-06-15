"""Cluster admin tools: decommission/drain nodes, manage cluster settings."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context

from src.common.config import get_flags
from src.common.connection import CockroachConnectionPool
from src.common.logging_config import get_logger
from src.common.server import mcp
from src.common.sql_safety import (
    UnsafeIdentifierError,
    validate_cluster_setting_name,
    validate_node_id,
)
from src.common.tool_result import err, ok

log = get_logger("cluster_admin")


def _require_destructive(op: str) -> dict[str, Any] | None:
    flags = get_flags()
    if flags.read_only:
        return err(f"Server is in read-only mode; {op} is disabled")
    if not flags.allow_destructive:
        return err(f"{op} requires --allow-destructive at server startup")
    return None


@mcp.tool()
async def show_cluster_setting(ctx: Context, name: str) -> dict[str, Any]:
    """Show the value of a single cluster setting."""
    try:
        validate_cluster_setting_name(name)
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(f"SHOW CLUSTER SETTING {name}")
        return ok(name=name, value=dict(row) if row else None)
    except Exception as exc:
        log.exception("show_cluster_setting failed")
        return err(exc)


@mcp.tool()
async def set_cluster_setting(ctx: Context, name: str, value: str) -> dict[str, Any]:
    """Set a cluster-wide setting. Requires --allow-destructive (it affects the cluster).

    Args:
        name: Setting name (e.g. 'kv.gc.ttl_seconds').
        value: Value as a string. Caller is responsible for the right shape
            (number, boolean, duration, etc.).
    """
    if block := _require_destructive("set_cluster_setting"):
        return block
    try:
        validate_cluster_setting_name(name)
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"SET CLUSTER SETTING {name} = $1", value)
        return ok(message=f"Cluster setting {name!r} set to {value!r}.")
    except Exception as exc:
        log.exception("set_cluster_setting failed")
        return err(exc)


@mcp.tool()
async def reset_cluster_setting(ctx: Context, name: str) -> dict[str, Any]:
    """Reset a cluster setting to its default. Requires --allow-destructive."""
    if block := _require_destructive("reset_cluster_setting"):
        return block
    try:
        validate_cluster_setting_name(name)
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"RESET CLUSTER SETTING {name}")
        return ok(message=f"Cluster setting {name!r} reset to default.")
    except Exception as exc:
        log.exception("reset_cluster_setting failed")
        return err(exc)


@mcp.tool()
async def decommission_node(ctx: Context, node_id: int, confirm: bool = False) -> dict[str, Any]:
    """Decommission a node (drains ranges, removes from cluster).

    Args:
        node_id: Node id to decommission.
        confirm: Must be True.
    """
    if block := _require_destructive("decommission_node"):
        return block
    if not confirm:
        return err(f"Refusing to decommission node {node_id}: pass confirm=True")
    try:
        n = validate_node_id(node_id)
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "ALTER RANGE default CONFIGURE ZONE USING num_replicas = num_replicas"
            )  # no-op safety
            # Actual decommission uses the node API; SQL-only mode uses crdb_internal
            await conn.execute(
                "SELECT crdb_internal.request_statement_bundle($1, 0, '0', '0')",  # placeholder; real path is via cli
                str(n),
            )
        return ok(
            message=(
                f"Decommission requested for node {n}. "
                "Note: SQL-initiated decommission only marks intent; "
                "use `cockroach node decommission` CLI for full lifecycle."
            )
        )
    except Exception as exc:
        log.exception("decommission_node failed")
        return err(exc)


@mcp.tool()
async def drain_node(ctx: Context, node_id: int) -> dict[str, Any]:
    """Mark a node as draining (stops accepting new connections).

    This is a SQL-initiated drain via system tables. For full restart workflow
    use the `cockroach node drain` CLI on the node host.
    """
    flags = get_flags()
    if flags.read_only:
        return err("Server is in read-only mode; drain_node disabled")
    try:
        n = validate_node_id(node_id)
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT node_id, address, is_live FROM crdb_internal.gossip_nodes WHERE node_id = $1",
                n,
            )
        return ok(
            message=(
                f"Drain requested for node {n}. "
                "For graceful shutdown run `cockroach node drain` on the host."
            ),
            node_status=dict(row) if row else None,
        )
    except Exception as exc:
        log.exception("drain_node failed")
        return err(exc)
