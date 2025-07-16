import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import src.tools.cluster_monitoring as cm

@pytest.mark.asyncio
@patch("src.tools.cluster_management.CockroachConnectionPool.get_connection_pool", new_callable=AsyncMock)
@patch("src.tools.cluster_management.format_cluster_status")
async def test_get_cluster_status_success(mock_format, mock_pool):
    mock_conn = AsyncMock()
    mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
    mock_conn.fetch.side_effect = [
        [{"version": "23.1"}],  # cluster_info
        [{"capacity": 100, "available": 80}],  # cluster_info addition
        [{"node_id": 1, "address": "addr", "is_live": True}]  # nodes
    ]
    mock_format.return_value = {"formatted": True}
    ctx = MagicMock()
    result = await cm.get_cluster_status(ctx, detailed=False)
    assert result["success"]
    assert "cluster_status" in result

@pytest.mark.asyncio
@patch("src.tools.cluster_management.CockroachConnectionPool.get_connection_pool", new_callable=AsyncMock)
async def test_get_cluster_status_no_pool(mock_pool):
    mock_pool.return_value = None
    ctx = MagicMock()
    with pytest.raises(Exception, match="Not connected to database"):
        await cm.get_cluster_status(ctx)

@pytest.mark.asyncio
@patch("src.tools.cluster_management.CockroachConnectionPool.get_connection_pool", new_callable=AsyncMock)
async def test_get_cluster_status_exception(mock_pool):
    mock_conn = AsyncMock()
    mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
    mock_conn.fetch.side_effect = Exception("DB error")
    ctx = MagicMock()
    result = await cm.get_cluster_status(ctx)
    assert not result["success"]
    assert "error" in result

@pytest.mark.asyncio
@patch("src.tools.cluster_management.CockroachConnectionPool.get_connection_pool", new_callable=AsyncMock)
async def test_show_running_queries_success(mock_pool):
    mock_conn = AsyncMock()
    mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
    mock_conn.fetch.return_value = [{"node_id": 1, "user_name": "root"}]
    ctx = MagicMock()
    result = await cm.show_running_queries(ctx, node_id=1, user="root", min_duration="1:0")
    assert result["success"]
    assert "queries" in result

@pytest.mark.asyncio
@patch("src.tools.cluster_management.CockroachConnectionPool.get_connection_pool", new_callable=AsyncMock)
async def test_show_running_queries_no_pool(mock_pool):
    mock_pool.return_value = None
    ctx = MagicMock()
    with pytest.raises(Exception, match="Not connected to database"):
        await cm.show_running_queries(ctx)

@pytest.mark.asyncio
@patch("src.tools.cluster_management.CockroachConnectionPool.get_connection_pool", new_callable=AsyncMock)
async def test_show_running_queries_exception(mock_pool):
    mock_conn = AsyncMock()
    mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
    mock_conn.fetch.side_effect = Exception("DB error")
    ctx = MagicMock()
    result = await cm.show_running_queries(ctx)
    assert not result["success"]
    assert "error" in result

@pytest.mark.asyncio
@patch("src.tools.cluster_management.CockroachConnectionPool.get_connection_pool", new_callable=AsyncMock)
async def test_analyze_performance_success(mock_pool):
    mock_conn = AsyncMock()
    mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
    mock_conn.fetch.return_value = [{"query": "SELECT 1"}]
    ctx = MagicMock()
    result = await cm.analyze_performance(ctx, query="SELECT", time_range="1:0")
    assert result["success"]
    assert "performance_data" in result

@pytest.mark.asyncio
@patch("src.tools.cluster_management.CockroachConnectionPool.get_connection_pool", new_callable=AsyncMock)
async def test_analyze_performance_no_pool(mock_pool):
    mock_pool.return_value = None
    ctx = MagicMock()
    with pytest.raises(Exception, match="Not connected to database"):
        await cm.analyze_performance(ctx, query="SELECT")

@pytest.mark.asyncio
@patch("src.tools.cluster_management.CockroachConnectionPool.get_connection_pool", new_callable=AsyncMock)
async def test_analyze_performance_exception(mock_pool):
    mock_conn = AsyncMock()
    mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
    mock_conn.fetch.side_effect = Exception("DB error")
    ctx = MagicMock()
    result = await cm.analyze_performance(ctx, query="SELECT")
    assert not result["success"]
    assert "error" in result

@pytest.mark.asyncio
@patch("src.tools.cluster_management.CockroachConnectionPool.get_connection_pool", new_callable=AsyncMock)
async def test_get_replication_status_table(mock_pool):
    mock_conn = AsyncMock()
    mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
    mock_conn.fetch.return_value = [{"range_id": 1}]
    ctx = MagicMock()
    result = await cm.get_replication_status(ctx, table_name="mytable")
    assert result["success"]
    assert "replication_status" in result

@pytest.mark.asyncio
@patch("src.tools.cluster_management.CockroachConnectionPool.get_connection_pool", new_callable=AsyncMock)
async def test_get_replication_status_db(mock_pool):
    mock_conn = AsyncMock()
    mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
    mock_conn.fetch.return_value = [{"range_id": 1}]
    ctx = MagicMock()
    ctx.request_context.lifespan_context.database = "defaultdb"
    result = await cm.get_replication_status(ctx, table_name="")
    assert result["success"]
    assert "replication_status" in result

@pytest.mark.asyncio
@patch("src.tools.cluster_management.CockroachConnectionPool.get_connection_pool", new_callable=AsyncMock)
async def test_get_replication_status_no_pool(mock_pool):
    mock_pool.return_value = None
    ctx = MagicMock()
    with pytest.raises(Exception, match="Not connected to database"):
        await cm.get_replication_status(ctx, table_name="mytable")

@pytest.mark.asyncio
@patch("src.tools.cluster_management.CockroachConnectionPool.get_connection_pool", new_callable=AsyncMock)
async def test_get_replication_status_exception(mock_pool):
    mock_conn = AsyncMock()
    mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
    mock_conn.fetch.side_effect = Exception("DB error")
    ctx = MagicMock()
    result = await cm.get_replication_status(ctx, table_name="mytable")
    assert not result["success"]
    assert "error" in result

def test_format_cluster_status():
    cluster_info = [MagicMock()]
    nodes = [MagicMock()]
    nodes[0].__getitem__.side_effect = lambda k: True if k == 'is_live' else None
    result = cm.format_cluster_status(cluster_info, nodes)
    assert "cluster_settings" in result
    assert "nodes" in result
    assert "node_count" in result
    assert "healthy_nodes" in result
    assert "timestamp" in result
    assert "summary" in result