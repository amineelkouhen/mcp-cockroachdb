FROM python:3.13-slim
RUN pip install --upgrade uv

WORKDIR /app
COPY . /app

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

# Use CLI entry point to properly handle command line arguments
ENTRYPOINT ["uv", "run", "cockroachdb-mcp-server"]
# Default to stdio transport, can be overridden with K8s args
CMD []
