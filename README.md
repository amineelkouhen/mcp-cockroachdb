# CockroachDB MCP Server
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-blue)](https://mcp.so/server/cockroachdb-mcp-server/cockroachdb)
[![Trust Score](https://archestra.ai/mcp-catalog/api/badge/quality/amineelkouhen/mcp-cockroachdb)](https://archestra.ai/mcp-catalog/amineelkouhen__mcp-cockroachdb)

## Overview

The CockroachDB MCP Server is a **natural language interface** designed for LLMs and agentic applications to manage, monitor, and query data in CockroachDB. It integrates seamlessly with **MCP (Model Content Protocol)** clients, such as Claude Desktop or Cursor, enabling AI-driven workflows to interact directly with your database. 

## Table of Contents
- [Overview](#overview)
- [Features](#features)
- [Tools](#tools)
  - [Cluster Monitoring](#cluster-monitoring)
  - [Database Operations](#database-operations)
  - [Table Management](#table-management)
  - [Query Engine](#query-engine)
  - [User & Privilege Management](#user--privilege-management)
  - [Vector Search](#vector-search)
  - [Job Management](#job-management)
  - [Backup & Restore](#backup--restore)
  - [Statistics](#statistics)
  - [Multi-Region](#multi-region)
  - [Changefeeds](#changefeeds)
  - [Cluster Admin](#cluster-admin)
  - [Diagnostics](#diagnostics)
- [Installation](#installation)
  - [Quick Start with uvx](#quick-start-with-uvx)
  - [Development Installation](#development-installation)
  - [With Docker](#with-docker)
- [Configuration](#configuration)
  - [Configuration via command line arguments](#configuration-via-command-line-arguments)
  - [Configuration via Environment Variables](#configuration-via-environment-variables)
- [Integrations](#integrations)
  - [OpenAI Agents SDK](#openai-agents-sdk)
  - [Augment](#augment)
  - [Claude Desktop](#claude-desktop)
  - [VS Code with GitHub Copilot](#vs-code-with-github-copilot)
  - [Cursor](#cursor)
- [Testing](#testing)
- [Contributing](#contributing)
- [License](#license)
- [Quality Badge](#quality-badge)
- [Contact](#contact)

## Features
- **Natural-Language Queries**: AI agents can query and transact via natural language.
- **Cluster Monitoring**: Cluster status, node health, replication, slow queries, contention, index recommendations.
- **Database Operations**: List, create, drop, and switch databases.
- **Table Management**: Create, drop, alter (add/drop/rename column), truncate, rename, describe; bulk-import; indexes, views, schemas.
- **Query Engine**: Parameterized SQL with json/csv/table output, multi-statement transactions, explain, history.
- **User & Privilege Management**: Provision SQL users and roles, grant/revoke privileges. Lets you run the agent under a scoped non-root user.
- **Vector Search**: Similarity search with cosine/L2/inner-product metrics (auto-detected from index opclass), C-SPANN ANN index management (v25.2+).
- **Job Management**: Observe and control async jobs (BACKUP, RESTORE, IMPORT, CHANGEFEED, SCHEMA CHANGE).
- **Backup & Restore**: Full / database / table backup and restore against s3, gs, azure, nodelocal, userfile.
- **Statistics**: Create and show optimizer statistics.
- **Multi-Region**: Regions, survival goals, locality (REGIONAL_BY_ROW etc.), zone configuration.
- **Changefeeds**: CDC pipelines to Kafka / webhook / cloud-storage with sink-scheme validation.
- **Cluster Admin**: Cluster settings, decommission/drain (gated).
- **Diagnostics**: Tracing spans, statement-diagnostics bundles.
- **Safety First**: Strict identifier validation, parameterized values, `--read-only` mode, explicit `confirm=True` for destructive ops, redacted DSN responses.
- **Seamless MCP Integration**: Works with any MCP client (Claude Desktop, Cursor, VS Code Copilot, OpenAI Agents SDK, etc.).
- **Multiple Transports**: stdio (default) and streamable HTTP.

## Tools

The CockroachDB MCP Server Server provides tools to manage the data stored in CockroachDB. 

![architecture](https://github.com/user-attachments/assets/36a121d9-48b7-4840-9317-002a38441b8d)

The tools are organized into thirteen categories. Every write-shaped tool is gated by `--read-only`. Every destructive tool also requires `--allow-destructive` plus a per-call `confirm=True` parameter; see the [Safety Model](#safety-model) section.

### Cluster Monitoring

Purpose:
Provides tools for monitoring and managing CockroachDB clusters.

Summary:
- Get cluster health and node status.
- Show currently running queries.
- Analyze query performance statistics.
- Retrieve replication and distribution status for tables or the whole database.
- Get query execution insights with optional keyword filtering.
- Find slow queries from statement statistics with optional keyword filtering.
- Get transaction execution insights with optional keyword filtering.
- View contention events with optional table filtering.
- Get index recommendations from query insights.

### Database Operations

Purpose:
Handles database-level operations and connection management.

Summary:
- Connect to a CockroachDB database.
- List, create, drop, and switch databases.
- Get connection status and active sessions.
- Retrieve database settings.

### Table Management

Purpose:
Provides tools for managing tables, indexes, views, schemas, and relationships in CockroachDB.

Summary:
- Create, drop, describe, rename, and truncate tables (destructive ops gated).
- `alter_table_add_column`, `alter_table_drop_column`, `alter_table_rename_column`.
- Bulk import data into tables (CSV / Avro from s3/gs/azure/http(s)).
- Manage indexes (create/drop).
- Manage views (create/drop, list).
- Manage schemas (`list_schemas`, `create_schema`, `drop_schema`).
- List tables and table relationships; analyze schema structure and metadata.

### Query Engine

Purpose:
Executes and manages SQL queries and transactions.

Summary:
- Execute SQL queries with formatting options (JSON, CSV, table).
- Run multi-statement transactions.
- Explain query plans for optimization.
- Track and retrieve query history.

### User & Privilege Management

Purpose:
Manage SQL users, roles, and privileges. Use this from an administrative agent
to provision the agent's own scoped (non-root) user.

Summary:
- `list_users`, `create_user`, `drop_user`, `alter_user_password`.
- `create_role`, `drop_role`, `grant_role`, `revoke_role`.
- `show_grants`, `grant_privileges`, `revoke_privileges`.

Privileges are validated against an allowlist (`SELECT`, `INSERT`, `UPDATE`,
`DELETE`, `ALL`, `BACKUP`, `RESTORE`, `MODIFYCLUSTERSETTING`, ...). Identifiers
go through the same strict regex as everywhere else.

### Vector Search

Purpose:
Search VECTOR columns with CockroachDB's similarity operators (v25.2+) and
manage C-SPANN ANN indexes.

Summary:
- `vector_similarity_search` with `metric` of `cosine` (default), `l2`, `ip`,
  or `auto` (matches the existing index opclass). Returns `distance` and a
  derived `similarity` field.
- `create_cspann_index` with metric → opclass mapping
  (`vector_cosine_ops` / `vector_l2_ops` / `vector_ip_ops`).
- `drop_cspann_index` (destructive).

The query vector is always passed as a `$1::VECTOR` parameter; identifier and
optional `where` clause values are validated. For normalized embeddings (e.g.
Takara DS1, OpenAI text-embedding-3) all three metrics rank identically; the
default `cosine` is the safest because it ignores magnitude.

### Job Management

Purpose:
Observe and control long-running CockroachDB jobs (BACKUP, RESTORE, IMPORT,
SCHEMA CHANGE, CHANGEFEED).

Summary:
- `list_jobs` (filter by status and type), `get_job_status`.
- `pause_job`, `resume_job`, `cancel_job` (destructive).

### Backup & Restore

Purpose:
Take and restore cluster, database, and table backups.

Summary:
- `create_backup` to s3/gs/azure/nodelocal/userfile destinations.
- `list_backups` to enumerate backups at a storage URI.
- `restore_backup` (destructive) with optional `new_db_name`.
- `list_scheduled_backups`.

URI schemes are validated against an allowlist; identifier targets are
identifier-validated.

### Statistics

Purpose:
Compute and inspect the table statistics the cost-based optimizer relies on.

Summary:
- `create_statistics` (CREATE STATISTICS).
- `show_statistics` (SHOW STATISTICS FOR TABLE).

### Multi-Region

Purpose:
Configure multi-region behaviour: regions, survival goals, table localities,
zone configurations.

Summary:
- `show_regions`, `show_database_regions`.
- `add_database_region`, `drop_database_region` (destructive).
- `set_survival_goal` (`ZONE` or `REGION`).
- `set_table_locality` (`REGIONAL`, `REGIONAL_BY_ROW`, `REGIONAL_BY_TABLE`, `GLOBAL`).
- `show_zone_config` for DATABASE/TABLE/INDEX.

### Changefeeds

Purpose:
Set up and operate CDC pipelines to Kafka, webhooks, or cloud storage.

Summary:
- `create_changefeed` with sink-scheme validation (kafka, webhook-http(s), s3,
  gs, azure-blob, external, null), JSON or Avro format, choice of envelope.
- `list_changefeeds`, `pause_changefeed`, `resume_changefeed`.
- `cancel_changefeed` (destructive).

### Cluster Admin

Purpose:
Cluster-wide administration: cluster settings and node lifecycle.

Summary:
- `show_cluster_setting`, `set_cluster_setting`, `reset_cluster_setting`
  (destructive). Setting names are validated against a strict regex.
- `decommission_node`, `drain_node`. Note that SQL-initiated decommission
  only marks intent; for the full lifecycle use the `cockroach node` CLI.

### Diagnostics

Purpose:
Inspect tracing spans and request statement-diagnostics bundles.

Summary:
- `get_recent_traces` from `crdb_internal.cluster_inflight_traces`.
- `list_statement_diagnostics_requests`.
- `request_statement_diagnostics` for a statement fingerprint.

## Installation

The CockroachDB MCP Server supports the `stdio` [transport](https://modelcontextprotocol.io/docs/concepts/transports#standard-input%2Foutput-stdio) and the `streamable-http` transport.

### Quick Start with uvx 

The easiest way to use the CockroachDB MCP Server is with `uvx`, which allows you to run it directly from GitHub (from a branch, or use a tagged release). It is recommended to use a tagged release. The `main` branch is under active development and may contain breaking changes. As an example, you can execute the following command to run the `0.1.0` release:

```commandline
uvx --from git+https://github.com/amineelkouhen/mcp-cockroachdb.git@0.1.0 cockroachdb-mcp-server --url postgresql://localhost:26257/defaultdb
```

Check the release notes for the latest version in the [Releases](https://github.com/amineelkouhen/mcp-cockroachdb/releases) section.
Additional examples are provided below.

```sh
# Run with CockroachDB URI
uvx --from git+https://github.com/amineelkouhen/mcp-cockroachdb.git cockroachdb-mcp-server --url postgresql://localhost:26257/defaultdb

# Run with individual parameters
uvx --from git+https://github.com/amineelkouhen/mcp-cockroachdb.git cockroachdb-mcp-server --host localhost --port 26257 --database defaultdb --user root --password mypassword

# See all options
uvx --from git+https://github.com/amineelkouhen/mcp-cockroachdb.git cockroachdb-mcp-server --help

# Run with streamable HTTP transport
uvx --from git+https://github.com/amineelkouhen/mcp-cockroachdb.git cockroachdb-mcp-server \
  --url postgresql://localhost:26257/defaultdb \
  --transport http \
  --http-host 0.0.0.0 \
  --http-port 8000 \
  --http-path /mcp
```

### Development Installation

For development or if you prefer to clone the repository:

```sh
# Clone the repository
git clone https://github.com/amineelkouhen/mcp-cockroachdb.git
cd mcp-cockroachdb

# Install dependencies using uv
uv venv
source .venv/bin/activate
uv sync

# Run with CLI interface
uv run cockroachdb-mcp-server --help

# Or run the main file directly (uses environment variables)
uv run src/main.py
```

Once you cloned the repository, installed the dependencies and verified you can run the server, you can configure Claude Desktop or any other MCP Client to use this MCP Server running the main file directly (it uses environment variables). This is usually preferred for development.
The following example is for Claude Desktop, but the same applies to any other MCP Client.

1. Specify your CockroachDB credentials and TLS configuration
2. Retrieve your `uv` command full path (e.g. `which uv`)
3. Edit the `claude_desktop_config.json` configuration file
   - on a MacOS, at `~/Library/Application Support/Claude/`

```json
{
    "mcpServers": {
        "cockroach": {
            "command": "<full_path_uv_command>",
            "args": [
                "--directory",
                "<your_mcp_server_directory>",
                "run",
                "src/main.py"
            ],
            "env": {
                "CRDB_HOST": "<your_cockroachdb_hostname>",
                "CRDB_PORT": "<your_cockroachdb_port>",
                "CRDB_DATABASE": "<your_cockroach_database>",
                "CRDB_USERNAME": "<your_cockroachdb_user>",
                "CRDB_PWD": "<your_cockroachdb_password>",
                "CRDB_SSL_MODE": "disable|allow|prefer|require|verify-ca|verify-full",
                "CRDB_SSL_CA_PATH": "<your_cockroachdb_ca_path>",
                "CRDB_SSL_KEYFILE": "<your_cockroachdb_keyfile_path>",
                "CRDB_SSL_CERTFILE": "<your_cockroachdb_certificate_path>",
            }
        }
    }
}
```

You can troubleshoot problems by tailing the log file.

```commandline
tail -f ~/Library/Logs/Claude/mcp-server-cockroach.log
```

### With Docker Compose (Local Development)

For local development and testing, use the provided `docker-compose.yaml` to spin up both CockroachDB and the MCP server:

```bash
# Start CockroachDB and MCP server
docker compose up -d

# The MCP server is available at http://localhost:8000/mcp/
# CockroachDB UI is available at http://localhost:8080

# View logs
docker compose logs -f mcp-server

# Stop and clean up
docker compose down -v
```

### With Docker

You can use a dockerized deployment of this server. You can either build your image or use the official [CockroachDB MCP Docker](https://hub.docker.com/r/mcp/cockroachdb) image.

If you'd like to build your image, the CockroachDB MCP Server provides a Dockerfile. Build this server's image with:

```commandline
docker build -t mcp-cockroachdb .
```

Finally, configure the client to create the container at start-up. An example for Claude Desktop is provided below. Edit the `claude_desktop_config.json` and add:

```json
{
  "mcpServers": {
    "cockroach": {
      "command": "docker",
      "args": ["run",
                "--rm",
                "--name",
                "cockroachdb-mcp-server",
                "-e", "CRDB_HOST=<cockroachdb_host>",
                "-e", "CRDB_PORT=<cockroachdb_port>",
                "-e", "CRDB_DATABASE=<cockroachdb_database>",
                "-e", "CRDB_USERNAME=<cockroachdb_user>",
                "mcp-cockroachdb"]
    }
  }
}
```

To use the [CockroachDB MCP Docker](https://hub.docker.com/mcp/server/cockroachdb) image, just replace your image name (`mcp-cockroachdb` in the example above) with `mcp/cockroachdb`.

## Configuration

The CockroachDB MCP Server can be configured in two ways: either via command-line arguments or via environment variables.
The precedence is: CLI arguments > environment variables > default values.

### Configuration via command line arguments

When using the CLI interface, you can configure the server with command line arguments:

```sh
# Basic CockroachDB connection
uvx --from git+https://github.com/amineelkouhen/mcp-cockroachdb.git cockroachdb-mcp-server \
  --host localhost \
  --port 26257 \
  --db defaultdb \
  --user root \
  --password mypassword

# Using CockroachDB URI (simpler)
uvx --from git+https://github.com/amineelkouhen/mcp-cockroachdb.git cockroachdb-mcp-server \
  --url postgresql://root@localhost:26257/defaultdb

# SSL connection
uvx --from git+https://github.com/amineelkouhen/mcp-cockroachdb.git cockroachdb-mcp-server \
  --url postgresql://user:pass@cockroach.example.com:26257/defaultdb?sslmode=verify-full&sslrootcert=path/to/ca.crt&sslcert=path/to/client.username.crt&sslkey=path/to/client.username.key

# See all available options
uvx --from git+https://github.com/amineelkouhen/mcp-cockroachdb.git cockroachdb-mcp-server --help
```

**Available CLI Options:**
- `--url` - CockroachDB connection URI (postgresql://user:pass@host:port/db)
- `--host` - CockroachDB hostname 
- `--port` - CockroachDB port (default: 26257)
- `--db` - CockroachDB database name (default: defaultdb)
- `--username` - CockroachDB username (default: root)
- `--password` - CockroachDB password
- `--ssl-mode` - SSL mode - Possible values: disable (default), allow, prefer, require, verify-ca, verify-full
- `--ssl-key` - Path to SSL client key file
- `--ssl-cert` - Path to SSL client certificate file
- `--ssl-ca-cert` - Path to CA (root) certificate file
- `--transport` - MCP transport to use (`stdio` or `http`)
- `--http-host` - HTTP host to bind for streamable HTTP transport
- `--http-port` - HTTP port to bind for streamable HTTP transport
- `--http-path` - HTTP path for streamable HTTP transport (e.g., `/mcp`)
- `--stateless-http` - Enable stateless HTTP mode for horizontal scaling
- `--use-env` - Use environment variables for CockroachDB configuration
- `--read-only` - Refuse all DDL and write tools; recommended for assistant-style deployments
- `--allow-destructive` - Required for `drop_database`, `drop_table`, `drop_index`, `drop_view`. Even with this flag, every destructive call must include `confirm=True`.
- `--version` - Show the server version and exit

### Safety Model

This server is designed for use with an LLM-driven agent, where a prompt-injection attack on the agent could turn into SQL injection or data destruction. Three layers of defense are built in:

1. **Identifier validation.** All database, schema, table, column, index, and view names are validated against `^[A-Za-z_][A-Za-z0-9_]{0,62}$` before being interpolated into SQL.
2. **Values are always parameterized.** Filters, limits, and intervals use asyncpg placeholders (`$1`, `$2`, ...). No user-controlled value is interpolated into SQL.
3. **Server-level policy.**
   - `--read-only` disables every DDL and write-shaped tool (`drop_*`, `create_*`, `execute_query` of INSERT/UPDATE/etc., `bulk_import`, ...).
   - `--allow-destructive` is required for `drop_*` tools. Even then, the caller must pass `confirm=True` per call.
   - DSNs are redacted in responses; passwords never appear in `connect()` results.

Recommended defaults for production assistant-style use: `--read-only`. For administrative agents that need to manage schema, set `--allow-destructive` but never disable the `confirm=True` requirement.

### Logging

Logging is configured via environment variables:

- `MCP_LOG_LEVEL` (default `INFO`) — standard Python logging level (DEBUG/INFO/WARNING/ERROR).
- `MCP_LOG_JSON=1` — emit JSON-structured log lines, recommended when running with `--transport http`.

### Connection pool tuning

- `CRDB_POOL_MIN` (default `1`)
- `CRDB_POOL_MAX` (default `10`)
- `CRDB_COMMAND_TIMEOUT` (default `60` seconds)

### Configuration via Environment Variables

If desired, you can use environment variables. Defaults are provided for all variables.

| Name                 | Description                                                                    | Default Value    |
|----------------------|--------------------------------------------------------------------------------|------------------|
| `CRDB_HOST`          | The host name or address of a CockroachDB node or load balancer.               | 127.0.0.1        |
| `CRDB_PORT`          | The port number of the SQL interface of the CockroachDB node or load balancer. | 26257            |
| `CRDB_DATABASE`      | A database name to use as the current database.                                | defaultdb        |
| `CRDB_USERNAME`      | The SQL user that will own the client session.                                 | root             |
| `CRDB_PWD`           | The user's password.                                                           | None             |
| `CRDB_SSL_MODE`      | Which type of secure connection to use.                                        | disable          |
| `CRDB_SSL_CA_PATH`   | Path to the CA certificate, when sslmode is not `disable`.                     | None             |
| `CRDB_SSL_CERTFILE`  | Path to the client certificate, when sslmode is not `disable`.                 | None             |
| `CRDB_SSL_KEYFILE`   | Path to the client private key, when sslmode is not `disable`.                 | None             |

There are several ways to set environment variables:

1. **Using a `.env` File**:  
Place a `.env` file in your project directory with key-value pairs for each environment variable. Tools like `python-dotenv`, `pipenv`, and `uv` can automatically load these variables when running your application. This is a convenient and secure way to manage configuration, as it keeps sensitive data out of your shell history and version control (if `.env` is in `.gitignore`).
For example, create a `.env` file with the following content from the `.env.example` file provided in the repository:

```bash
cp .env.example .env
```

Then edit the `.env` file to set your CockroachDB configuration:

OR,

2. **Setting Variables in the Shell**:  
You can export environment variables directly in your shell before running your application. For example:

```sh
export CRDB_URL= postgresql://root@127.0.0.1:26257/defaultdb
```

This method is helpful for temporary overrides or quick testing.

## Integrations

Integrating this MCP Server with development frameworks like OpenAI Agents SDK or using tools like Claude Desktop, VS Code, or Augment is described in the following sections.

### OpenAI Agents SDK

Integrate this MCP Server with the OpenAI Agents SDK. Read the [documents](https://openai.github.io/openai-agents-python/mcp/) to learn more about the integration of the SDK with MCP.

Install the Python SDK.

```commandline
pip install openai-agents
```

Configure the OpenAI token:

```commandline
export OPENAI_API_KEY="<openai_token>"
```

And run the [application](./examples/cockroachdb_assistant.py).

```commandline
python3 examples/cockroachdb_assistant.py
```

You can troubleshoot your agent workflows using the [OpenAI dashboard](https://platform.openai.com/traces/).

### Augment

You can configure the CockroachDB MCP Server in Augment by importing the server via JSON:

```json
{
  "mcpServers": {
    "CockroachDB MCP Server": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/amineelkouhen/mcp-cockroachdb.git",
        "cockroachdb-mcp-server",
        "--url",
        "postgresql://root@localhost:26257/defaultdb",
        "--read-only"
      ]
    }
  }
}
```

### Claude Desktop

The simplest way to configure MCP clients is using `uvx`. Add the following JSON to your `claude_desktop_config.json`, remember to provide the full path to `uvx`.

```json
{
    "mcpServers": {
        "cockroach-mcp-server": {
            "type": "stdio",
            "command": "/opt/homebrew/bin/uvx",
            "args": [
                "--from", "git+https://github.com/amineelkouhen/mcp-cockroachdb.git",
                "cockroachdb-mcp-server",
                "--url", "postgresql://localhost:26257/defaultdb"
            ]
        }
    }
}
```

Please follow the prompt and give the details to configure the server and connect to CockroachDB (e.g., using a managed CockroachDB instance).
The procedure will create the proper configuration in the `claude_desktop_config.json` configuration file.

### VS Code with GitHub Copilot

To use the CockroachDB MCP Server with VS Code, you must enable the [agent mode](https://code.visualstudio.com/docs/copilot/chat/chat-agent-mode) tools. Add the following to your `settings.json`:

```json
{
  "chat.agent.enabled": true
}
```

You can start the GitHub desired version of the CockroachDB MCP server using `uvx` by adding the following JSON to your `settings.json`:

```json
"mcp": {
    "servers": {
        "CockroachDB MCP Server": {
        "type": "stdio",
        "command": "uvx", 
        "args": [
            "--from", "git+https://github.com/amineelkouhen/mcp-cockroachdb.git",
            "cockroachdb-mcp-server",
            "--url", "postgresql://root@localhost:26257/defaultdb"
        ]
        },
    }
},
```

Alternatively, you can start the server using `uv` and configure your `mcp.json` or `settings.json`. This is usually desired for development.

```json
{
  "servers": {
    "cockroach": {
      "type": "stdio",
      "command": "<full_path_uv_command>",
      "args": [
        "--directory",
        "<your_mcp_server_directory>",
        "run",
        "src/main.py"
      ],
      "env": {
        "CRDB_HOST": "<your_cockroachdb_hostname>",
        "CRDB_PORT": "<your_cockroachdb_port>",
        "CRDB_DATABASE": "<your_cockroach_database>",
        "CRDB_USERNAME": "<your_cockroachdb_user>",
        "CRDB_PWD": "<your_cockroachdb_password>"
      }
    }
  }
}
```

For more information, see the [VS Code documentation](https://code.visualstudio.com/docs/copilot/chat/mcp-servers).

### Cursor

Read the configuration options [here](#configuration-via-environment-variables) and input your selections with this link:

[![Install MCP Server](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/install-mcp?name=cockroachdb&config=JTdCJTIyY29tbWFuZCUyMiUzQSUyMmRvY2tlciUyMHJ1biUyMC1pJTIwLS1ybSUyMC1lJTIwQ1JEQl9IT1NUJTIwLWUlMjBDUkRCX1BPUlQlMjAtZSUyMENSREJfREFUQUJBU0UlMjAtZSUyMENSREJfVVNFUk5BTUUlMjAtZSUyMENSREJfU1NMX01PREUlMjAtZSUyMENSREJfU1NMX0NBX1BBVEglMjAtZSUyMENSREJfU1NMX0tFWUZJTEUlMjAtZSUyMENSREJfU1NMX0NFUlRGSUxFJTIwLWUlMjBDUkRCX1BXRCUyMG1jcCUyRmNvY2tyb2FjaGRiJTIyJTJDJTIyZW52JTIyJTNBJTdCJTIyQ1JEQl9IT1NUJTIyJTNBJTIyMTI3LjAuMC4xJTIyJTJDJTIyQ1JEQl9QT1JUJTIyJTNBJTIyMjYyNTclMjIlMkMlMjJDUkRCX0RBVEFCQVNFJTIyJTNBJTIyZGVmYXVsdGRiJTIyJTJDJTIyQ1JEQl9VU0VSTkFNRSUyMiUzQSUyMnJvb3QlMjIlMkMlMjJDUkRCX1NTTF9NT0RFJTIyJTNBJTIyZGlzYWJsZSUyMiUyQyUyMkNSREJfU1NMX0NBX1BBVEglMjIlM0ElMjIlMjIlMkMlMjJDUkRCX1NTTF9LRVlGSUxFJTIyJTNBJTIyJTIyJTJDJTIyQ1JEQl9TU0xfQ0VSVEZJTEUlMjIlM0ElMjIlMjIlMkMlMjJDUkRCX1BXRCUyMiUzQSUyMiUyMiU3RCU3RA%3D%3D)

## Testing

### Unit tests

The repository ships with a pytest suite covering the SQL identifier validators, type serializers, DSN parsing, URL helpers, output formatting, and policy gating (read-only mode, destructive-op gating, injection rejection).

```sh
uv sync --extra dev
uv run pytest -v
```

CI runs the same suite on Python 3.12 and 3.13. See `.github/workflows/test.yml`.

### Linting

```sh
uv run ruff check src tests
uv run ruff format --check src tests
```

### MCP Inspector

For interactive debugging of the live server, use the [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector):

```sh
npx @modelcontextprotocol/inspector uv run src/main.py
```

## Contributing
1. Fork the repository
2. Create a new branch (`feature-branch`)
3. Commit your changes
4. Push to your branch and submit a pull request.

## License
This project is licensed under the **MIT License**.

## Quality Badge

<a href="https://glama.ai/mcp/servers/@amineelkouhen/mcp-cockroach">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@amineelkouhen/mcp-cockroach/badge" />
</a>

## Contact
If you have any questions or need support, please feel free to contact us through [GitHub Issues](https://github.com/amineelkouhen/mcp-cockroachdb/issues).
