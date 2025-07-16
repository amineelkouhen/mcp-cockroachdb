# CockroachDB MCP Server
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.13%2B-blue)](https://www.python.org/downloads/)
[![smithery badge](https://smithery.ai/badge/@amineelkouhen/mcp-cockroachdb)](https://smithery.ai/server/@amineelkouhen/mcp-cockroachdb)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-blue)](https://mcp.so/server/cockroachdb-mcp-server/cockroachdb)

## Overview

The CockroachDB MCP Server is a **natural language interface** designed for LLMs and agentic applications to manage, monitor, and query data in CockroachDB. It integrates seamlessly with **MCP (Model Content Protocol)** clients, such as Claude Desktop or Cursor, enabling AI-driven workflows to interact directly with your database. 

## Table of Contents
- [Overview](#overview)
- [Features](#features)
- [Tools](#tools)
  - [Cluster Management](#cluster-management)
  - [Database Management](#database-management)
  - [Table Management](#table-management)
  - [Query Engine](#query-engine)
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
- [Contact](#contact)

## Features
- **Natural Language Queries**: Enables AI agents to query and create transactions using natural language, supporting complex workflows.
- **Search & Filtering**: Supports efficient data retrieval and searching in CockroachDB.
- **Cluster Management**: Check and monitor the CockroachDB cluster status, including node health and replication.
- **Database Management**: Perform all operations related to databases, such as creation, deletion, and configuration.
- **Table Management**: Handle tables, indexes, and schemas for flexible data modeling.
- **Seamless MCP Integration**: Works with any **MCP client** for smooth communication.
- **Scalable & Lightweight**: Designed for **high-performance** data operations.

## Tools

The CockroachDB MCP Server Server provides tools to manage the data stored in CockroachDB. 

![architecture](https://github.com/user-attachments/assets/36a121d9-48b7-4840-9317-002a38441b8d)

The tools are organized into four main categories:

### Cluster Management

Purpose:
Provides tools for monitoring and managing CockroachDB clusters.

Summary:
- Get cluster health and node status.
- Show currently running queries.
- Analyze query performance statistics.
- Retrieve replication and distribution status for tables or the whole database.

### Database Management

Purpose:
Handles database-level operations and connection management.

Summary:
- Connect to a CockroachDB database.
- List, create, drop, and switch databases.
- Get connection status and active sessions.
- Retrieve database settings.

### Table Management

Purpose:
Provides tools for managing tables, indexes, views, and schema relationships in CockroachDB.

Summary:
- Create, drop, and describe tables and views.
- Bulk import data into tables.
- Manage indexes (create/drop).
- List tables, views, and table relationships.
- Analyze schema structure and metadata.

### Query Engine

Purpose:
Executes and manages SQL queries and transactions.

Summary:
- Execute SQL queries with formatting options (JSON, CSV, table).
- Run multi-statement transactions.
- Explain query plans for optimization.
- Track and retrieve query history.

## Installation

The CockroachDB MCP Server supports the `stdio` [transport](https://modelcontextprotocol.io/docs/concepts/transports#standard-input%2Foutput-stdio). Support for the `streamable-http` transport will be added in a future release.

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

To use the [CockroachDB MCP Docker](https://hub.docker.com/r/mcp/cockroachdb) image, just replace your image name (`mcp-cockroachdb` in the example above) with `mcp/cockroachdb`.

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
- `--user` - CockroachDB username
- `--password` - CockroachDB password
- `--ssl-mode` - SSL mode - Possible values: require, verify-ca, verify-full, disable (default)
- `--ssl-key` - Path to SSL Client key file
- `--ssl-cert` - Path to SSL Client certificate file
- `--ssl-ca-cert` - Path to CA (Root) certificate file'

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
        "git+https://github.com/cockroachdb/mcp-cockroachdb.git",
        "cockroachdb-mcp-server",
        "--url",
        "postgresql://root@localhost:26257/defaultdb"
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

If you'd like to test the [CockroachDB MCP Server](https://smithery.ai/server/@amineelkouhen/mcp-cockroachdb) via Smithery, you can configure Claude Desktop automatically:

```bash
npx -y @smithery/cli install @amineelkouhen/mcp-cockroachdb --client claude
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

You can use the [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector) for visual debugging of this MCP Server.

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

## Contact
If you have any questions or need support, please feel free to contact us through [GitHub Issues](https://github.com/amineelkouhen/mcp-cockroachdb/issues).
