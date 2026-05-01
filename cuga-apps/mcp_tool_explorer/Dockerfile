# syntax=docker/dockerfile:1
# =====================================================================
# mcp_tool_explorer/Dockerfile — MCP Tool Explorer UI.
#
# Thin FastAPI service that acts as an MCP client, introspects every
# mcp-* server in the stack, and serves a single-page browser UI.
#
# Build context is the cuga-apps repo root so we can copy both this
# module and apps/_ports.py (the MCP_PORTS registry).
# =====================================================================
FROM python:3.13-slim

WORKDIR /app

COPY mcp_tool_explorer/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Resolves mcp-<name>:<port>/mcp via compose service DNS.
ENV CUGA_IN_DOCKER=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# The explorer imports MCP_PORTS from apps/_ports.py.
COPY apps/__init__.py ./apps/__init__.py
COPY apps/_ports.py   ./apps/_ports.py

COPY mcp_tool_explorer/ ./mcp_tool_explorer/

EXPOSE 28900

CMD ["python", "mcp_tool_explorer/server.py", "--host", "0.0.0.0", "--port", "28900"]
