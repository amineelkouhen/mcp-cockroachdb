"""Table, view, and index MCP tools."""

from __future__ import annotations

import urllib.parse
from datetime import datetime
from typing import Any

from mcp.server.fastmcp import Context

from src.common.config import get_flags
from src.common.connection import CockroachConnectionPool
from src.common.logging_config import get_logger
from src.common.server import mcp
from src.common.sql_safety import (
    UnsafeIdentifierError,
    quote_identifier,
    validate_identifier,
    validate_import_scheme,
)
from src.common.tool_result import err, ok

log = get_logger("table_management")

# Allowlist of column constraints. Constraints are SQL keywords / clauses; we
# validate the leading token to keep injection out while permitting expressive
# constraint definitions (e.g. "PRIMARY KEY", "NOT NULL", "DEFAULT now()").
_ALLOWED_CONSTRAINT_KEYWORDS = frozenset(
    {
        "PRIMARY",  # PRIMARY KEY
        "NOT",  # NOT NULL
        "NULL",
        "UNIQUE",
        "DEFAULT",
        "CHECK",
        "REFERENCES",
        "GENERATED",
        "COLLATE",
    }
)

# Allowlist of column data types (CockroachDB common set).
_ALLOWED_DATATYPES = frozenset(
    {
        "BOOL",
        "BOOLEAN",
        "INT",
        "INTEGER",
        "INT2",
        "INT4",
        "INT8",
        "BIGINT",
        "SMALLINT",
        "FLOAT",
        "FLOAT4",
        "FLOAT8",
        "REAL",
        "DOUBLE",
        "DECIMAL",
        "NUMERIC",
        "DATE",
        "TIME",
        "TIMETZ",
        "TIMESTAMP",
        "TIMESTAMPTZ",
        "INTERVAL",
        "STRING",
        "TEXT",
        "CHAR",
        "CHARACTER",
        "VARCHAR",
        "BYTES",
        "BLOB",
        "JSONB",
        "JSON",
        "UUID",
        "INET",
        "SERIAL",
        "SERIAL2",
        "SERIAL4",
        "SERIAL8",
        "BIGSERIAL",
        "SMALLSERIAL",
        "ARRAY",
        "VECTOR",  # CockroachDB v25.2+ native vector type
        "GEOMETRY",
        "GEOGRAPHY",
    }
)


def _validate_datatype(datatype: str) -> str:
    """Allow an alphanumeric/parens-only datatype string like INT or VARCHAR(255)."""
    if not datatype or len(datatype) > 64:
        raise UnsafeIdentifierError(f"Invalid datatype {datatype!r}")
    head = datatype.split("(", 1)[0].strip().upper()
    if head not in _ALLOWED_DATATYPES:
        raise UnsafeIdentifierError(
            f"Datatype {head!r} not in allowlist. See docs for supported types."
        )
    # Permit only safe characters in the full string (letters, digits, parens, comma, space)
    if not all(c.isalnum() or c in "(),. " for c in datatype):
        raise UnsafeIdentifierError(f"Datatype {datatype!r} contains unsafe characters")
    return datatype


def _validate_constraint(constraint: str) -> str:
    """Allow simple constraint clauses; reject SQL terminators."""
    if not constraint:
        return ""
    if any(c in constraint for c in [";", "--", "/*", "*/"]):
        raise UnsafeIdentifierError(f"Unsafe characters in constraint {constraint!r}")
    head = constraint.strip().split(None, 1)[0].upper()
    if head not in _ALLOWED_CONSTRAINT_KEYWORDS:
        raise UnsafeIdentifierError(
            f"Constraint must start with one of {sorted(_ALLOWED_CONSTRAINT_KEYWORDS)}"
        )
    return constraint


def _require_writes_allowed() -> dict[str, Any] | None:
    """Return an error dict if the server policy forbids write operations."""
    flags = get_flags()
    if flags.read_only:
        return err("Server is in read-only mode; write tools are disabled")
    return None


def _require_destructive_allowed(operation: str) -> dict[str, Any] | None:
    flags = get_flags()
    if flags.read_only:
        return err(f"Server is in read-only mode; {operation} is disabled")
    if not flags.allow_destructive:
        return err(f"{operation} requires --allow-destructive at server startup")
    return None


@mcp.tool()
async def create_table(
    ctx: Context, table_name: str, columns: list[dict[str, str]]
) -> dict[str, Any]:
    """Create a table with the given columns.

    Args:
        table_name: Table name. Must be a valid SQL identifier.
        columns: List of dicts. Each entry has:
            - name (str, required): column name
            - datatype (str, required): allowed CockroachDB datatype
            - constraint (str, optional): clause starting with PRIMARY KEY,
              NOT NULL, UNIQUE, DEFAULT, CHECK, REFERENCES, GENERATED, COLLATE

    Example:
        columns = [
            {"name": "id", "datatype": "SERIAL", "constraint": "PRIMARY KEY"},
            {"name": "username", "datatype": "TEXT", "constraint": "NOT NULL"},
            {"name": "created_at", "datatype": "TIMESTAMP"},
        ]
    """
    if block := _require_writes_allowed():
        return block
    try:
        table_ident = quote_identifier(table_name, kind="table")
        col_defs: list[str] = []
        for col in columns:
            name = col.get("name")
            datatype = col.get("datatype")
            constraint = col.get("constraint", "")
            if not name or not datatype:
                return err("Each column must have 'name' and 'datatype'")
            col_ident = quote_identifier(name, kind="column")
            dt = _validate_datatype(datatype)
            constr = _validate_constraint(constraint) if constraint else ""
            col_def = f"{col_ident} {dt}"
            if constr:
                col_def += f" {constr}"
            col_defs.append(col_def)
        sql = f"CREATE TABLE IF NOT EXISTS {table_ident} ({', '.join(col_defs)})"
    except UnsafeIdentifierError as exc:
        return err(exc)

    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(sql)
        return ok(message=f"Table {table_name!r} created.", definition=sql)
    except Exception as exc:
        log.exception("create_table failed")
        return err(exc)


@mcp.tool()
async def bulk_import(
    ctx: Context,
    table_name: str,
    file_url: str,
    format: str,
    delimiter: str = ",",
    skip_header: bool = True,
) -> dict[str, Any]:
    """Bulk-import data from a remote file into a table.

    Args:
        table_name: Destination table.
        file_url: URL to the data file. Allowed schemes: s3, azure, azure-blob,
            gs, http, https.
        format: 'csv' or 'avro'.
        delimiter: Single-character CSV delimiter. Default: ','.
        skip_header: Whether to skip the first row. Default: True.
    """
    if block := _require_writes_allowed():
        return block
    try:
        table_ident = quote_identifier(table_name, kind="table")
        parsed = urllib.parse.urlparse(file_url)
        validate_import_scheme(parsed.scheme)
        # asyncpg won't parameterize IMPORT INTO; we use safe string composition
        # against tight whitelists for the format and delimiter.
        if format not in ("csv", "avro"):
            return err(f"Unsupported format {format!r}; allowed: csv, avro")
        if not isinstance(delimiter, str) or len(delimiter) != 1:
            return err("delimiter must be a single character")
        if delimiter == "'":
            return err("delimiter cannot be a single quote")
    except UnsafeIdentifierError as exc:
        return err(exc)

    pool = await CockroachConnectionPool.get_connection_pool()
    try:
        async with pool.acquire() as conn:
            if format == "csv":
                # asyncpg supports placeholders for the data URI (a SQL value)
                # and for skip; delimiter is a literal single character we've
                # already validated.
                import_query = (
                    f"IMPORT INTO {table_ident} "
                    f"CSV DATA ($1) "
                    f"WITH delimiter = '{delimiter}', skip = $2"
                )
                result = await conn.execute(import_query, file_url, "1" if skip_header else "0")
            else:  # avro
                import_query = f"IMPORT INTO {table_ident} AVRO DATA ($1)"
                result = await conn.execute(import_query, file_url)
        return ok(result=result)
    except Exception as exc:
        log.exception("bulk_import failed")
        return err(exc)


@mcp.tool()
async def drop_table(ctx: Context, table_name: str, confirm: bool = False) -> dict[str, Any]:
    """Drop a table.

    Args:
        table_name: Table name. Must be a valid SQL identifier.
        confirm: Must be True. Refusal is the default for destructive ops.

    Refused unless server runs with --allow-destructive and confirm=True.
    """
    if block := _require_destructive_allowed("drop_table"):
        return block
    if not confirm:
        return err(f"Refusing to drop table {table_name!r}: pass confirm=True to proceed")
    try:
        ident = quote_identifier(table_name, kind="table")
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"DROP TABLE {ident} CASCADE")
        return ok(message=f"Table {table_name!r} dropped.")
    except Exception as exc:
        log.exception("drop_table failed")
        return err(exc)


@mcp.tool()
async def create_index(
    ctx: Context, table_name: str, index_name: str, columns: list[str]
) -> dict[str, Any]:
    """Create an index on a table.

    Args:
        table_name: Target table.
        index_name: New index name.
        columns: One or more column names.
    """
    if block := _require_writes_allowed():
        return block
    try:
        table_ident = quote_identifier(table_name, kind="table")
        index_ident = quote_identifier(index_name, kind="index")
        col_idents = ", ".join(quote_identifier(c, kind="column") for c in columns)
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"CREATE INDEX {index_ident} ON {table_ident} ({col_idents})")
        return ok(message=f"Index {index_name!r} created on {table_name!r}.")
    except Exception as exc:
        log.exception("create_index failed")
        return err(exc)


@mcp.tool()
async def drop_index(ctx: Context, index_name: str, confirm: bool = False) -> dict[str, Any]:
    """Drop an index.

    Args:
        index_name: Index name. May be schema-qualified (table@index).
        confirm: Must be True.
    """
    if block := _require_destructive_allowed("drop_index"):
        return block
    if not confirm:
        return err(f"Refusing to drop index {index_name!r}: pass confirm=True to proceed")
    # Index names in CockroachDB can be schema-qualified as table@index;
    # we accept either bare identifier or table@index.
    try:
        if "@" in index_name:
            table_part, idx_part = index_name.split("@", 1)
            table_ident = quote_identifier(table_part, kind="table")
            idx_ident = quote_identifier(idx_part, kind="index")
            ident = f"{table_ident}@{idx_ident}"
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
        log.exception("drop_index failed")
        return err(exc)


@mcp.tool()
async def create_view(ctx: Context, view_name: str, query: str) -> dict[str, Any]:
    """Create a view from a SELECT query.

    Args:
        view_name: View name. Must be a valid SQL identifier.
        query: A SELECT statement.
    """
    if block := _require_writes_allowed():
        return block
    try:
        ident = quote_identifier(view_name, kind="view")
    except UnsafeIdentifierError as exc:
        return err(exc)
    # We cannot parameterize the view body. The query is supplied by the
    # caller, so this tool is effectively as privileged as execute_query.
    # Refuse anything that isn't a SELECT.
    head = query.strip().split(None, 1)[0].upper() if query.strip() else ""
    if head not in ("SELECT", "WITH"):
        return err("View body must be a SELECT or WITH (CTE) statement")
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"CREATE VIEW IF NOT EXISTS {ident} AS {query}")
        return ok(message=f"View {view_name!r} created.")
    except Exception as exc:
        log.exception("create_view failed")
        return err(exc)


@mcp.tool()
async def drop_view(ctx: Context, view_name: str, confirm: bool = False) -> dict[str, Any]:
    """Drop a view.

    Args:
        view_name: View name.
        confirm: Must be True.
    """
    if block := _require_destructive_allowed("drop_view"):
        return block
    if not confirm:
        return err(f"Refusing to drop view {view_name!r}: pass confirm=True to proceed")
    try:
        ident = quote_identifier(view_name, kind="view")
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"DROP VIEW {ident} CASCADE")
        return ok(message=f"View {view_name!r} dropped.")
    except Exception as exc:
        log.exception("drop_view failed")
        return err(exc)


@mcp.tool()
async def list_tables(ctx: Context, db_schema: str = "public") -> dict[str, Any]:
    """List all tables in the given schema (default 'public')."""
    try:
        validate_identifier(db_schema, kind="schema")
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    t.table_name,
                    t.table_type,
                    t.table_schema,
                    s.estimated_row_count
                FROM information_schema.tables t
                LEFT JOIN crdb_internal.table_row_statistics s
                    ON t.table_name = s.table_name
                WHERE t.table_schema = $1
                ORDER BY t.table_name
                """,
                db_schema,
            )
        return ok(tables=[dict(r) for r in rows], schema=db_schema, count=len(rows))
    except Exception as exc:
        log.exception("list_tables failed")
        return err(exc)


@mcp.tool()
async def describe_table(
    ctx: Context, table_name: str, db_schema: str = "public"
) -> dict[str, Any]:
    """Return columns, constraints, indexes, and range metadata for a table."""
    try:
        validate_identifier(db_schema, kind="schema")
        # validate_identifier so that subsequent SHOW INDEXES FROM <ident> is safe
        validate_identifier(table_name, kind="table")
    except UnsafeIdentifierError as exc:
        return err(exc)
    database = CockroachConnectionPool.current_database
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            columns = await conn.fetch(
                """
                SELECT
                    column_name, data_type, is_nullable, column_default,
                    character_maximum_length, numeric_precision, numeric_scale,
                    is_identity, generation_expression, ordinal_position
                FROM information_schema.columns
                WHERE table_name = $1 AND table_schema = $2
                ORDER BY ordinal_position
                """,
                table_name,
                db_schema,
            )
            constraints = await conn.fetch(
                """
                SELECT
                    tc.constraint_name, tc.constraint_type, kcu.column_name,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name,
                    cc.check_clause
                FROM information_schema.table_constraints tc
                LEFT JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                LEFT JOIN information_schema.constraint_column_usage ccu
                    ON ccu.constraint_name = tc.constraint_name
                LEFT JOIN information_schema.check_constraints cc
                    ON tc.constraint_name = cc.constraint_name
                WHERE tc.table_name = $1 AND tc.table_schema = $2
                """,
                table_name,
                db_schema,
            )
            # SHOW INDEXES and SHOW RANGES don't accept parameters, but table_name
            # and database are validated identifiers above.
            t_ident = quote_identifier(table_name, kind="table")
            db_ident = quote_identifier(database, kind="database") if database else None
            indexes = await conn.fetch(
                f"SELECT index_name, non_unique, column_name, direction, storing, implicit "
                f"FROM [SHOW INDEXES FROM {t_ident}] "
                f"ORDER BY index_name, seq_in_index"
            )
            metadata = None
            if db_ident:
                metadata = await conn.fetchrow(
                    f"SELECT range_id, schema_name, table_name, range_size_mb, "
                    f"lease_holder, lease_holder_locality, replicas, "
                    f"replica_localities, range_size, span_stats "
                    f"FROM [SHOW RANGES FROM DATABASE {db_ident} WITH TABLES, KEYS, DETAILS] "
                    f"WHERE table_name = $1",
                    table_name,
                )
        return ok(
            database=database,
            schema=db_schema,
            table=table_name,
            columns=[dict(r) for r in columns],
            constraints=[dict(r) for r in constraints],
            indexes=[dict(r) for r in indexes],
            metadata=dict(metadata) if metadata else None,
        )
    except Exception as exc:
        log.exception("describe_table failed")
        return err(exc)


@mcp.tool()
async def list_views(ctx: Context, db_schema: str = "public") -> dict[str, Any]:
    """List all views in the given schema."""
    try:
        validate_identifier(db_schema, kind="schema")
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    table_name AS view_name,
                    view_definition
                FROM information_schema.views
                WHERE table_schema = $1
                ORDER BY table_name
                """,
                db_schema,
            )
        return ok(views=[dict(r) for r in rows], schema=db_schema, count=len(rows))
    except Exception as exc:
        log.exception("list_views failed")
        return err(exc)


@mcp.tool()
async def get_table_relationships(ctx: Context, table_name: str | None = None) -> dict[str, Any]:
    """List foreign-key relationships, optionally filtered by table."""
    if table_name is not None:
        try:
            validate_identifier(table_name, kind="table")
        except UnsafeIdentifierError as exc:
            return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        params = []
        sql = """
        SELECT
            tc.table_name,
            kcu.column_name,
            ccu.table_name AS foreign_table_name,
            ccu.column_name AS foreign_column_name,
            rc.constraint_name,
            rc.update_rule,
            rc.delete_rule
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage AS ccu
            ON ccu.constraint_name = tc.constraint_name
        JOIN information_schema.referential_constraints AS rc
            ON tc.constraint_name = rc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
        """
        if table_name:
            sql += " AND tc.table_name = $1"
            params.append(table_name)
        sql += " ORDER BY tc.table_name, kcu.ordinal_position"
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return ok(relationships=[dict(r) for r in rows], count=len(rows))
    except Exception as exc:
        log.exception("get_table_relationships failed")
        return err(exc)


@mcp.tool()
async def analyze_schema(ctx: Context, db_schema: str = "public") -> dict[str, Any]:
    """Summarize tables, views, and relationships for a schema."""
    tables = await list_tables(ctx, db_schema)
    views = await list_views(ctx, db_schema)
    relationships = await get_table_relationships(ctx)
    if not all(r.get("success", False) for r in (tables, views, relationships)):
        return err(
            "One or more sub-queries failed",
            tables=tables,
            views=views,
            relationships=relationships,
        )
    return ok(
        schema=db_schema,
        summary={
            "table_count": tables["count"],
            "view_count": views["count"],
            "relationship_count": relationships["count"],
        },
        tables=tables["tables"],
        views=views["views"],
        relationships=relationships["relationships"],
        generated_at=datetime.now().isoformat(),
    )
