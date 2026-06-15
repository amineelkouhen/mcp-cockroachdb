"""Cluster monitoring MCP tools."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mcp.server.fastmcp import Context

from src.common.connection import CockroachConnectionPool
from src.common.logging_config import get_logger
from src.common.serializers import serialize_row
from src.common.server import mcp
from src.common.sql_safety import (
    UnsafeIdentifierError,
    quote_identifier,
    validate_identifier,
    validate_interval,
)
from src.common.tool_result import err, ok

log = get_logger("cluster_monitoring")


@mcp.tool()
async def get_cluster_status(ctx: Context, detailed: bool = False) -> dict[str, Any]:
    """Get cluster health and node distribution.

    Args:
        detailed: If True, return per-node capacity, range counts, etc.
    """
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            cluster_info: list[Any] = list(await conn.fetch("SHOW CLUSTER SETTING version"))
            cluster_info.extend(
                await conn.fetch(
                    """
                    SELECT
                        sum(capacity) AS cluster_capacity,
                        sum(available) AS available_capacity,
                        sum(used) AS used_capacity,
                        sum(range_count) AS total_ranges
                    FROM crdb_internal.kv_store_status
                    """
                )
            )
            if detailed:
                nodes = await conn.fetch(
                    """
                    SELECT g.*, capacity, s.available, s.used,
                           s.logical_bytes, s.range_count
                    FROM crdb_internal.gossip_nodes g
                    LEFT JOIN crdb_internal.kv_store_status s
                        ON g.node_id = s.node_id
                    """
                )
            else:
                nodes = await conn.fetch(
                    "SELECT node_id, address, is_live FROM crdb_internal.gossip_nodes"
                )
        return ok(cluster_status=_format_cluster_status(cluster_info, nodes))
    except Exception as exc:
        log.exception("get_cluster_status failed")
        return err(exc)


@mcp.tool()
async def show_running_queries(
    ctx: Context,
    node_id: int = 0,
    user: str = "",
    min_duration: str = "1:0",
) -> dict[str, Any]:
    """Show currently running queries on the cluster.

    Args:
        node_id: Node ID to filter, or 0 for all nodes.
        user: User name to filter, or "" for all users.
        min_duration: 'minutes:seconds' min duration. Default '1:0'.
    """
    try:
        min_duration = validate_interval(min_duration, kind="min_duration")
        if not isinstance(node_id, int) or node_id < 0:
            return err("node_id must be a non-negative integer")
        if user:
            # Username allowed chars: identifier rules apply
            validate_identifier(user, kind="user")
    except UnsafeIdentifierError as exc:
        return err(exc)

    sql = "SELECT * FROM crdb_internal.cluster_queries WHERE (now() - start) > $1::INTERVAL"
    args: list[Any] = [min_duration]
    if node_id:
        sql += " AND node_id = $2"
        args.append(node_id)
    if user:
        sql += f" AND user_name = ${len(args) + 1}"
        args.append(user)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
        return ok(queries=[serialize_row(dict(r)) for r in rows])
    except Exception as exc:
        log.exception("show_running_queries failed")
        return err(exc)


@mcp.tool()
async def get_replication_status(ctx: Context, table_name: str = "") -> dict[str, Any]:
    """Get replication and distribution status for a table or the whole database.

    Args:
        table_name: Table name to filter, or "" for the whole database.
    """
    if table_name:
        try:
            validate_identifier(table_name, kind="table")
        except UnsafeIdentifierError as exc:
            return err(exc)

    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            if table_name:
                t_ident = quote_identifier(table_name, kind="table")
                sql = (
                    "SELECT r.range_id, r.replicas, r.voting_replicas, "
                    "r.replica_localities, r.lease_holder, r.range_size "
                    f"FROM [SHOW RANGES FROM TABLE {t_ident}] t "
                    "LEFT JOIN crdb_internal.ranges r ON r.range_id = t.range_id"
                )
            else:
                database = CockroachConnectionPool.current_database
                if not database:
                    return err("No current database; call connect first")
                db_ident = quote_identifier(database, kind="database")
                sql = (
                    "SELECT r.range_id, r.replicas, r.voting_replicas, "
                    "r.replica_localities, r.lease_holder, r.range_size "
                    f"FROM [SHOW RANGES FROM DATABASE {db_ident}] d "
                    "LEFT JOIN crdb_internal.ranges r ON r.range_id = d.range_id"
                )
            rows = await conn.fetch(sql)
        return ok(replication_status=[serialize_row(dict(r)) for r in rows])
    except Exception as exc:
        log.exception("get_replication_status failed")
        return err(exc)


def _format_cluster_status(cluster_info: list[Any], nodes: list[Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "cluster_settings": [dict(r) for r in cluster_info],
        "nodes": [dict(r) for r in nodes],
        "node_count": len(nodes),
        "healthy_nodes": len([n for n in nodes if dict(n).get("is_live", False)]),
        "timestamp": datetime.now().isoformat(),
    }
    if nodes:
        node_data = [dict(r) for r in nodes]
        out["summary"] = {
            "total_nodes": len(node_data),
            "available_nodes": len([n for n in node_data if n.get("is_live", False)]),
            "node_addresses": [n.get("address", "unknown") for n in node_data],
        }
    return out


@mcp.tool()
async def get_query_insights(
    ctx: Context,
    query_filter: str = "",
    min_execution_time_ms: int = 100,
    limit: int = 50,
) -> dict[str, Any]:
    """Slow/problematic queries from crdb_internal.cluster_execution_insights.

    Args:
        query_filter: Optional case-insensitive substring filter.
        min_execution_time_ms: Minimum execution time. Default 100ms.
        limit: Max rows (1..1000). Default 50.
    """
    if not isinstance(min_execution_time_ms, int) or min_execution_time_ms < 0:
        return err("min_execution_time_ms must be a non-negative integer")
    if not isinstance(limit, int) or limit < 1 or limit > 1000:
        return err("limit must be an integer 1..1000")

    sql = """
        SELECT
            session_id, txn_id, stmt_id, problem, causes, query, status,
            start_time, end_time, full_scan, user_name, app_name,
            database_name, rows_read, rows_written, retries, contention,
            cpu_sql_nanos, index_recommendations
        FROM crdb_internal.cluster_execution_insights
        WHERE (EXTRACT(EPOCH FROM (end_time - start_time)) * 1000) >= $1
    """
    args: list[Any] = [min_execution_time_ms]
    if query_filter:
        sql += " AND LOWER(query) LIKE LOWER($2)"
        args.append(f"%{query_filter}%")
    sql += f" ORDER BY end_time DESC LIMIT {int(limit)}"

    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
        insights = [serialize_row(dict(r)) for r in rows]
        return ok(
            insights=insights,
            summary={
                "total_insights": len(insights),
                "full_scan_queries": sum(1 for i in insights if i.get("full_scan")),
                "queries_with_contention": sum(
                    1 for i in insights if i.get("contention") and i["contention"] != "00:00:00"
                ),
                "queries_with_retries": sum(1 for i in insights if (i.get("retries") or 0) > 0),
            },
        )
    except Exception as exc:
        log.exception("get_query_insights failed")
        return err(exc)


@mcp.tool()
async def get_slow_queries(
    ctx: Context,
    query_filter: str = "",
    min_duration_seconds: float = 1.0,
    limit: int = 50,
) -> dict[str, Any]:
    """Slow queries from statement_statistics, ordered by max latency.

    Args:
        query_filter: Optional case-insensitive substring filter on the query
            text. Compared with LIKE.
        min_duration_seconds: Minimum max-latency in seconds. Default 1.0.
        limit: Max rows (1..1000). Default 50.
    """
    if not isinstance(min_duration_seconds, (int, float)) or min_duration_seconds < 0:
        return err("min_duration_seconds must be a non-negative number")
    if not isinstance(limit, int) or limit < 1 or limit > 1000:
        return err("limit must be an integer 1..1000")

    sql = """
        SELECT
            aggregated_ts, fingerprint_id,
            json_extract_path_text(metadata, 'query') AS query,
            json_extract_path_text(metadata, 'db') AS database_name,
            json_extract_path_text(metadata, 'user') AS user_name,
            cast(json_extract_path_text(metadata, 'fullScan') AS BOOL) AS full_scan,
            cast(json_extract_path_text(statistics, 'statistics', 'cnt') AS INT) AS execution_count,
            cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'max') AS FLOAT) AS max_latency_seconds,
            cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'min') AS FLOAT) AS min_latency_seconds,
            cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'p50') AS FLOAT) AS p50_latency_seconds,
            cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'p90') AS FLOAT) AS p90_latency_seconds,
            cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'p99') AS FLOAT) AS p99_latency_seconds,
            cast(json_extract_path_text(statistics, 'statistics', 'rowsRead', 'mean') AS FLOAT) AS avg_rows_read,
            cast(json_extract_path_text(statistics, 'statistics', 'rowsWritten', 'mean') AS FLOAT) AS avg_rows_written,
            cast(json_extract_path_text(statistics, 'statistics', 'contentionTime', 'mean') AS FLOAT) AS avg_contention_seconds
        FROM crdb_internal.statement_statistics
        WHERE cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'max') AS FLOAT) >= $1
    """
    args: list[Any] = [float(min_duration_seconds)]
    if query_filter:
        sql += " AND LOWER(json_extract_path_text(metadata, 'query')) LIKE LOWER($2)"
        args.append(f"%{query_filter}%")
    sql += (
        " ORDER BY cast(json_extract_path_text(statistics, 'statistics', "
        "'latencyInfo', 'max') AS FLOAT) DESC "
        f"LIMIT {int(limit)}"
    )

    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
        return ok(
            slow_queries=[serialize_row(dict(r)) for r in rows],
            count=len(rows),
            threshold_seconds=float(min_duration_seconds),
        )
    except Exception as exc:
        log.exception("get_slow_queries failed")
        return err(exc)


@mcp.tool()
async def get_contention_events(
    ctx: Context, table_filter: str = "", limit: int = 50
) -> dict[str, Any]:
    """Recent contention events from crdb_internal.transaction_contention_events.

    Args:
        table_filter: Optional substring filter on table_name (case-insensitive).
        limit: Max rows (1..1000). Default 50.
    """
    if not isinstance(limit, int) or limit < 1 or limit > 1000:
        return err("limit must be an integer 1..1000")

    sql = """
        SELECT
            collection_ts, blocking_txn_id, blocking_txn_fingerprint_id,
            waiting_txn_id, waiting_txn_fingerprint_id, contention_duration,
            contending_pretty_key, waiting_stmt_id, database_name,
            schema_name, table_name, index_name, contention_type
        FROM crdb_internal.transaction_contention_events
    """
    args: list[Any] = []
    if table_filter:
        sql += " WHERE LOWER(table_name) LIKE LOWER($1)"
        args.append(f"%{table_filter}%")
    sql += f" ORDER BY collection_ts DESC LIMIT {int(limit)}"

    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
        events = [serialize_row(dict(r)) for r in rows]
        tables_affected: dict[str, int] = {}
        for e in events:
            t = e.get("table_name") or "unknown"
            tables_affected[t] = tables_affected.get(t, 0) + 1
        return ok(
            contention_events=events,
            count=len(events),
            tables_affected=tables_affected,
        )
    except Exception as exc:
        log.exception("get_contention_events failed")
        return err(exc)


@mcp.tool()
async def get_transaction_insights(
    ctx: Context, query_filter: str = "", limit: int = 50
) -> dict[str, Any]:
    """Transaction insights from crdb_internal.cluster_txn_execution_insights.

    Args:
        query_filter: Optional substring filter on query text.
        limit: Max rows (1..1000). Default 50.
    """
    if not isinstance(limit, int) or limit < 1 or limit > 1000:
        return err("limit must be an integer 1..1000")

    sql = """
        SELECT
            txn_id, txn_fingerprint_id, query, status, start_time, end_time,
            user_name, app_name, rows_read, rows_written, retries,
            contention, problems, causes, cpu_sql_nanos, last_retry_reason,
            stmt_execution_ids
        FROM crdb_internal.cluster_txn_execution_insights
    """
    args: list[Any] = []
    if query_filter:
        sql += " WHERE LOWER(query) LIKE LOWER($1)"
        args.append(f"%{query_filter}%")
    sql += f" ORDER BY end_time DESC LIMIT {int(limit)}"

    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
        insights = [serialize_row(dict(r)) for r in rows]
        return ok(
            transaction_insights=insights,
            summary={
                "total_transactions": len(insights),
                "transactions_with_retries": sum(
                    1 for i in insights if (i.get("retries") or 0) > 0
                ),
                "transactions_with_contention": sum(
                    1 for i in insights if i.get("contention") and i["contention"] != "00:00:00"
                ),
            },
        )
    except Exception as exc:
        log.exception("get_transaction_insights failed")
        return err(exc)


@mcp.tool()
async def get_index_recommendations(ctx: Context) -> dict[str, Any]:
    """Distinct non-empty index recommendations across recent queries."""
    sql = """
        SELECT DISTINCT
            index_recommendations,
            query,
            database_name
        FROM crdb_internal.cluster_execution_insights
        WHERE index_recommendations IS NOT NULL
          AND array_length(index_recommendations, 1) > 0
        ORDER BY database_name
    """
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql)
        recommendations: list[dict[str, Any]] = []
        for r in rows:
            row_dict = dict(r)
            recs = row_dict.get("index_recommendations", [])
            if recs:
                recommendations.append(
                    {
                        "database": row_dict.get("database_name"),
                        "query": row_dict.get("query"),
                        "recommendations": recs,
                    }
                )
        return ok(
            index_recommendations=recommendations,
            total_recommendations=len(recommendations),
        )
    except Exception as exc:
        log.exception("get_index_recommendations failed")
        return err(exc)
