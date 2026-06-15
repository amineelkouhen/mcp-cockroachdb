"""Shared serializers for JSON-incompatible Python/PostgreSQL types.

Used by every tool that returns rows to the MCP client.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


def serialize_value(value: Any) -> Any:
    """Convert non-JSON-serializable types to serializable ones."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {k: serialize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize_value(v) for v in value]
    return value


def serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Serialize all values in a row dictionary."""
    return {k: serialize_value(v) for k, v in row.items()}
