"""Tests that policy flags actually gate the relevant tools."""

from __future__ import annotations

import pytest

from src.common.config import ServerFlags, set_flags


@pytest.fixture
def read_only_flags():
    set_flags(ServerFlags(read_only=True))
    yield
    set_flags(ServerFlags())  # reset to defaults


@pytest.fixture
def destructive_off_flags():
    set_flags(ServerFlags(read_only=False, allow_destructive=False))
    yield
    set_flags(ServerFlags())


@pytest.fixture
def destructive_on_flags():
    set_flags(ServerFlags(read_only=False, allow_destructive=True))
    yield
    set_flags(ServerFlags())


class TestReadOnlyMode:
    @pytest.mark.asyncio
    async def test_create_database_refused(self, read_only_flags) -> None:
        from src.tools.database_operations import create_database

        result = await create_database(None, "x")
        assert result["success"] is False
        assert "read-only" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_drop_database_refused(self, read_only_flags) -> None:
        from src.tools.database_operations import drop_database

        result = await drop_database(None, "x", confirm=True)
        assert result["success"] is False
        assert "read-only" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_create_table_refused(self, read_only_flags) -> None:
        from src.tools.table_management import create_table

        result = await create_table(None, "x", [{"name": "a", "datatype": "INT"}])
        assert result["success"] is False
        assert "read-only" in result["error"].lower()


class TestDestructiveGating:
    @pytest.mark.asyncio
    async def test_drop_table_refused_without_allow_destructive(
        self, destructive_off_flags
    ) -> None:
        from src.tools.table_management import drop_table

        result = await drop_table(None, "x", confirm=True)
        assert result["success"] is False
        assert "destructive" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_drop_table_requires_confirm(self, destructive_on_flags) -> None:
        from src.tools.table_management import drop_table

        result = await drop_table(None, "users", confirm=False)
        assert result["success"] is False
        assert "confirm=true" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_drop_database_requires_confirm(self, destructive_on_flags) -> None:
        from src.tools.database_operations import drop_database

        result = await drop_database(None, "mydb", confirm=False)
        assert result["success"] is False
        assert "confirm=true" in result["error"].lower()


class TestIdentifierValidation:
    """Smoke: SQL-injection-shaped identifiers are rejected before any DB call."""

    @pytest.mark.asyncio
    async def test_create_database_rejects_injection(self, destructive_on_flags) -> None:
        from src.tools.database_operations import create_database

        result = await create_database(None, 'foo"; DROP DATABASE evil; --')
        assert result["success"] is False
        assert "invalid" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_create_table_rejects_injection(self, destructive_on_flags) -> None:
        from src.tools.table_management import create_table

        result = await create_table(
            None,
            'foo"; DROP TABLE evil; --',
            [{"name": "a", "datatype": "INT"}],
        )
        assert result["success"] is False
        assert "invalid" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_create_view_rejects_non_select_body(self, destructive_on_flags) -> None:
        from src.tools.table_management import create_view

        result = await create_view(None, "v", "DROP TABLE evil; SELECT 1")
        assert result["success"] is False
        assert "select" in result["error"].lower()
