"""Configuration loader for the CockroachDB MCP server.

Reads from environment variables (with .env support) and accepts overrides
from CLI args.

Public:
- get_config() returns a snapshot dict (read-only)
- set_config_from_cli(...) updates the underlying state from CLI parsing
- parse_crdb_uri(uri) returns a partial config dict from a URI
- ServerFlags is the dataclass for run-time policy (read-only, allow_destructive)
"""

from __future__ import annotations

import os
import urllib.parse
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv

from src.common.sql_safety import validate_ssl_mode

load_dotenv()


# Default port matches CockroachDB SQL interface.
_DEFAULT_PORT = 26257


def _initial_config() -> dict[str, Any]:
    return {
        "host": os.getenv("CRDB_HOST", "127.0.0.1"),
        "port": int(os.getenv("CRDB_PORT", str(_DEFAULT_PORT))),
        "username": os.getenv("CRDB_USERNAME", "root"),
        "password": os.getenv("CRDB_PWD") or None,
        "database": os.getenv("CRDB_DATABASE", "defaultdb"),
        "ssl_ca_cert": os.getenv("CRDB_SSL_CA_PATH") or None,
        "ssl_key": os.getenv("CRDB_SSL_KEYFILE") or None,
        "ssl_cert": os.getenv("CRDB_SSL_CERTFILE") or None,
        "ssl_mode": os.getenv("CRDB_SSL_MODE", "disable"),
        # Pool sizing - configurable via env so HTTP deployments can tune.
        "pool_min_size": int(os.getenv("CRDB_POOL_MIN", "1")),
        "pool_max_size": int(os.getenv("CRDB_POOL_MAX", "10")),
        "command_timeout": float(os.getenv("CRDB_COMMAND_TIMEOUT", "60")),
    }


# Module-level state, kept private. Use get_config() / set_config_from_cli().
_CRDB_CONFIG: dict[str, Any] = _initial_config()


def get_config() -> dict[str, Any]:
    """Return a shallow copy of the current effective configuration."""
    return dict(_CRDB_CONFIG)


def parse_crdb_uri(uri: str) -> dict[str, Any]:
    """Parse a CockroachDB / PostgreSQL URI into a config dict.

    Raises ValueError on unknown schemes or malformed URLs.
    """
    parsed = urllib.parse.urlparse(uri)

    if parsed.scheme not in ("cockroach", "postgresql", "postgres"):
        raise ValueError(f"Unsupported scheme: {parsed.scheme!r}")

    config: dict[str, Any] = {
        "url": uri,
        "host": parsed.hostname or "127.0.0.1",
        "port": parsed.port or _DEFAULT_PORT,
    }

    if parsed.path and parsed.path != "/":
        config["database"] = parsed.path.lstrip("/")
    else:
        config["database"] = "defaultdb"

    if parsed.username:
        config["username"] = parsed.username
    if parsed.password:
        config["password"] = parsed.password

    if parsed.query:
        query_params = urllib.parse.parse_qs(parsed.query)
        if "sslmode" in query_params:
            config["ssl_mode"] = validate_ssl_mode(query_params["sslmode"][0])
        if "sslrootcert" in query_params:
            config["ssl_ca_cert"] = query_params["sslrootcert"][0]
        if "sslcert" in query_params:
            config["ssl_cert"] = query_params["sslcert"][0]
        if "sslkey" in query_params:
            config["ssl_key"] = query_params["sslkey"][0]
        if "password" in query_params:
            config["password"] = query_params["password"][0]

    return config


def set_config_from_cli(updates: dict[str, Any]) -> None:
    """Merge CLI-provided overrides into the effective config.

    Port and pool sizes are coerced to int. Other values are kept as-is or
    None. SSL mode is validated.
    """
    int_keys = {"port", "pool_min_size", "pool_max_size"}
    float_keys = {"command_timeout"}
    for key, value in updates.items():
        if value is None:
            # Allow explicit None to clear a value
            _CRDB_CONFIG[key] = None
            continue
        if key in int_keys:
            _CRDB_CONFIG[key] = int(value)
        elif key in float_keys:
            _CRDB_CONFIG[key] = float(value)
        elif key == "ssl_mode":
            _CRDB_CONFIG[key] = validate_ssl_mode(str(value))
        else:
            _CRDB_CONFIG[key] = str(value)


@dataclass
class ServerFlags:
    """Run-time policy flags decided at server startup, not by tool callers."""

    read_only: bool = False
    allow_destructive: bool = False
    transport: str = "stdio"
    http_host: str | None = None
    http_port: int | None = None
    http_path: str | None = None
    stateless_http: bool = False


# Module-level flags object updated once at startup.
_FLAGS = ServerFlags()


def get_flags() -> ServerFlags:
    return _FLAGS


def set_flags(flags: ServerFlags) -> None:
    global _FLAGS
    _FLAGS = flags


# Backwards compatibility shim: some external code may still import CRDB_CONFIG.
# It is a live reference but treated as read-only by convention.
CRDB_CONFIG = _CRDB_CONFIG
