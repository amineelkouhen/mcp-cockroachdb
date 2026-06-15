"""Vector similarity search tools (CockroachDB v25.2+ VECTOR + C-SPANN)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context

from src.common.config import get_flags
from src.common.connection import CockroachConnectionPool
from src.common.logging_config import get_logger
from src.common.serializers import serialize_row
from src.common.server import mcp
from src.common.sql_safety import (
    VECTOR_METRIC_OPCLASS,
    VECTOR_METRIC_OPERATORS,
    UnsafeIdentifierError,
    quote_identifier,
    validate_identifier,
    validate_vector_metric,
)
from src.common.tool_result import err, ok

log = get_logger("vector_search")


def _require_writes_allowed() -> dict[str, Any] | None:
    if get_flags().read_only:
        return err("Server is in read-only mode; vector index writes disabled")
    return None


def _require_destructive(op: str) -> dict[str, Any] | None:
    flags = get_flags()
    if flags.read_only:
        return err(f"Server is in read-only mode; {op} is disabled")
    if not flags.allow_destructive:
        return err(f"{op} requires --allow-destructive at server startup")
    return None


async def _detect_index_metric(pool, table_name: str, column_name: str) -> str | None:
    """Inspect indexes on (table, column) and return the matching metric, or None."""
    sql = """
        SELECT i.indexrelid::regclass AS index_name,
               am.amname AS access_method,
               pg_get_indexdef(i.indexrelid) AS def
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indrelid
        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        JOIN pg_class ic ON ic.oid = i.indexrelid
        JOIN pg_am am ON am.oid = ic.relam
        WHERE c.relname = $1 AND a.attname = $2
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, table_name, column_name)
    for r in rows:
        d = (r["def"] or "").lower()
        for metric, opclass in VECTOR_METRIC_OPCLASS.items():
            if opclass in d:
                return metric
    return None


@mcp.tool()
async def vector_similarity_search(
    ctx: Context,
    table_name: str,
    vector_column: str,
    query_vector: list[float],
    metric: str = "cosine",
    limit: int = 10,
    select_columns: list[str] | None = None,
    where: str = "",
    where_params: list[Any] | None = None,
) -> dict[str, Any]:
    """Top-K nearest-neighbour search using CockroachDB vector operators.

    Args:
        table_name: Source table.
        vector_column: VECTOR column to search.
        query_vector: Embedding as a list of floats. Must match column dimension.
        metric: 'cosine' (default), 'l2', 'ip', or 'auto' (match the index opclass).
        limit: Top-K. Default 10, max 1000.
        select_columns: Columns to return alongside distance. Default returns all.
        where: Optional WHERE clause with parameter placeholders. Values must
            be passed via where_params (use $2, $3, ... since $1 is the vector).
        where_params: Values for the WHERE clause placeholders.

    Returns:
        Rows sorted by distance ascending. Each row includes 'distance' and a
        derived 'similarity' (1 - distance for cosine; metric-appropriate for others).
    """
    if not isinstance(limit, int) or limit < 1 or limit > 1000:
        return err("limit must be an integer 1..1000")
    if not isinstance(query_vector, list) or not query_vector:
        return err("query_vector must be a non-empty list of floats")
    try:
        for v in query_vector:
            float(v)
    except (TypeError, ValueError):
        return err("query_vector elements must be numbers")

    try:
        validate_identifier(table_name, kind="table")
        validate_identifier(vector_column, kind="column")
        chosen_metric = validate_vector_metric(metric)
        sel_idents = "*"
        if select_columns:
            for c in select_columns:
                validate_identifier(c, kind="column")
            sel_idents = ", ".join(quote_identifier(c, kind="column") for c in select_columns)
    except UnsafeIdentifierError as exc:
        return err(exc)

    pool = await CockroachConnectionPool.get_connection_pool()

    # Resolve auto: read the index opclass.
    if chosen_metric == "auto":
        detected = await _detect_index_metric(pool, table_name, vector_column)
        chosen_metric = detected or "cosine"

    op = VECTOR_METRIC_OPERATORS[chosen_metric]
    t_ident = quote_identifier(table_name, kind="table")
    v_ident = quote_identifier(vector_column, kind="column")
    # CockroachDB accepts VECTOR literals as the array string. We pass the
    # vector as a parameter and let asyncpg encode it.
    where_clause = f" WHERE {where}" if where else ""
    where_args = where_params or []
    sql = (
        f"SELECT {sel_idents}, ({v_ident} {op} $1::VECTOR) AS distance "
        f"FROM {t_ident}{where_clause} "
        f"ORDER BY {v_ident} {op} $1::VECTOR ASC "
        f"LIMIT {int(limit)}"
    )
    args: list[Any] = [query_vector] + list(where_args)

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
        out = []
        for r in rows:
            d = dict(r)
            dist = d.get("distance")
            if dist is not None:
                if chosen_metric == "cosine":
                    d["similarity"] = 1.0 - float(dist)
                elif chosen_metric == "ip":
                    d["similarity"] = -float(dist)
                else:  # l2 - no canonical similarity, leave as distance
                    d["similarity"] = None
            out.append(serialize_row(d))
        return ok(metric=chosen_metric, results=out, count=len(out))
    except Exception as exc:
        log.exception("vector_similarity_search failed")
        return err(exc)


@mcp.tool()
async def create_cspann_index(
    ctx: Context,
    table_name: str,
    column_name: str,
    metric: str = "cosine",
    index_name: str = "",
) -> dict[str, Any]:
    """Create a C-SPANN ANN index on a VECTOR column.

    Args:
        table_name: Target table.
        column_name: VECTOR column to index.
        metric: 'cosine' (default), 'l2', or 'ip'. Determines the opclass.
        index_name: Optional explicit index name.
    """
    if block := _require_writes_allowed():
        return block
    try:
        t_ident = quote_identifier(table_name, kind="table")
        c_ident = quote_identifier(column_name, kind="column")
        if metric not in VECTOR_METRIC_OPCLASS:
            return err(f"metric must be one of {sorted(VECTOR_METRIC_OPCLASS)}")
        opclass = VECTOR_METRIC_OPCLASS[metric]
        idx_name = index_name or f"{table_name}_{column_name}_{metric}_cspann"
        idx_ident = quote_identifier(idx_name, kind="index")
    except UnsafeIdentifierError as exc:
        return err(exc)
    sql = f"CREATE VECTOR INDEX IF NOT EXISTS {idx_ident} ON {t_ident} ({c_ident} {opclass})"
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(sql)
        return ok(
            message=f"C-SPANN index {idx_name!r} created on {table_name!r}.{column_name!r} ({metric})",
            opclass=opclass,
        )
    except Exception as exc:
        log.exception("create_cspann_index failed")
        return err(exc)


@mcp.tool()
async def drop_cspann_index(ctx: Context, index_name: str, confirm: bool = False) -> dict[str, Any]:
    """Drop a C-SPANN index.

    Args:
        index_name: Index name. May be table@index.
        confirm: Must be True.
    """
    if block := _require_destructive("drop_cspann_index"):
        return block
    if not confirm:
        return err(f"Refusing to drop index {index_name!r}: pass confirm=True")
    try:
        if "@" in index_name:
            t, i = index_name.split("@", 1)
            ident = f"{quote_identifier(t, kind='table')}@{quote_identifier(i, kind='index')}"
        else:
            ident = quote_identifier(index_name, kind="index")
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"DROP INDEX {ident}")
        return ok(message=f"Index {index_name!r} dropped.")
    except Exception as exc:
        log.exception("drop_cspann_index failed")
        return err(exc)
