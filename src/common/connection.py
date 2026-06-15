"""Async connection pool management for CockroachDB.

Single-process singleton pool. Built from the merged effective config in
src.common.config. Pool sizing and command timeout are configurable via env
vars (CRDB_POOL_MIN, CRDB_POOL_MAX, CRDB_COMMAND_TIMEOUT).
"""

from __future__ import annotations

import urllib.parse
from typing import Any

import asyncpg

from src.common.config import get_config
from src.common.logging_config import get_logger
from src.common.sql_safety import validate_ssl_mode

log = get_logger("connection")


class CockroachConnectionPool:
    _instance: asyncpg.Pool | None = None
    database_url: str = ""
    current_database: str = ""
    query_history: list[dict[str, Any]] = []

    @classmethod
    async def get_connection_pool(cls) -> asyncpg.Pool:
        if cls._instance is None or cls._instance._closed:
            await cls.create_connection_pool(create_default_url())
        return cls._instance  # type: ignore[return-value]

    @classmethod
    async def refresh_connection_pool(
        cls,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        sslmode: str,
        sslcert: str,
        sslkey: str,
        sslrootcert: str,
    ) -> asyncpg.Pool:
        database_url = create_url(
            host, port, database, username, password, sslmode, sslcert, sslkey, sslrootcert
        )
        return await cls.create_connection_pool(database_url)

    @classmethod
    async def create_connection_pool(cls, database_url: str) -> asyncpg.Pool:
        if not database_url:
            raise ValueError("database_url must be a non-empty string")
        # Close any existing pool gracefully before replacing it.
        if cls._instance is not None and not cls._instance._closed:
            try:
                await cls._instance.close()
            except Exception as exc:
                log.warning("error closing previous pool: %s", exc)

        cfg = get_config()
        try:
            cls._instance = await asyncpg.create_pool(
                database_url,
                min_size=int(cfg.get("pool_min_size", 1)),
                max_size=int(cfg.get("pool_max_size", 10)),
                command_timeout=float(cfg.get("command_timeout", 60.0)),
            )
            cls.database_url = database_url
            cls.current_database = extract_database(database_url)
            log.info(
                "connection pool ready: host=%s db=%s pool=%s/%s",
                _hide(database_url),
                cls.current_database,
                cfg.get("pool_min_size", 1),
                cfg.get("pool_max_size", 10),
            )
        except Exception as exc:
            log.error("cannot create connection pool: %s", exc)
            raise

        return cls._instance

    @classmethod
    async def close(cls) -> None:
        if cls._instance is not None and not cls._instance._closed:
            await cls._instance.close()
        cls._instance = None
        cls.database_url = ""
        cls.current_database = ""


def create_default_url() -> str:
    """Build a DSN from the effective configuration."""
    cfg = get_config()
    return create_url(
        cfg["host"],
        cfg["port"],
        cfg["database"],
        cfg["username"],
        cfg.get("password") or "",
        cfg.get("ssl_mode") or "disable",
        cfg.get("ssl_cert") or "",
        cfg.get("ssl_key") or "",
        cfg.get("ssl_ca_cert") or "",
    )


def create_url(
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
    sslmode: str,
    sslcert: str,
    sslkey: str,
    sslrootcert: str,
) -> str:
    """Compose a postgresql:// DSN. Password is URL-encoded if present."""
    sslmode = validate_ssl_mode(sslmode)

    userinfo = urllib.parse.quote(username, safe="")
    if password:
        userinfo = f"{userinfo}:{urllib.parse.quote(password, safe='')}"

    host_part = host
    if ":" in host and not host.startswith("["):
        host_part = f"[{host}]"

    url = f"postgresql://{userinfo}@{host_part}:{int(port)}/{urllib.parse.quote(str(database), safe='')}"

    params: list[tuple[str, str]] = []
    if sslmode and sslmode != "disable":
        params.append(("sslmode", sslmode))
        if sslrootcert:
            params.append(("sslrootcert", sslrootcert))
        if sslcert:
            params.append(("sslcert", sslcert))
        if sslkey:
            params.append(("sslkey", sslkey))
    if params:
        url += "?" + urllib.parse.urlencode(params)
    return url


def extract_database(database_url: str) -> str:
    """Return the database name from a DSN, ignoring query string."""
    parsed = urllib.parse.urlparse(database_url)
    db = parsed.path.lstrip("/")
    return urllib.parse.unquote(db) if db else ""


def replace_database_in_url(database_url: str, new_database: str) -> str:
    """Return a copy of database_url with the path replaced by new_database.

    Keeps user, host, port, and query parameters intact. Used by switch_database.
    """
    parsed = urllib.parse.urlparse(database_url)
    new_path = "/" + urllib.parse.quote(new_database, safe="")
    return urllib.parse.urlunparse(parsed._replace(path=new_path))


def _hide(url: str) -> str:
    """Tiny helper for log lines - never log full DSN with password."""
    from src.common.sql_safety import redact_dsn

    return redact_dsn(url)
