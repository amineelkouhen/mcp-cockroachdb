from mcp.server.fastmcp import Context
from typing import Dict, Any, List
from src.common.server import mcp
from datetime import datetime, date
from decimal import Decimal
from uuid import UUID
from src.common.connection import CockroachConnectionPool


def serialize_value(value: Any) -> Any:
    """Convert non-JSON-serializable types to serializable ones."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    elif isinstance(value, Decimal):
        return float(value)
    elif isinstance(value, UUID):
        return str(value)
    elif isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    elif isinstance(value, dict):
        return {k: serialize_value(v) for k, v in value.items()}
    elif isinstance(value, (list, tuple)):
        return [serialize_value(v) for v in value]
    return value


def serialize_row(row: Dict) -> Dict:
    """Serialize all values in a row dictionary."""
    return {k: serialize_value(v) for k, v in row.items()}

@mcp.tool()   
async def get_cluster_status(ctx: Context, detailed: bool = False) -> Dict[str, Any]:
    '''Get cluster health and node distribution.
    
    Args:
        detailed (bool): If True, returns all node details. If False, returns summary info.
    
    Returns:
        Details about the cluster's status and how nodes/ranges are distributed or an error message.
    '''
    pool = await CockroachConnectionPool.get_connection_pool()
    if not pool:
        raise Exception("Not connected to database")
    try:
        async with pool.acquire() as conn:
            # Get cluster info
            cluster_info = await conn.fetch("SHOW CLUSTER SETTING version")
            cluster_info += await conn.fetch("""
                                             SELECT 
                                                sum(capacity) as cluster_capacity, 
                                                sum(available) as available_capacity, 
                                                sum(used) as used_capacity, 
                                                sum(range_count) as total_ranges 
                                             FROM crdb_internal.kv_store_status
                                            """)
            # Get node status
            if detailed:
                nodes = await conn.fetch("""
                                        SELECT g.*, capacity, s.available, s.used, s.logical_bytes, s.range_count FROM crdb_internal.gossip_nodes g
                                        LEFT JOIN crdb_internal.kv_store_status s
                                        ON g.node_id = s.node_id      
                                        """)
            else:
                nodes = await conn.fetch("SELECT node_id, address, is_live FROM crdb_internal.gossip_nodes")
        
            # Format cluster status
            formatted_status = format_cluster_status(cluster_info, nodes)
            return {
                "success": True,
                "cluster_status": formatted_status
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()   
async def show_running_queries(ctx: Context, node_id: int = 1, user: str = 'root', min_duration: str = '1:0') -> Dict[str, Any]:
    '''Show currently running queries on the cluster.
    
    Args:
        node_id (int): Node ID to filter (default: 1).
        user (str): Username to filter (default: 'root').
        min_duration (str): Minimum query duration (default: '1:0', format: 'minutes:seconds').
    
    Returns:
        The queries running on the cluster.
    '''
    pool = await CockroachConnectionPool.get_connection_pool()
    if not pool:
        raise Exception("Not connected to database")

    try:
        query = "SELECT * FROM crdb_internal.cluster_queries"
        conditions = []
        
        if node_id:
            conditions.append(f"node_id = {node_id}")
        if user:
            conditions.append(f"user_name = '{user}'")
        if min_duration:
            conditions.append(f"(now() - start) > INTERVAL '{min_duration}'")
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(query)
            return {
                "success": True,
                "queries": [dict(row) for row in rows]
            }
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool()   
async def get_replication_status(ctx: Context, table_name: str) -> Dict[str, Any]:
    '''Get replication and distribution status for a table or the whole database.
    
    Args:
        table_name (str): Table name to filter (default: "", for all tables).
    
    Returns:
        Details about range replication for a specific table or the current database.
    '''
    pool = await CockroachConnectionPool.get_connection_pool()
    if not pool:
        raise Exception("Not connected to database")

    try:
        async with pool.acquire() as conn:
            if table_name:
                # Specific table replication
                query = f"""
                SELECT 
                    r.range_id,
                    r.replicas,
                    r.voting_replicas,
                    r.replica_localities,
                    r.lease_holder,
                    r.range_size
                FROM [SHOW RANGES FROM table {table_name}] t
                left join  crdb_internal.ranges r
                on r.range_id = t.range_id
                """
            else:
                # General replication status
                query = """
                SELECT 
                    r.range_id,
                    r.replicas,
                    r.voting_replicas,
                    r.replica_localities,
                    r.lease_holder,
                    r.range_size
                FROM [SHOW RANGES FROM DATABASE """ + CockroachConnectionPool.current_database + """] d
                left join  crdb_internal.ranges r
                on r.range_id = d.range_id
                """
            
            rows = await conn.fetch(query)
            return {
                "success": True,
                "replication_status": [dict(row) for row in rows]
            }
    except Exception as e:
        return {"success": False, "error": str(e)}
    
def format_cluster_status(cluster_info: List[Any], nodes: List[Any]) -> Dict[str, Any]:
    formatted_cluster = {
        "cluster_settings": [dict(row) for row in cluster_info],
        "nodes": [dict(row) for row in nodes],
        "node_count": len(nodes),
        "healthy_nodes": len([n for n in nodes if dict(n).get('is_live', False)]),
        "timestamp": datetime.now().isoformat()
    }
    
    # Add summary statistics
    if nodes:
        node_data = [dict(row) for row in nodes]
        formatted_cluster["summary"] = {
            "total_nodes": len(node_data),
            "available_nodes": len([n for n in node_data if n.get('is_live', False)]),
            "node_addresses": [n.get('address', 'unknown') for n in node_data]
        }
    
    return formatted_cluster


@mcp.tool()
async def get_query_insights(ctx: Context, query_filter: str = "", min_execution_time_ms: int = 100, limit: int = 50) -> Dict[str, Any]:
    '''Get query execution insights including slow queries, failed queries, and queries with issues.
    
    Args:
        query_filter (str): Keyword to filter queries (case-insensitive, matches query text).
        min_execution_time_ms (int): Minimum execution time in milliseconds to filter (default: 100ms).
        limit (int): Maximum number of insights to return (default: 50).
    
    Returns:
        Query execution insights with details about slow/problematic queries.
    '''
    pool = await CockroachConnectionPool.get_connection_pool()
    if not pool:
        raise Exception("Not connected to database")

    try:
        # Build WHERE conditions
        conditions = [f"(EXTRACT(EPOCH FROM (end_time - start_time)) * 1000) >= {min_execution_time_ms}"]
        if query_filter:
            # Escape single quotes in the filter
            safe_filter = query_filter.replace("'", "''")
            conditions.append(f"LOWER(query) LIKE LOWER('%{safe_filter}%')")
        
        where_clause = " AND ".join(conditions)
        
        query = f"""
        SELECT 
            session_id,
            txn_id,
            stmt_id,
            problem,
            causes,
            query,
            status,
            start_time,
            end_time,
            full_scan,
            user_name,
            app_name,
            database_name,
            rows_read,
            rows_written,
            retries,
            contention,
            cpu_sql_nanos,
            index_recommendations
        FROM crdb_internal.cluster_execution_insights
        WHERE {where_clause}
        ORDER BY end_time DESC
        LIMIT {limit}
        """
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(query)
            
            insights = [serialize_row(dict(row)) for row in rows]
            
            # Calculate summary
            total = len(insights)
            full_scans = len([i for i in insights if i.get('full_scan')])
            with_contention = len([i for i in insights if i.get('contention') and i['contention'] != '00:00:00'])
            with_retries = len([i for i in insights if i.get('retries', 0) > 0])
            
            return {
                "success": True,
                "insights": insights,
                "summary": {
                    "total_insights": total,
                    "full_scan_queries": full_scans,
                    "queries_with_contention": with_contention,
                    "queries_with_retries": with_retries
                }
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def get_slow_queries(ctx: Context, query_filter: str = "", min_duration_seconds: float = 1.0, limit: int = 50) -> Dict[str, Any]:
    '''Get slow queries from statement statistics, ordered by execution time.
    
    Args:
        query_filter (str): Keyword to filter queries (case-insensitive, matches query text).
        min_duration_seconds (float): Minimum query duration in seconds (default: 1.0).
        limit (int): Maximum number of queries to return (default: 50).
    
    Returns:
        List of slow queries with execution statistics.
    '''
    pool = await CockroachConnectionPool.get_connection_pool()
    if not pool:
        raise Exception("Not connected to database")

    try:
        # Build WHERE conditions
        conditions = [f"cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'max') as FLOAT) >= {min_duration_seconds}"]
        if query_filter:
            safe_filter = query_filter.replace("'", "''")
            conditions.append(f"LOWER(json_extract_path_text(metadata, 'query')) LIKE LOWER('%{safe_filter}%')")
        
        where_clause = " AND ".join(conditions)
        
        query = f"""
        SELECT 
            aggregated_ts,
            fingerprint_id,
            json_extract_path_text(metadata, 'query') as query,
            json_extract_path_text(metadata, 'db') as database_name,
            json_extract_path_text(metadata, 'user') as user_name,
            cast(json_extract_path_text(metadata, 'fullScan') as BOOL) as full_scan,
            cast(json_extract_path_text(statistics, 'statistics', 'cnt') as INT) as execution_count,
            cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'max') as FLOAT) as max_latency_seconds,
            cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'min') as FLOAT) as min_latency_seconds,
            cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'p50') as FLOAT) as p50_latency_seconds,
            cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'p90') as FLOAT) as p90_latency_seconds,
            cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'p99') as FLOAT) as p99_latency_seconds,
            cast(json_extract_path_text(statistics, 'statistics', 'rowsRead', 'mean') as FLOAT) as avg_rows_read,
            cast(json_extract_path_text(statistics, 'statistics', 'rowsWritten', 'mean') as FLOAT) as avg_rows_written,
            cast(json_extract_path_text(statistics, 'statistics', 'contentionTime', 'mean') as FLOAT) as avg_contention_seconds
        FROM crdb_internal.statement_statistics
        WHERE {where_clause}
        ORDER BY cast(json_extract_path_text(statistics, 'statistics', 'latencyInfo', 'max') as FLOAT) DESC
        LIMIT {limit}
        """
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(query)
            return {
                "success": True,
                "slow_queries": [serialize_row(dict(row)) for row in rows],
                "count": len(rows),
                "threshold_seconds": min_duration_seconds
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def get_contention_events(ctx: Context, table_filter: str = "", limit: int = 50) -> Dict[str, Any]:
    '''Get recent contention events showing transaction conflicts and lock waits.
    
    Args:
        table_filter (str): Filter by table name (case-insensitive, partial match).
        limit (int): Maximum number of events to return (default: 50).
    
    Returns:
        List of contention events with blocking/waiting transaction details.
    '''
    pool = await CockroachConnectionPool.get_connection_pool()
    if not pool:
        raise Exception("Not connected to database")

    try:
        # Build WHERE clause
        where_clause = ""
        if table_filter:
            safe_filter = table_filter.replace("'", "''")
            where_clause = f"WHERE LOWER(table_name) LIKE LOWER('%{safe_filter}%')"
        
        query = f"""
        SELECT 
            collection_ts,
            blocking_txn_id,
            blocking_txn_fingerprint_id,
            waiting_txn_id,
            waiting_txn_fingerprint_id,
            contention_duration,
            contending_pretty_key,
            waiting_stmt_id,
            database_name,
            schema_name,
            table_name,
            index_name,
            contention_type
        FROM crdb_internal.transaction_contention_events
        {where_clause}
        ORDER BY collection_ts DESC
        LIMIT {limit}
        """
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(query)
            
            events = [serialize_row(dict(row)) for row in rows]
            
            # Group by table for summary
            tables_affected = {}
            for event in events:
                table = event.get('table_name', 'unknown')
                if table not in tables_affected:
                    tables_affected[table] = 0
                tables_affected[table] += 1
            
            return {
                "success": True,
                "contention_events": events,
                "count": len(events),
                "tables_affected": tables_affected
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def get_transaction_insights(ctx: Context, query_filter: str = "", limit: int = 50) -> Dict[str, Any]:
    '''Get transaction execution insights including slow transactions and retries.
    
    Args:
        query_filter (str): Keyword to filter by query text (case-insensitive, partial match).
        limit (int): Maximum number of insights to return (default: 50).
    
    Returns:
        Transaction execution insights with details about problematic transactions.
    '''
    pool = await CockroachConnectionPool.get_connection_pool()
    if not pool:
        raise Exception("Not connected to database")

    try:
        # Build WHERE clause
        where_clause = ""
        if query_filter:
            safe_filter = query_filter.replace("'", "''")
            where_clause = f"WHERE LOWER(query) LIKE LOWER('%{safe_filter}%')"
        
        query = f"""
        SELECT 
            txn_id,
            txn_fingerprint_id,
            query,
            status,
            start_time,
            end_time,
            user_name,
            app_name,
            rows_read,
            rows_written,
            retries,
            contention,
            problems,
            causes,
            cpu_sql_nanos,
            last_retry_reason,
            stmt_execution_ids
        FROM crdb_internal.cluster_txn_execution_insights
        {where_clause}
        ORDER BY end_time DESC
        LIMIT {limit}
        """
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(query)
            
            insights = [serialize_row(dict(row)) for row in rows]
            
            # Summary stats
            total = len(insights)
            with_retries = len([i for i in insights if i.get('retries', 0) > 0])
            with_contention = len([i for i in insights if i.get('contention') and i['contention'] != '00:00:00'])
            
            return {
                "success": True,
                "transaction_insights": insights,
                "summary": {
                    "total_transactions": total,
                    "transactions_with_retries": with_retries,
                    "transactions_with_contention": with_contention
                }
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def get_index_recommendations(ctx: Context) -> Dict[str, Any]:
    '''Get index recommendations based on query workload analysis.
    
    Returns:
        List of recommended indexes that could improve query performance.
    '''
    pool = await CockroachConnectionPool.get_connection_pool()
    if not pool:
        raise Exception("Not connected to database")

    try:
        # Get index recommendations from insights
        query = """
        SELECT DISTINCT
            index_recommendations,
            query,
            database_name
        FROM crdb_internal.cluster_execution_insights
        WHERE index_recommendations IS NOT NULL 
          AND array_length(index_recommendations, 1) > 0
        ORDER BY database_name
        """
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(query)
            
            recommendations = []
            for row in rows:
                row_dict = dict(row)
                recs = row_dict.get('index_recommendations', [])
                if recs:
                    recommendations.append({
                        "database": row_dict.get('database_name'),
                        "query": row_dict.get('query'),
                        "recommendations": recs
                    })
            
            return {
                "success": True,
                "index_recommendations": recommendations,
                "total_recommendations": len(recommendations)
            }
    except Exception as e:
        return {"success": False, "error": str(e)}