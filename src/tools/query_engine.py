"""Query execution, transactions, EXPLAIN, performance, history."""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any

from mcp.server.fastmcp import Context

from src.common.config import get_flags
from src.common.connection import CockroachConnectionPool
from src.common.logging_config import get_logger
from src.common.serializers import serialize_row
from src.common.server import mcp
from src.common.sql_safety import (
    UnsafeIdentifierError,
    validate_format,
    validate_interval,
)
from src.common.tool_result import err, ok

log = get_logger("query_engine")


def _is_write_statement(query: str) -> bool:
    """True if the leading keyword indicates a write or DDL statement."""
    head = query.strip().split(None, 1)[0].upper() if query.strip() else ""
    write_keywords = {
        "INSERT",
        "UPDATE",
        "DELETE",
        "TRUNCATE",
        "MERGE",
        "CREATE",
        "DROP",
        "ALTER",
        "RENAME",
        "GRANT",
        "REVOKE",
        "IMPORT",
        "BACKUP",
        "RESTORE",
        "SET",
        "RESET",
    }
    return head in write_keywords


@mcp.tool()
async def execute_query(
    ctx: Context,
    query: str,
    params: list[Any] | None = None,
    format: str = "json",
    limit: int | None = None,
) -> dict[str, Any]:
    """Execute a SQL query with optional parameters and formatting.

    Args:
        query: SQL query. Pass values via params, not via string interpolation.
        params: Optional list of parameters substituted for $1, $2, ... in the
            query.
        format: One of 'json', 'csv', 'table'.
        limit: Optional integer; appends LIMIT n. Refused if query already
            contains a LIMIT clause.

    Refused if the server runs --read-only and the query is a write/DDL statement.
    """
    flags = get_flags()
    if flags.read_only and _is_write_statement(query):
        return err("Server is in read-only mode; refusing write/DDL statement")

    try:
        format = validate_format(format)
    except UnsafeIdentifierError as exc:
        return err(exc)

    if not query or not query.strip():
        return err("Query is empty")

    if limit is not None:
        if not isinstance(limit, int) or limit < 0 or limit > 10_000_000:
            return err("limit must be a non-negative integer up to 10_000_000")
        # Defensive: refuse if LIMIT is already present
        if " limit " in (" " + query.strip().lower()):
            return err("Query already contains LIMIT; do not also pass limit")
        query = f"{query} LIMIT {int(limit)}"

    pool = await CockroachConnectionPool.get_connection_pool()
    start = time.time()
    try:
        async with pool.acquire() as conn:
            if params:
                rows = await conn.fetch(query, *params)
            else:
                rows = await conn.fetch(query)
        duration = time.time() - start
        CockroachConnectionPool.query_history.append(
            {
                "query": query,
                "timestamp": datetime.now().isoformat(),
                "duration": duration,
                "row_count": len(rows),
                "success": True,
            }
        )
        serialized = [serialize_row(dict(r)) for r in rows]
        return ok(
            rows=serialized,
            row_count=len(rows),
            duration=duration,
            columns=list(dict(rows[0]).keys()) if rows else [],
            formatted_result=format_result(serialized, format),
        )
    except Exception as exc:
        duration = time.time() - start
        CockroachConnectionPool.query_history.append(
            {
                "query": query,
                "timestamp": datetime.now().isoformat(),
                "duration": duration,
                "row_count": 0,
                "success": False,
                "error": str(exc),
            }
        )
        log.exception("execute_query failed")
        return err(exc, duration=duration)


@mcp.tool()
async def execute_transaction(ctx: Context, queries: list[str]) -> dict[str, Any]:
    """Execute multiple SQL statements as a single transaction.

    Args:
        queries: List of SQL statements. They run in order in one transaction;
            the whole transaction is rolled back if any one fails.
    """
    flags = get_flags()
    if flags.read_only and any(_is_write_statement(q) for q in queries):
        return err("Server is in read-only mode; refusing write/DDL statements")

    if not queries:
        return err("queries list is empty")

    pool = await CockroachConnectionPool.get_connection_pool()
    results: list[dict[str, Any]] = []
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                for q in queries:
                    rows = await conn.fetch(q)
                    results.append(
                        {
                            "query": q,
                            "row_count": len(rows),
                            "rows": [serialize_row(dict(r)) for r in rows],
                        }
                    )
        return ok(
            results=results,
            message=f"Transaction committed with {len(queries)} statement(s)",
        )
    except Exception as exc:
        log.exception("execute_transaction failed")
        return err(exc, completed_statements=len(results), total_statements=len(queries))


@mcp.tool()
async def explain_query(ctx: Context, query: str, analyze: bool = False) -> dict[str, Any]:
    """Run EXPLAIN or EXPLAIN ANALYZE on a query.

    Args:
        query: SQL query to explain.
        analyze: If True, runs EXPLAIN ANALYZE (executes the query and reports stats).
    """
    flags = get_flags()
    if flags.read_only and analyze and _is_write_statement(query):
        return err("Server is in read-only mode; EXPLAIN ANALYZE would execute the statement")

    if not query or not query.strip():
        return err("Query is empty")

    prefix = "EXPLAIN ANALYZE" if analyze else "EXPLAIN"
    full_query = f"{prefix} {query}"
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(full_query)
        plan_text = "\n".join([r.get("info", r.get("plan", "")) for r in [dict(r) for r in rows]])
        if analyze:
            CockroachConnectionPool.query_history.append(
                {
                    "query": full_query,
                    "timestamp": datetime.now().isoformat(),
                    "row_count": len(rows),
                    "success": True,
                }
            )
        return ok(
            plan=[serialize_row(dict(r)) for r in rows],
            plan_text=plan_text,
            analyzed=analyze,
        )
    except Exception as exc:
        log.exception("explain_query failed")
        return err(exc)


@mcp.tool()
async def analyze_performance(
    ctx: Context, query: str = "", time_range: str = "1:0"
) -> dict[str, Any]:
    """Pull query performance stats from crdb_internal.statement_statistics.

    Args:
        query: Optional filter substring (case-insensitive LIKE match).
        time_range: 'minutes:seconds' interval. Default '1:0' = last minute.
    """
    try:
        time_range = validate_interval(time_range, kind="time_range")
    except UnsafeIdentifierError as exc:
        return err(exc)

    pool = await CockroachConnectionPool.get_connection_pool()
    base_sql = """
        SELECT
            aggregated_ts,
            query,
            full_scan,
            follower_read,
            execution_count,
            max_latency,
            min_latency,
            p50_latency,
            p90_latency,
            p99_latency,
            avg_rows_read,
            avg_rows_written
        FROM (
            SELECT
                aggregated_ts,
                json_extract_path_text(metadata, 'query') AS query,
                cast(json_extract_path_text(metadata, 'fullScan') AS BOOL) AS full_scan,
                cast(json_extract_path_text(statistics, 'statistics', 'cnt') AS INT) AS execution_count,
                cast(json_extract_path_text(statistics, 'statistics', 'usedFollowerRead') AS BOOL) AS follower_read,
                cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'max') AS FLOAT) AS max_latency,
                cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'min') AS FLOAT) AS min_latency,
                cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'p50') AS FLOAT) AS p50_latency,
                cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'p90') AS FLOAT) AS p90_latency,
                cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'p99') AS FLOAT) AS p99_latency,
                cast(json_extract_path_text(statistics, 'statistics', 'rowsRead', 'mean') AS FLOAT) AS avg_rows_read,
                cast(json_extract_path_text(statistics, 'statistics', 'rowsWritten', 'mean') AS FLOAT) AS avg_rows_written
            FROM crdb_internal.statement_statistics
        )
        WHERE aggregated_ts >= now() - $1::INTERVAL
        """
    if query:
        sql = base_sql + " AND LOWER(query) LIKE LOWER($2)"
        sql += " ORDER BY max_latency DESC LIMIT 20"
        args = [time_range, f"%{query}%"]
    else:
        sql = base_sql + " ORDER BY max_latency DESC LIMIT 20"
        args = [time_range]

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
        return ok(performance_data=[serialize_row(dict(r)) for r in rows])
    except Exception as exc:
        log.exception("analyze_performance failed")
        return err(exc)


@mcp.tool()
async def get_query_history(ctx: Context, limit: int = 10) -> dict[str, Any]:
    """Return the most recent N queries executed through this MCP server.

    Args:
        limit: Number of recent queries (default 10, max 1000).
    """
    if not isinstance(limit, int) or limit < 1 or limit > 1000:
        return err("limit must be an integer 1..1000")
    history = CockroachConnectionPool.query_history
    return ok(
        history=sorted(history[-limit:], key=lambda x: x["timestamp"], reverse=True),
        total_queries=len(history),
    )


def format_result(rows: list[dict[str, Any]], format: str) -> str | list[dict[str, Any]]:
    """Format a result set as json/csv/table; default returns the list itself."""
    if format == "csv":
        if not rows:
            return ""
        headers = list(rows[0].keys())
        lines = [",".join(headers)]
        for row in rows:
            values = []
            for h in headers:
                v = row.get(h, "")
                if v is None:
                    values.append("")
                else:
                    s = str(v)
                    if "," in s or '"' in s or "\n" in s:
                        s = '"' + s.replace('"', '""') + '"'
                    values.append(s)
            lines.append(",".join(values))
        return "\n".join(lines)

    if format == "json":
        return json.dumps(rows, indent=2)

    if format == "table":
        if not rows:
            return ""
        headers = list(rows[0].keys())
        widths = {h: len(h) for h in headers}
        for row in rows:
            for h in headers:
                widths[h] = max(widths[h], len(str(row.get(h, ""))))
        lines = [
            " | ".join(h.ljust(widths[h]) for h in headers),
            " | ".join("-" * widths[h] for h in headers),
        ]
        for row in rows:
            lines.append(" | ".join(str(row.get(h, "")).ljust(widths[h]) for h in headers))
        return "\n".join(lines)

    return rows
