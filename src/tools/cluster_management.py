from mcp.server.fastmcp import Context
from typing import Dict, Any, List
from src.common.server import mcp
from datetime import datetime
from src.common.CockroachConnectionPool import CockroachConnectionPool

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
                current_database = ctx.request_context.lifespan_context.database
                query = """
                SELECT 
                    r.range_id,
                    r.replicas,
                    r.voting_replicas,
                    r.replica_localities,
                    r.lease_holder,
                    r.range_size
                FROM [SHOW RANGES FROM DATABASE """ + current_database + """] d
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