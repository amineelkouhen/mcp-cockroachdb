"""Gating + injection-rejection tests for the new tool families.

These tests don't hit a database; they exercise the input-validation and
policy-flag paths in each new tool.
"""

from __future__ import annotations

import pytest

from src.common.config import ServerFlags, set_flags


@pytest.fixture
def read_only():
    set_flags(ServerFlags(read_only=True))
    yield
    set_flags(ServerFlags())


@pytest.fixture
def destructive_off():
    set_flags(ServerFlags(read_only=False, allow_destructive=False))
    yield
    set_flags(ServerFlags())


@pytest.fixture
def destructive_on():
    set_flags(ServerFlags(read_only=False, allow_destructive=True))
    yield
    set_flags(ServerFlags())


# ----- user_management -----


class TestUserManagement:
    @pytest.mark.asyncio
    async def test_create_user_read_only(self, read_only) -> None:
        from src.tools.user_management import create_user

        r = await create_user(None, "alice")
        assert r["success"] is False
        assert "read-only" in r["error"].lower()

    @pytest.mark.asyncio
    async def test_drop_user_requires_destructive(self, destructive_off) -> None:
        from src.tools.user_management import drop_user

        r = await drop_user(None, "alice", confirm=True)
        assert r["success"] is False
        assert "destructive" in r["error"].lower()

    @pytest.mark.asyncio
    async def test_drop_user_requires_confirm(self, destructive_on) -> None:
        from src.tools.user_management import drop_user

        r = await drop_user(None, "alice", confirm=False)
        assert r["success"] is False
        assert "confirm=true" in r["error"].lower()

    @pytest.mark.asyncio
    async def test_grant_privileges_rejects_bad_priv(self, destructive_on) -> None:
        from src.tools.user_management import grant_privileges

        r = await grant_privileges(None, ["EVIL"], "TABLE", "users", "agent")
        assert r["success"] is False
        assert "invalid" in r["error"].lower()

    @pytest.mark.asyncio
    async def test_grant_privileges_rejects_bad_target(self, destructive_on) -> None:
        from src.tools.user_management import grant_privileges

        r = await grant_privileges(None, ["SELECT"], "ROW", "users", "agent")
        assert r["success"] is False
        assert "grant target" in r["error"].lower()

    @pytest.mark.asyncio
    async def test_grant_privileges_rejects_injection_in_user(self, destructive_on) -> None:
        from src.tools.user_management import grant_privileges

        r = await grant_privileges(None, ["SELECT"], "TABLE", "users", 'agent"; DROP USER root; --')
        assert r["success"] is False


# ----- table_management extensions -----


class TestTableExtras:
    @pytest.mark.asyncio
    async def test_truncate_requires_destructive(self, destructive_off) -> None:
        from src.tools.table_management import truncate_table

        r = await truncate_table(None, "users", confirm=True)
        assert r["success"] is False
        assert "destructive" in r["error"].lower()

    @pytest.mark.asyncio
    async def test_truncate_requires_confirm(self, destructive_on) -> None:
        from src.tools.table_management import truncate_table

        r = await truncate_table(None, "users", confirm=False)
        assert r["success"] is False
        assert "confirm=true" in r["error"].lower()

    @pytest.mark.asyncio
    async def test_alter_table_add_column_rejects_bad_datatype(self, destructive_on) -> None:
        from src.tools.table_management import alter_table_add_column

        r = await alter_table_add_column(None, "users", "weird", "EVIL_TYPE")
        assert r["success"] is False
        assert "datatype" in r["error"].lower()

    @pytest.mark.asyncio
    async def test_alter_table_drop_column_requires_confirm(self, destructive_on) -> None:
        from src.tools.table_management import alter_table_drop_column

        r = await alter_table_drop_column(None, "users", "secret", confirm=False)
        assert r["success"] is False
        assert "confirm=true" in r["error"].lower()


# ----- job_management -----


class TestJobManagement:
    @pytest.mark.asyncio
    async def test_list_jobs_validates_status(self) -> None:
        from src.tools.job_management import list_jobs

        r = await list_jobs(None, status="evil")
        assert r["success"] is False

    @pytest.mark.asyncio
    async def test_cancel_job_requires_destructive(self, destructive_off) -> None:
        from src.tools.job_management import cancel_job

        r = await cancel_job(None, 1, confirm=True)
        assert r["success"] is False
        assert "destructive" in r["error"].lower()

    @pytest.mark.asyncio
    async def test_cancel_job_requires_confirm(self, destructive_on) -> None:
        from src.tools.job_management import cancel_job

        r = await cancel_job(None, 1, confirm=False)
        assert r["success"] is False
        assert "confirm=true" in r["error"].lower()


# ----- backup_restore -----


class TestBackupRestore:
    @pytest.mark.asyncio
    async def test_create_backup_rejects_bad_scheme(self, destructive_on) -> None:
        from src.tools.backup_restore import create_backup

        r = await create_backup(None, destination_uri="ftp://host/path")
        assert r["success"] is False

    @pytest.mark.asyncio
    async def test_restore_requires_destructive(self, destructive_off) -> None:
        from src.tools.backup_restore import restore_backup

        r = await restore_backup(None, source_uri="s3://b/p", confirm=True)
        assert r["success"] is False

    @pytest.mark.asyncio
    async def test_restore_requires_confirm(self, destructive_on) -> None:
        from src.tools.backup_restore import restore_backup

        r = await restore_backup(None, source_uri="s3://b/p", confirm=False)
        assert r["success"] is False
        assert "confirm=true" in r["error"].lower()


# ----- vector_search -----


class TestVectorSearch:
    @pytest.mark.asyncio
    async def test_rejects_bad_metric(self) -> None:
        from src.tools.vector_search import vector_similarity_search

        r = await vector_similarity_search(None, "docs", "embedding", [0.1, 0.2], metric="jaccard")
        assert r["success"] is False

    @pytest.mark.asyncio
    async def test_rejects_empty_query_vector(self) -> None:
        from src.tools.vector_search import vector_similarity_search

        r = await vector_similarity_search(None, "docs", "embedding", [], metric="cosine")
        assert r["success"] is False

    @pytest.mark.asyncio
    async def test_rejects_bad_table_name(self) -> None:
        from src.tools.vector_search import vector_similarity_search

        r = await vector_similarity_search(None, 'docs"; DROP', "embedding", [0.1], metric="cosine")
        assert r["success"] is False

    @pytest.mark.asyncio
    async def test_create_cspann_rejects_unknown_metric(self, destructive_on) -> None:
        from src.tools.vector_search import create_cspann_index

        r = await create_cspann_index(None, "docs", "embedding", metric="manhattan")
        assert r["success"] is False

    @pytest.mark.asyncio
    async def test_drop_cspann_requires_confirm(self, destructive_on) -> None:
        from src.tools.vector_search import drop_cspann_index

        r = await drop_cspann_index(None, "my_idx", confirm=False)
        assert r["success"] is False


# ----- multi_region -----


class TestMultiRegion:
    @pytest.mark.asyncio
    async def test_set_survival_goal_rejects_bad_goal(self) -> None:
        from src.tools.multi_region import set_survival_goal

        r = await set_survival_goal(None, "mydb", "MACHINE")
        assert r["success"] is False

    @pytest.mark.asyncio
    async def test_set_table_locality_rejects_bad_locality(self) -> None:
        from src.tools.multi_region import set_table_locality

        r = await set_table_locality(None, "users", "PER_NODE")
        assert r["success"] is False


# ----- changefeeds -----


class TestChangefeeds:
    @pytest.mark.asyncio
    async def test_rejects_bad_sink(self) -> None:
        from src.tools.changefeeds import create_changefeed

        r = await create_changefeed(None, ["users"], "ftp://h/x")
        assert r["success"] is False

    @pytest.mark.asyncio
    async def test_cancel_requires_destructive(self, destructive_off) -> None:
        from src.tools.changefeeds import cancel_changefeed

        r = await cancel_changefeed(None, 1, confirm=True)
        assert r["success"] is False


# ----- cluster_admin -----


class TestClusterAdmin:
    @pytest.mark.asyncio
    async def test_set_cluster_setting_requires_destructive(self, destructive_off) -> None:
        from src.tools.cluster_admin import set_cluster_setting

        r = await set_cluster_setting(None, "kv.gc.ttl_seconds", "3600")
        assert r["success"] is False

    @pytest.mark.asyncio
    async def test_set_cluster_setting_rejects_bad_name(self, destructive_on) -> None:
        from src.tools.cluster_admin import set_cluster_setting

        r = await set_cluster_setting(None, "evil; DROP TABLE x", "1")
        assert r["success"] is False

    @pytest.mark.asyncio
    async def test_decommission_requires_confirm(self, destructive_on) -> None:
        from src.tools.cluster_admin import decommission_node

        r = await decommission_node(None, 1, confirm=False)
        assert r["success"] is False
