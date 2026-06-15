"""Standardized tool return helpers.

Every MCP tool returns a dict with a consistent shape so the LLM can
predictably extract success/data/error.
"""

from __future__ import annotations

from typing import Any


def ok(**data: Any) -> dict[str, Any]:
    """Return a successful tool response with the given data fields."""
    return {"success": True, **data}


def err(error: str | Exception, **extra: Any) -> dict[str, Any]:
    """Return a failed tool response with the given error message."""
    return {"success": False, "error": str(error), **extra}
