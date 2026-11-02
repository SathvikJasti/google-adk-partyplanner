# One image for all four services; pick the service with the command:
#   python -m agents | budget_agent | compliance_agent | mcp_server
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app

# Dependencies first, so code changes don't invalidate this layer.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY common ./common
COPY agents ./agents
COPY budget_agent ./budget_agent
COPY compliance_agent ./compliance_agent
COPY mcp_server ./mcp_server

ENV PATH="/app/.venv/bin:$PATH" BIND_HOST=0.0.0.0
RUN useradd --create-home app && chown -R app /app
USER app

# SERVICE picks the module (agents, budget_agent, compliance_agent, mcp_server);
# a container command/args set on the platform overrides this.
ENV SERVICE=agents
CMD ["sh", "-c", "exec python -m ${SERVICE}"]
