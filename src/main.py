"""Entry point for the CockroachDB MCP server."""

from __future__ import annotations

import sys

import click

# Import tool modules to register them with the FastMCP instance.
import src.tools.cluster_monitoring  # noqa: F401
import src.tools.database_operations  # noqa: F401
import src.tools.query_engine  # noqa: F401
import src.tools.table_management  # noqa: F401
from src.common.config import (
    ServerFlags,
    parse_crdb_uri,
    set_config_from_cli,
    set_flags,
)
from src.common.logging_config import get_logger
from src.common.server import mcp
from src.version import __version__

log = get_logger("main")


class CockroachMCPServer:
    """Thin wrapper that runs FastMCP in stdio or HTTP transport mode."""

    def __init__(self) -> None:
        log.info("Starting CockroachDB MCP Server v%s", __version__)

    def run(
        self,
        transport: str,
        http_host: str | None,
        http_port: int | None,
        http_path: str | None,
        stateless_http: bool,
    ) -> None:
        if mcp is None:
            return
        if transport == "http":
            import uvicorn

            app = mcp.streamable_http_app()
            bind_host = http_host or "0.0.0.0"
            bind_port = http_port or 8000
            log.info("HTTP transport on %s:%s", bind_host, bind_port)
            uvicorn.run(app, host=bind_host, port=bind_port)
        else:
            mcp.run()


@click.command()
@click.version_option(__version__, prog_name="cockroachdb-mcp-server")
@click.option(
    "--url",
    help=(
        "CockroachDB connection URI "
        "(postgresql://<user>:<password>@<host>:<port>/<db> or cockroach://...)"
    ),
)
@click.option("--host", help="CockroachDB host")
@click.option("--port", default=26257, type=int, help="CockroachDB port")
@click.option("--db", default="defaultdb", help="CockroachDB database name")
@click.option("--username", default="root", help="Username")
@click.option("--password", help="Password")
@click.option(
    "--ssl-mode",
    default="disable",
    help=(
        "SSL mode for CockroachDB connection. "
        "One of: disable, allow, prefer, require, verify-ca, verify-full."
    ),
)
@click.option("--ssl-key", help="Path to SSL client key file")
@click.option("--ssl-cert", help="Path to SSL client certificate file")
@click.option("--ssl-ca-cert", help="Path to CA (root) certificate file")
@click.option(
    "--transport",
    type=click.Choice(["stdio", "http"]),
    default="stdio",
    show_default=True,
    help="MCP transport to use.",
)
@click.option("--http-host", help="HTTP host to bind for streamable HTTP transport.")
@click.option(
    "--http-port",
    type=int,
    help="HTTP port to bind for streamable HTTP transport.",
)
@click.option("--http-path", help="HTTP path for streamable HTTP transport (e.g., /mcp).")
@click.option(
    "--stateless-http/--stateful-http",
    default=False,
    show_default=True,
    help="Enable stateless HTTP mode for horizontal scaling.",
)
@click.option(
    "--use-env/--no-use-env",
    default=False,
    show_default=True,
    help="Read CockroachDB configuration from environment variables.",
)
@click.option(
    "--read-only/--no-read-only",
    default=False,
    show_default=True,
    help=(
        "Refuse all DDL and write tools (drop_*, create_*, execute_query of "
        "write statements, etc.)."
    ),
)
@click.option(
    "--allow-destructive/--no-allow-destructive",
    default=False,
    show_default=True,
    help=(
        "Required for drop_database, drop_table, drop_index, drop_view. "
        "Even with this flag, callers must pass confirm=True per call."
    ),
)
def cli(
    url: str | None,
    host: str | None,
    port: int,
    db: str,
    username: str,
    password: str | None,
    ssl_mode: str,
    ssl_key: str | None,
    ssl_cert: str | None,
    ssl_ca_cert: str | None,
    transport: str,
    http_host: str | None,
    http_port: int | None,
    http_path: str | None,
    stateless_http: bool,
    use_env: bool,
    read_only: bool,
    allow_destructive: bool,
) -> None:
    """CockroachDB MCP Server - Model Context Protocol server for CockroachDB."""

    if url:
        try:
            set_config_from_cli(parse_crdb_uri(url))
        except ValueError as exc:
            click.echo(f"Error parsing CockroachDB URI: {exc}", err=True)
            sys.exit(1)
    elif host:
        cfg = {
            "host": host,
            "port": port,
            "username": username,
            "database": db,
            "ssl_mode": ssl_mode,
        }
        if password is not None:
            cfg["password"] = password
        if ssl_key:
            cfg["ssl_key"] = ssl_key
        if ssl_cert:
            cfg["ssl_cert"] = ssl_cert
        if ssl_ca_cert:
            cfg["ssl_ca_cert"] = ssl_ca_cert
        set_config_from_cli(cfg)
    elif not use_env:
        click.echo(
            "You must provide --url, --host, or --use-env to launch the MCP server.",
            err=True,
        )
        sys.exit(1)

    # If both --read-only and --allow-destructive are passed, read-only wins.
    if read_only and allow_destructive:
        log.warning(
            "Both --read-only and --allow-destructive were set; read-only takes precedence."
        )

    set_flags(
        ServerFlags(
            read_only=read_only,
            allow_destructive=allow_destructive,
            transport=transport,
            http_host=http_host,
            http_port=http_port,
            http_path=http_path,
            stateless_http=stateless_http,
        )
    )

    server = CockroachMCPServer()
    server.run(transport, http_host, http_port, http_path, stateless_http)


def main() -> None:
    """Legacy main function for backward compatibility."""
    server = CockroachMCPServer()
    server.run("stdio", None, None, None, False)


if __name__ == "__main__":
    main()
