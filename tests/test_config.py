"""Tests for src.common.config (URI parsing)."""

from __future__ import annotations

import pytest

from src.common.config import parse_crdb_uri


class TestParseCrdbUri:
    def test_full_uri(self) -> None:
        out = parse_crdb_uri("postgresql://user:pass@host:5432/mydb")
        assert out["host"] == "host"
        assert out["port"] == 5432
        assert out["username"] == "user"
        assert out["password"] == "pass"
        assert out["database"] == "mydb"

    def test_cockroach_scheme(self) -> None:
        out = parse_crdb_uri("cockroach://user@host:26257/defaultdb")
        assert out["host"] == "host"
        assert out["username"] == "user"

    def test_postgres_scheme(self) -> None:
        out = parse_crdb_uri("postgres://host/db")
        assert out["host"] == "host"
        assert out["database"] == "db"

    def test_no_password(self) -> None:
        out = parse_crdb_uri("postgresql://user@host:26257/mydb")
        assert "password" not in out

    def test_default_database(self) -> None:
        out = parse_crdb_uri("postgresql://host:26257")
        assert out["database"] == "defaultdb"

    def test_default_port(self) -> None:
        out = parse_crdb_uri("postgresql://host/mydb")
        assert out["port"] == 26257

    def test_ssl_query_params(self) -> None:
        out = parse_crdb_uri(
            "postgresql://user@host:26257/mydb"
            "?sslmode=verify-full"
            "&sslrootcert=/path/ca.crt"
            "&sslcert=/path/c.crt"
            "&sslkey=/path/c.key"
        )
        assert out["ssl_mode"] == "verify-full"
        assert out["ssl_ca_cert"] == "/path/ca.crt"
        assert out["ssl_cert"] == "/path/c.crt"
        assert out["ssl_key"] == "/path/c.key"

    def test_password_in_query(self) -> None:
        out = parse_crdb_uri("postgresql://user@host/mydb?password=secret")
        assert out["password"] == "secret"

    def test_rejects_unknown_scheme(self) -> None:
        with pytest.raises(ValueError):
            parse_crdb_uri("mysql://host/db")

    def test_rejects_invalid_ssl_mode(self) -> None:
        from src.common.sql_safety import UnsafeIdentifierError

        with pytest.raises(UnsafeIdentifierError):
            parse_crdb_uri("postgresql://host/db?sslmode=invalid")
