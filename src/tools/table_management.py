from src.common.connection import CockroachConnectionPool
from mcp.server.fastmcp import Context
from typing import Dict, Any, List, Optional
from src.common.server import mcp
from datetime import datetime
import urllib.parse

@mcp.tool()
async def create_table(ctx: Context, table_name: str, columns: List[Dict[str, str]]) -> Dict[str, Any]:
    """Enable the creation of new tables in the current database. You can instruct the AI to define table names, columns, and their types, streamlining database setup and schema evolution directly through natural language. 
    
    Args:
        table_name (str): Name of the table.
        columns (List[Dict[str, str]]): List of dicts with keys:
            - 'name' (str): column name (required)
            - 'datatype' (str): column datatype (required)
            - 'constraint' (str): column constraint (optional)
    
    Returns:
        A success message or an error message.
    
    Example:
        columns = [
            {"name": "id", "datatype": "SERIAL", "constraint": "PRIMARY KEY"},
            {"name": "username", "datatype": "TEXT", "constraint": "NOT NULL"},
            {"name": "created_at", "datatype": "TIMESTAMP"}
        ]
    """
    pool = await CockroachConnectionPool.get_connection_pool()
    if not pool:
        raise Exception("Not connected to database")
    try:
        col_defs = []
        for col in columns:
            name = col.get("name")
            datatype = col.get("datatype")
            constraint = col.get("constraint")
            if not name or not datatype:
                return {"success": False, "error": "Each column must have 'name' and 'datatype'"}
            col_def = f'"{name}" {datatype}'
            if constraint:
                col_def += f' {constraint}'
            col_defs.append(col_def)
        col_defs_str = ", ".join(col_defs)
        sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({col_defs_str})'
        async with pool.acquire() as conn:
            await conn.execute(sql)
        return {"success": True, "message": f"Table '{table_name}' created with columns: {col_defs_str}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool()
async def bulk_import(ctx: Context, table_name: str, file_url: str, format: str, 
                    delimiter: str = ",", skip_header: bool = True) -> Dict[str, Any]:
    """Bulk import data into a table from a file (CSV or Avro) stored in cloud or web storage. Supports S3, Azure Blob, Google Storage, HTTP/HTTPS URLs.
    
    Args:
        table_name (str): Name of the table to import data into.
        file_url (str): URL to the data file (s3://, azure://, gs://, http://, https://, etc.).
        format (str): File format ('csv' or 'avro').
        delimiter (str): CSV delimiter (default: ',').
        skip_header (bool): Whether to skip the first row as header (default: True).
    
    Returns:
        A success message or an error message.
    
    Example:
        bulk_import(ctx, table_name="users", file_url="s3://bucket/data.csv", format="csv", delimiter=";", skip_header=True)
    """
    pool = await CockroachConnectionPool.get_connection_pool()
    if not pool:
        raise Exception("Not connected to database")

    parsed = urllib.parse.urlparse(file_url)
    if parsed.scheme not in ['s3', 'azure-blob', 'azure', 'gs', 'http', 'https']:
        raise ValueError(f"Unsupported scheme: {parsed.scheme}")
    
    try:            
        async with pool.acquire() as conn:
            if format == "csv":
                import_query = f"""
                IMPORT INTO {table_name} 
                CSV DATA ('{file_url}') 
                WITH delimiter = '{delimiter}', skip = '{1 if skip_header else 0}'
                """
            elif format == "avro":
                import_query = f"""
                IMPORT INTO {table_name} 
                AVRO DATA ('{file_url}') 
                """
            else:
                return {"success": False, "error": "Unsupported format"}
            
            result = await conn.execute(import_query)
            return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool()
async def drop_table(ctx: Context, table_name: str) -> Dict[str, Any]:
    """Facilitate the deletion of existing tables from the database. This tool is useful for cleaning up test environments or managing schema changes, always with the necessary confirmations for security.
    
    Args:
        table_name (str): Name of the table to drop.
    
    Returns:
        A success message or an error message.
    """
    pool = await CockroachConnectionPool.get_connection_pool()
    if not pool:
        raise Exception("Not connected to database")
    try:
        async with pool.acquire() as conn:
            await conn.execute(f'DROP TABLE "{table_name}" CASCADE')
        return {"success": True, "message": f"Table '{table_name}' dropped."}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool()
async def create_index(ctx: Context, table_name: str, index_name: str, columns: List[str]) -> Dict[str, Any]:
    """Create a new index on a specified table to improve query performance. This tool allows users to define indexes on one or more columns, enabling faster data retrieval and optimized execution plans for read-heavy workloads.
    
    Args:
        table_name (str): Name of the table.
        index_name (str): Name of the index.
        columns (List[str]): List of column names to include in the index.
    
    Returns:
        A success message or an error message.
    """
    pool = await CockroachConnectionPool.get_connection_pool()
    if not pool:
        raise Exception("Not connected to database")
    try:
        cols = ', '.join([f'"{col}"' for col in columns])
        async with pool.acquire() as conn:
            await conn.execute(f'CREATE INDEX "{index_name}" ON "{table_name}" ({cols})')
        return {"success": True, "message": f"Index '{index_name}' created on table '{table_name}'."}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool()
async def drop_index(ctx: Context, index_name: str) -> Dict[str, Any]:
    """Drop an existing index.
    
    Args:
        index_name (str): Name of the index to drop.
    
    Returns:
        A success message or an error message.
    """
    pool = await CockroachConnectionPool.get_connection_pool()
    if not pool:
        raise Exception("Not connected to database")
    try:
        async with pool.acquire() as conn:
            await conn.execute(f'DROP INDEX "{index_name}"')
        return {"success": True, "message": f"Index '{index_name}' dropped."}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool()
async def create_view(ctx: Context, view_name: str, query: str) -> Dict[str, Any]:
    """Create a view from a specific query.
    
    Args:
        view_name (str): Name of the view.
        query (str): SQL query for the view definition.
    
    Returns:
        A success message or an error message.
    """
    pool = await CockroachConnectionPool.get_connection_pool()
    if not pool:
        raise Exception("Not connected to database")
    try:
        async with pool.acquire() as conn:
            await conn.execute(f'CREATE VIEW IF NOT EXISTS "{view_name}" AS {query}')
        return {"success": True, "message": f"View '{view_name}' created."}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool()
async def drop_view(ctx: Context, view_name: str) -> Dict[str, Any]:
    """Drop an existing view.
    
    Args:
        view_name (str): Name of the view to drop.
    
    Returns:
        A success message or an error message.
    """
    pool = await CockroachConnectionPool.get_connection_pool()
    if not pool:
        raise Exception("Not connected to database")
    try:
        async with pool.acquire() as conn:
            await conn.execute(f'DROP VIEW "{view_name}" CASCADE')
        return {"success": True, "message": f"View '{view_name}' dropped."}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool()
async def list_tables(ctx: Context, db_schema: str = "public") -> Dict[str, Any]:
    """List all tables present in the connected Cockroach database instance. This is invaluable for AI to understand the database’s landscape and identify relevant data sources for a given query. 

    Args:
        db_schema (str): Schema name (default: "public").
    
    Returns:
        The list of all tables present in the connected Cockroach database.
    """
    pool = await CockroachConnectionPool.get_connection_pool()
    if not pool:
        raise Exception("Not connected to database")
    
    query = """
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
    """
    
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, db_schema)
    
    return {
        "tables": [dict(row) for row in rows],
        "schema": db_schema,
        "count": len(rows)
    }

@mcp.tool()
async def describe_table(ctx: Context, table_name: str, db_schema: str = "public") -> Dict[str, Any]:
    """Provide detailed schema information, column definitions, data types, and other metadata for a specified table. This allows the AI to accurately interpret table structures and formulate precise queries or data manipulation commands. 

    Args:
        table_name (str): Name of the table.
        db_schema (str): Schema name (default: "public").
    
    Returns:
        Table details including columns, constraints, indexes, and metadata.
    """
    pool = await CockroachConnectionPool.get_connection_pool()
    database = CockroachConnectionPool.current_database
    if not pool:
        raise Exception("Not connected to database")
    
    async with pool.acquire() as conn:
        # Get columns
        columns = await conn.fetch("""
        SELECT 
            column_name,
            data_type,
            is_nullable,
            column_default,
            character_maximum_length,
            numeric_precision,
            numeric_scale,
            is_identity,
            generation_expression,
            ordinal_position
        FROM information_schema.columns
        WHERE table_name = $1 AND table_schema = $2
        ORDER BY ordinal_position
        """, table_name, db_schema)
        
        # Get constraints
        constraints = await conn.fetch("""
        SELECT 
            tc.constraint_name,
            tc.constraint_type,
            kcu.column_name,
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
        """, table_name, db_schema)
        
        # Get indexes
        idx_query = "SELECT index_name, non_unique, column_name, direction, storing, implicit FROM [SHOW INDEXES FROM " + table_name +"] ORDER BY index_name, seq_in_index"
        indexes = await conn.fetch(idx_query)
        
        # Get table metadata
        md_query = "SELECT range_id, schema_name, table_name, range_size_mb, lease_holder, lease_holder_locality, replicas, replica_localities, range_size, span_stats from [SHOW RANGES FROM DATABASE " + database + " WITH TABLES, KEYS, details] WHERE table_name = '" + table_name +"'"
        metadata = await conn.fetchrow(md_query)
    
    return {
        "database": database,
        "schema": db_schema,
        "table": table_name,
        "columns": [dict(row) for row in columns],
        "constraints": [dict(row) for row in constraints],
        "indexes": [dict(row) for row in indexes],
        "metadata": dict(metadata) if metadata else None
    }

@mcp.tool()   
async def list_views(ctx: Context, db_schema: str = "public") -> Dict[str, Any]:
    """List all views in a schema.
    
    Args:
        db_schema (str): Schema name (default: "public").
    
    Returns:
        All views in a schema
    """
    pool = await CockroachConnectionPool.get_connection_pool()
    if not pool:
        raise Exception("Not connected to database")
    
    query = """
    SELECT 
        table_name as view_name,
        view_definition
    FROM information_schema.views
    WHERE table_schema = $1
    ORDER BY table_name
    """
    
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, db_schema)
    
    return {
        "views": [dict(row) for row in rows],
        "schema": db_schema,
        "count": len(rows)
    }

@mcp.tool()    
async def get_table_relationships(ctx: Context, table_name: Optional[str] = None) -> Dict[str, Any]:
    """Get foreign key relationships for a table or all tables.
    
    Args:
        table_name (str, optional): Table name to filter relationships (default: None).
    
    Returns:
        List all relationships for a specific table or in a schema.
    """
    pool = await CockroachConnectionPool.get_connection_pool()
    if not pool:
        raise Exception("Not connected to database")
    
    query = """
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
    
    params = []
    if table_name:
        query += " AND tc.table_name = $1"
        params.append(table_name)
    
    query += " ORDER BY tc.table_name, kcu.ordinal_position"
    
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    
    return {
        "relationships": [dict(row) for row in rows],
        "count": len(rows)
    }

@mcp.tool()    
async def analyze_schema(ctx: Context, db_schema: str = "public") -> Dict[str, Any]:
    """Analyze the schema and provide a summary of tables, views, and relationships.
    
    Args:
        db_schema (str): Schema name (default: "public").
    
    Returns:
        Summary and details of tables, views, and relationships.        
    """
    # Get all schema components
    tables = await list_tables(ctx, db_schema)
    views = await list_views(ctx, db_schema)
    relationships = await get_table_relationships(ctx)
    
    return {
        "schema": db_schema,
        "summary": {
            "table_count": tables["count"],
            "view_count": views["count"],
            "relationship_count": relationships["count"]
        },
        "tables": tables["tables"],
        "views": views["views"],
        "relationships": relationships["relationships"],
        "generated_at": datetime.now().isoformat()
    }