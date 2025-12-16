import sys
import click
from src.common.config import parse_crdb_uri, set_crdb_config_from_cli
from src.common.server import mcp
from smithery.decorators import smithery

class CockroachMCPServer:
    def __init__(self):
        print("Starting the CockroachDB MCP Server", file=sys.stderr)

    @smithery.server
    def run(self):
        if mcp:
            mcp.run()

@click.command()
@click.option('--url', help='CockroachDB connection URI (cockroach://<username>:<password>@<host>:<port>/<database> or postgresql://<username>:<password>@<host>:<port>/<database>)')
@click.option('--host', help='CockroachDB host')
@click.option('--port', default=26257, type=int, help='CockroachDB port')
@click.option('--db', default='defaultdb', help='Cockroach database name')
@click.option('--username', default='root', help='Username')
@click.option('--password', help='Password')
@click.option('--ssl-mode', default='disable', help='SSL mode for CockroachDB connection. Possible values: disable, allow, prefer, require, verify-ca or verify-full. Default is disable.')
@click.option('--ssl-key', help='Path to SSL Client key file')
@click.option('--ssl-cert', help='Path to SSL Client certificate file')
@click.option('--ssl-ca-cert', help='Path to CA (Root) certificate file')
def cli(url, host, port, db, username, password,
        ssl_mode, ssl_key, ssl_cert, ssl_ca_cert):
    """CockroachDB MCP Server - Model Context Protocol server for CockroachDB."""

    # Handle CockroachDB URI if provided
    if url:
        try:
            uri_config = parse_crdb_uri(url)
            set_crdb_config_from_cli(uri_config)
        except ValueError as e:
            click.echo(f"Error parsing CockroachDB URI: {e}", err=True)
            sys.exit(1)
    elif host:
        # Set individual parameters
        cfg = {
            'host': host,
            'port': port,
            'username': username,
            'database': db,
        }

        if password:
            cfg['password'] = password
        if ssl_mode:
            cfg['ssl_mode'] = ssl_mode
        if ssl_key:
            cfg['ssl_key'] = ssl_key
        if ssl_cert:
            cfg['ssl_cert'] = ssl_cert
        if ssl_ca_cert:
            cfg['ssl_ca_cert'] = ssl_ca_cert
    
        set_crdb_config_from_cli(cfg)
    else: 
        print(f"You are in CLI mode. You must fill in at least one of the two parameters --url or --host to launch the MCP server", file=sys.stderr)
        sys.exit(1)

    # Start the server
    server = CockroachMCPServer()
    server.run()

def main():
    """Legacy main function for backward compatibility."""
    server = CockroachMCPServer()
    server.run()

if __name__ == "__main__":
    main()