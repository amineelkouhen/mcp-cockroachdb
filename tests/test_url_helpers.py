"""Tests for src.common.connection URL helpers."""

from __future__ import annotations

from src.common.connection import (
    create_url,
    extract_database,
    replace_database_in_url,
)


def test_create_url_basic() -> None:
    url = create_url(
        "host",
        26257,
        "mydb",
        "root",
        "",
        "disable",
        "",
        "",
        "",
    )
    assert url == "postgresql://root@host:26257/mydb"


def test_create_url_with_password() -> None:
    url = create_url(
        "host",
        26257,
        "mydb",
        "root",
        "s3cret",
        "disable",
        "",
        "",
        "",
    )
    assert "root:s3cret@host" in url


def test_create_url_password_special_chars() -> None:
    url = create_url(
        "host",
        26257,
        "mydb",
        "root",
        "a/b@c",
        "disable",
        "",
        "",
        "",
    )
    # password should be URL-encoded
    assert "a/b@c" not in url
    assert "a%2Fb%40c" in url


def test_create_url_ssl() -> None:
    url = create_url(
        "host",
        26257,
        "mydb",
        "root",
        "",
        "verify-full",
        "/c.crt",
        "/c.key",
        "/ca.crt",
    )
    assert "sslmode=verify-full" in url
    assert "sslrootcert=" in url
    assert "sslcert=" in url
    assert "sslkey=" in url


def test_extract_database_no_query() -> None:
    assert extract_database("postgresql://root@host:26257/mydb") == "mydb"


def test_extract_database_with_query() -> None:
    assert extract_database("postgresql://root@host:26257/mydb?sslmode=disable") == "mydb"


def test_extract_database_empty() -> None:
    assert extract_database("postgresql://root@host:26257/") == ""


def test_replace_database_in_url_preserves_query() -> None:
    src = "postgresql://root@host:26257/mydb?sslmode=verify-full&sslcert=/x"
    out = replace_database_in_url(src, "other")
    assert out == "postgresql://root@host:26257/other?sslmode=verify-full&sslcert=/x"


def test_replace_database_in_url_preserves_userinfo() -> None:
    src = "postgresql://user:pass@host/mydb"
    out = replace_database_in_url(src, "newdb")
    assert "user:pass@host" in out
    assert "/newdb" in out
