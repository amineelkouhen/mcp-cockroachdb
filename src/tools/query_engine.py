import time
from src.common.connection import CockroachConnectionPool
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from mcp.server.fastmcp import Context
from src.common.server import mcp

@mcp.tool()
async def execute_query(ctx: Context, query: str, params: Optional[List] = None, 
                        format: str = "json", limit: Optional[int] = None) -> Dict[str, Any]:
    '''Execute a SQL query with optional parameters and formatting.
    
    Args:
        query (str): SQL query to execute.
        params (List, optional): Query parameters.
        format (str): Output format ('json', 'csv', 'table').
        limit (int, optional): Limit number of rows returned.
    
    Returns:
        The query resultset in json or csv format.
    '''
    
    pool = await CockroachConnectionPool.get_connection_pool()
    query_history = CockroachConnectionPool.query_history
    if not pool:
        raise Exception("Not connected to database")

    if not query:
        raise Exception("Query is Empty")

    start_time = time.time()
    
    try:
        # Add limit if specified
        if limit:
            query = f"{query} LIMIT {limit}"
        
        async with pool.acquire() as conn:
            if params:
                rows = await conn.fetch(query, *params)
            else:
                rows = await conn.fetch(query)
        
        duration = time.time() - start_time
        
        # Add to query history
        query_history.append({
            "query": query,
            "timestamp": datetime.now().isoformat(),
            "duration": duration,
            "row_count": len(rows),
            "success": True
        })
        
        # Format results
        formatted_result = format_result([dict(row) for row in rows], format)
        
        return {
            "success": True,
            "rows": [dict(row) for row in rows],
            "row_count": len(rows),
            "duration": duration,
            "columns": list(dict(rows[0]).keys()) if rows else [],
            "formatted_result": formatted_result
        }
        
    except Exception as e:
        duration = time.time() - start_time
        
        # Add to query history
        query_history.append({
            "query": query,
            "timestamp": datetime.now().isoformat(),
            "duration": duration,
            "row_count": 0,
            "success": False,
            "error": str(e)
        })
        
        return {
            "success": False,
            "error": str(e),
            "duration": duration
        }

@mcp.tool()
async def execute_transaction(ctx: Context, queries: List[str]) -> Dict[str, Any]:
    '''Execute a list of SQL queries as a single transaction.
    
    Args:
        queries (List[str]): List of SQL queries to execute.
    
    Returns:
        A success message or an error message.
    '''
    
    pool = await CockroachConnectionPool.get_connection_pool()
    if not pool:
        raise Exception("Not connected to database")
    
    results = []
    
    async with pool.acquire() as conn:
        async with conn.transaction():
            try:
                for query in queries:
                    rows = await conn.fetch(query)
                    results.append({
                        "query": query,
                        "row_count": len(rows),
                        "rows": [dict(row) for row in rows]
                    })
                
                return {
                    "success": True,
                    "results": results,
                    "message": f"Transaction completed successfully with {len(queries)} statements"
                }
                
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "completed_statements": len(results),
                    "total_statements": len(queries)
                }

@mcp.tool()  
async def explain_query(ctx: Context, query: str, analyze: bool = False) -> Dict[str, Any]:
    '''Return CockroachDB's statement plan for a preparable statement. You can use this information to optimize the query. If you run it with Analyze, it executes the SQL query and generates a statement plan with execution statistics.
    
    Args:
        query (str): SQL query to explain.
        analyze (bool): If True, run EXPLAIN ANALYZE.
    
    Returns:
        A success message or an error message.
    '''
    
    pool = await CockroachConnectionPool.get_connection_pool()
    if not pool:
        raise Exception("Not connected to database")
    
    explain_query = f"EXPLAIN {'ANALYZE' if analyze else ''} {query}"
    
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(explain_query)
        
        plan_text = "\n".join([row.get('info', row.get('plan', '')) for row in rows])
        if analyze:
             # Add to query history
            query_history = CockroachConnectionPool.query_history
            query_history.append({
                "query": explain_query,
                "timestamp": datetime.now().isoformat(),
                "row_count": len(rows),
                "success": True
            })
        
        return {
            "success": True,
            "plan": [dict(row) for row in rows],
            "plan_text": plan_text,
            "analyzed": analyze
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()   
async def analyze_performance(ctx: Context, query: str, time_range: str = "1:0") -> Dict[str, Any]:
    '''Analyze query performance statistics for a given query or time range.
    
    Args:
        query (str): Query string to filter (default: "").
        time_range (str): Time range for analysis (default: '1:0', format: 'minutes:seconds').
    
    Returns:
        Statistics about performance and latency (e.g., P50, P99).
    '''
    pool = await CockroachConnectionPool.get_connection_pool()
    if not pool:
        raise Exception("Not connected to database")

    try:
        async with pool.acquire() as conn:
            if query:
                # Analyze specific query
                perf_query = f"""
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
                FROM
                (SELECT 
                    aggregated_ts,
                    json_extract_path_text(metadata, 'query') as query, 
                    cast(json_extract_path_text(metadata, 'fullScan') as BOOL) as full_scan, 
                    cast(json_extract_path_text(statistics, 'statistics', 'cnt') as INT) as execution_count,
                    cast(json_extract_path_text(statistics, 'statistics', 'usedFollowerRead') as BOOL) as follower_read,
                    cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'max') as FLOAT) as max_latency,
                    cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'min') as FLOAT) as min_latency,
                    cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'p50') as FLOAT) as p50_latency,
                    cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'p90') as FLOAT) as p90_latency,                       
                    cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'p99') as FLOAT) as p99_latency,
                    cast(json_extract_path_text(statistics, 'statistics', 'rowsRead', 'mean') as FLOAT) as avg_rows_read,
                    cast(json_extract_path_text(statistics, 'statistics', 'rowsWritten', 'mean') as FLOAT) as avg_rows_written
                FROM crdb_internal.statement_statistics)
                WHERE LOWER(query) LIKE LOWER('%{query}%')
                AND aggregated_ts >= now() - INTERVAL '{time_range}'
                """
            else:
                # General performance stats
                perf_query = f"""
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
                FROM
                (SELECT 
                    aggregated_ts,
                    json_extract_path_text(metadata, 'query') as query, 
                    cast(json_extract_path_text(metadata, 'fullScan') as BOOL) as full_scan, 
                    cast(json_extract_path_text(statistics, 'statistics', 'cnt') as INT) as execution_count,
                    cast(json_extract_path_text(statistics, 'statistics', 'usedFollowerRead') as BOOL) as follower_read,
                    cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'max') as FLOAT) as max_latency,
                    cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'min') as FLOAT) as min_latency,
                    cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'p50') as FLOAT) as p50_latency,
                    cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'p90') as FLOAT) as p90_latency,                       
                    cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'p99') as FLOAT) as p99_latency,
                    cast(json_extract_path_text(statistics, 'statistics', 'rowsRead', 'mean') as FLOAT) as avg_rows_read,
                    cast(json_extract_path_text(statistics, 'statistics', 'rowsWritten', 'mean') as FLOAT) as avg_rows_written
                FROM crdb_internal.statement_statistics)
                WHERE aggregated_ts >= now() - INTERVAL '{time_range}'
                ORDER BY max_latency DESC
                LIMIT 20
                """
            
            rows = await conn.fetch(perf_query)
            return {
                "success": True,
                "performance_data": [dict(row) for row in rows]
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()     
async def get_query_history(ctx : Context, limit: int = 10) -> Dict[str, Any]:
    '''Get the history of executed queries.
    
    Args:
        limit (int): Number of recent queries to return (default: 10).
    
    Returns:
        A list of the last executed queries.
    '''
    
    query_history = CockroachConnectionPool.query_history
    return {
        "history": sorted(
            query_history[-limit:],
            key=lambda x: x["timestamp"],
            reverse=True
        ),
        "total_queries": len(query_history)
    }

def format_result(rows: List[Dict], format: str) -> Union[str, List[Dict]]:
    if format == "csv":
        if not rows:
            return ""
        
        headers = list(rows[0].keys())
        csv_lines = [",".join(headers)]
        
        for row in rows:
            # Convert values to strings and handle None/null values
            values = []
            for header in headers:
                value = row.get(header, "")
                if value is None:
                    values.append("")
                else:
                    # Escape commas and quotes in CSV format
                    str_value = str(value)
                    if "," in str_value or '"' in str_value or "\n" in str_value:
                        # Escape quotes by doubling them and wrap in quotes
                        str_value = '"' + str_value.replace('"', '""') + '"'
                    values.append(str_value)
            
            csv_lines.append(",".join(values))
        
        return "\n".join(csv_lines)
    
    elif format == "json":
        import json
        return json.dumps(rows, indent=2)
    
    elif format == "table":
        if not rows:
            return ""
        
        headers = list(rows[0].keys())
        
        # Calculate column widths
        col_widths = {}
        for header in headers:
            col_widths[header] = len(header)
        
        for row in rows:
            for header in headers:
                value = str(row.get(header, ""))
                col_widths[header] = max(col_widths[header], len(value))
        
        # Create table
        table_lines = []
        
        # Header row
        header_row = " | ".join(header.ljust(col_widths[header]) for header in headers)
        table_lines.append(header_row)
        
        # Separator row
        separator = " | ".join("-" * col_widths[header] for header in headers)
        table_lines.append(separator)
        
        # Data rows
        for row in rows:
            data_row = " | ".join(str(row.get(header, "")).ljust(col_widths[header]) for header in headers)
            table_lines.append(data_row)
        
        return "\n".join(table_lines)
    
    else:
        # Default: return original data as list of dictionaries
        return rows