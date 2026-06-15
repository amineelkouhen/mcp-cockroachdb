"""Tests for src.tools.query_engine.format_result."""

from __future__ import annotations

import json

from src.tools.query_engine import format_result


def test_json_empty() -> None:
    out = format_result([], "json")
    assert isinstance(out, str)
    assert json.loads(out) == []


def test_json_basic() -> None:
    out = format_result([{"a": 1, "b": "x"}], "json")
    assert json.loads(out) == [{"a": 1, "b": "x"}]


def test_csv_empty() -> None:
    assert format_result([], "csv") == ""


def test_csv_basic() -> None:
    out = format_result([{"a": 1, "b": "x"}, {"a": 2, "b": "y"}], "csv")
    assert out == "a,b\n1,x\n2,y"


def test_csv_escapes_quotes_and_commas() -> None:
    out = format_result([{"a": 'has "quote", comma'}], "csv")
    assert out == 'a\n"has ""quote"", comma"'


def test_csv_handles_none() -> None:
    out = format_result([{"a": None, "b": 1}], "csv")
    assert out == "a,b\n,1"


def test_table_empty() -> None:
    assert format_result([], "table") == ""


def test_table_basic() -> None:
    out = format_result([{"a": 1, "b": "xx"}], "table")
    # Header line, separator line, then data
    lines = out.split("\n")
    assert len(lines) == 3
    assert "a" in lines[0] and "b" in lines[0]
    assert "1" in lines[2] and "xx" in lines[2]


def test_unknown_format_returns_rows() -> None:
    rows = [{"a": 1}]
    assert format_result(rows, "weird") == rows
