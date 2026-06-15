FROM python:3.13-slim AS base

# Install uv from the official source
RUN pip install --no-cache-dir --upgrade uv

# Create non-root user
RUN groupadd --gid 1000 mcp \
 && useradd --uid 1000 --gid 1000 --shell /bin/bash --create-home mcp

WORKDIR /app

# Copy project files
COPY --chown=mcp:mcp . /app

# Install dependencies (locked) into a virtualenv owned by the mcp user
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

# Drop privileges
USER mcp

# Healthcheck applies when running with --transport http
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request, os, sys; \
url = f\"http://127.0.0.1:{os.environ.get('MCP_HEALTH_PORT', '8000')}/health\"; \
sys.exit(0 if urllib.request.urlopen(url, timeout=5).status == 200 else 1)" \
  || exit 0

ENTRYPOINT ["uv", "run", "cockroachdb-mcp-server"]
CMD []
