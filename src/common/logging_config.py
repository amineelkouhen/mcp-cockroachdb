"""Logging configuration for the CockroachDB MCP server.

Replaces ad-hoc print(..., file=sys.stderr) calls. Level is configurable via
the MCP_LOG_LEVEL environment variable (default: INFO).

For HTTP transport mode, set MCP_LOG_JSON=1 to emit structured JSON logs.
"""

from __future__ import annotations

import json
import logging
import os
import sys


def _configure_root_logger() -> logging.Logger:
    level_name = os.getenv("MCP_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    use_json = os.getenv("MCP_LOG_JSON", "").lower() in {"1", "true", "yes"}

    root = logging.getLogger("cockroachdb_mcp")
    root.setLevel(level)
    # Idempotent: clear pre-existing handlers if reconfiguring
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stderr)
    if use_json:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    root.propagate = False
    return root


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


_ROOT = _configure_root_logger()


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger under the cockroachdb_mcp tree."""
    return logging.getLogger(f"cockroachdb_mcp.{name}")
