"""Tests for src.common.serializers."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from src.common.serializers import serialize_row, serialize_value


def test_datetime_to_iso() -> None:
    dt = datetime(2026, 1, 2, 3, 4, 5)
    assert serialize_value(dt) == "2026-01-02T03:04:05"


def test_date_to_iso() -> None:
    d = date(2026, 1, 2)
    assert serialize_value(d) == "2026-01-02"


def test_decimal_to_float() -> None:
    assert serialize_value(Decimal("1.5")) == 1.5


def test_uuid_to_str() -> None:
    u = UUID("12345678-1234-5678-1234-567812345678")
    assert serialize_value(u) == "12345678-1234-5678-1234-567812345678"


def test_bytes_to_string() -> None:
    assert serialize_value(b"hello") == "hello"


def test_bytes_with_invalid_utf8_replaced() -> None:
    out = serialize_value(b"\xff\xfe")
    assert isinstance(out, str)


def test_nested_dict() -> None:
    src = {"a": Decimal("1.5"), "b": {"c": datetime(2026, 1, 1)}}
    out = serialize_value(src)
    assert out == {"a": 1.5, "b": {"c": "2026-01-01T00:00:00"}}


def test_nested_list() -> None:
    out = serialize_value([Decimal("1"), Decimal("2")])
    assert out == [1.0, 2.0]


def test_primitives_passthrough() -> None:
    assert serialize_value(1) == 1
    assert serialize_value("x") == "x"
    assert serialize_value(None) is None
    assert serialize_value(True) is True


def test_serialize_row() -> None:
    row = {"d": date(2026, 1, 2), "n": Decimal("3.14")}
    assert serialize_row(row) == {"d": "2026-01-02", "n": 3.14}
