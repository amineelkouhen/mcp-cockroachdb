"""Tests for src.common.sql_safety."""

from __future__ import annotations

import pytest

from src.common.sql_safety import (
    UnsafeIdentifierError,
    quote_identifier,
    quote_qualified_identifier,
    redact_dsn,
    validate_format,
    validate_identifier,
    validate_import_scheme,
    validate_interval,
    validate_ssl_mode,
)


class TestValidateIdentifier:
    @pytest.mark.parametrize(
        "name",
        ["t", "table_1", "_underscore", "Camel", "VECTOR", "x" * 63],
    )
    def test_accepts_valid(self, name: str) -> None:
        assert validate_identifier(name) == name

    @pytest.mark.parametrize(
        "name",
        [
            "",  # empty
            "1abc",  # starts with digit
            "a-b",  # hyphen
            "a b",  # space
            'foo"; DROP',  # quote + sql
            "foo;DROP",  # semicolon
            "x" * 64,  # too long
            None,  # not a string
            123,  # not a string
            "schema.table",  # qualified not allowed by base validator
        ],
    )
    def test_rejects_invalid(self, name) -> None:
        with pytest.raises(UnsafeIdentifierError):
            validate_identifier(name)


class TestQuoteIdentifier:
    def test_quotes_identifier(self) -> None:
        assert quote_identifier("users") == '"users"'

    def test_rejects_injection(self) -> None:
        with pytest.raises(UnsafeIdentifierError):
            quote_identifier('foo"; DROP TABLE evil; --')


class TestQuoteQualifiedIdentifier:
    def test_accepts_unqualified(self) -> None:
        assert quote_qualified_identifier("users") == '"users"'

    def test_accepts_qualified(self) -> None:
        assert quote_qualified_identifier("public.users") == '"public"."users"'

    def test_rejects_three_part(self) -> None:
        with pytest.raises(UnsafeIdentifierError):
            quote_qualified_identifier("db.public.users")


class TestValidateSslMode:
    @pytest.mark.parametrize(
        "mode", ["disable", "allow", "prefer", "require", "verify-ca", "verify-full"]
    )
    def test_accepts_known(self, mode: str) -> None:
        assert validate_ssl_mode(mode) == mode

    def test_empty_returns_disable(self) -> None:
        assert validate_ssl_mode("") == "disable"
        assert validate_ssl_mode(None) == "disable"

    def test_rejects_unknown(self) -> None:
        with pytest.raises(UnsafeIdentifierError):
            validate_ssl_mode("none")


class TestValidateFormat:
    @pytest.mark.parametrize("fmt", ["json", "csv", "table"])
    def test_accepts(self, fmt: str) -> None:
        assert validate_format(fmt) == fmt

    def test_empty_defaults_to_json(self) -> None:
        assert validate_format("") == "json"
        assert validate_format(None) == "json"

    def test_rejects_unknown(self) -> None:
        with pytest.raises(UnsafeIdentifierError):
            validate_format("xml")


class TestValidateImportScheme:
    @pytest.mark.parametrize("scheme", ["s3", "azure-blob", "azure", "gs", "http", "https"])
    def test_accepts(self, scheme: str) -> None:
        assert validate_import_scheme(scheme) == scheme

    def test_rejects(self) -> None:
        with pytest.raises(UnsafeIdentifierError):
            validate_import_scheme("file")


class TestValidateInterval:
    @pytest.mark.parametrize("value", ["1:0", "10:30", "0:1", "999999:999999"])
    def test_accepts(self, value: str) -> None:
        assert validate_interval(value) == value

    @pytest.mark.parametrize(
        "value",
        ["", "1", "abc", "1m", "10:30:45", "-1:0", "1:0; DROP TABLE x"],
    )
    def test_rejects(self, value) -> None:
        with pytest.raises(UnsafeIdentifierError):
            validate_interval(value)


class TestRedactDsn:
    def test_redacts_password_in_userinfo(self) -> None:
        dsn = "postgresql://user:secret@host:5432/db"
        out = redact_dsn(dsn)
        assert "secret" not in out
        assert "***" in out

    def test_redacts_password_in_query(self) -> None:
        dsn = "postgresql://user@host:5432/db?password=secret"
        out = redact_dsn(dsn)
        assert "secret" not in out

    def test_no_password_unchanged(self) -> None:
        dsn = "postgresql://user@host:5432/db"
        assert redact_dsn(dsn) == dsn

    def test_empty_string(self) -> None:
        assert redact_dsn("") == ""
