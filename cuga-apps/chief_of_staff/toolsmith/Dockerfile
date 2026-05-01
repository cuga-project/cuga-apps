# syntax=docker/dockerfile:1
# =====================================================================
# chief_of_staff/toolsmith/Dockerfile
#
# The Toolsmith service — durable LangGraph ReAct agent that builds tools.
# Build context must be cuga-apps/ (one level up) so we can read-only
# consume apps/_llm.py + chief_of_staff/backend/acquisition/*.
# =====================================================================
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Reuse the parent stack's deps (cuga, langchain, langgraph, etc.) plus
# Toolsmith-specific extras (anthropic, langgraph version pinning).
COPY requirements.apps.txt ./
COPY chief_of_staff/toolsmith/requirements.txt ./toolsmith-extras.txt
RUN pip install --no-cache-dir -r requirements.apps.txt && \
    pip install --no-cache-dir -r toolsmith-extras.txt

ENV CUGA_IN_DOCKER=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app:/app/apps:/app/chief_of_staff/backend

# Read-only: provider plumbing + the existing acquisition/* logic that
# Toolsmith reuses (catalog, openapi source, probe harness, vault).
COPY apps/_mcp_bridge.py apps/_llm.py apps/_ports.py apps/__init__.py ./apps/
COPY chief_of_staff/backend/__init__.py ./chief_of_staff/backend/
COPY chief_of_staff/backend/acquisition/ ./chief_of_staff/backend/acquisition/
COPY chief_of_staff/__init__.py ./chief_of_staff/

# The Toolsmith service itself.
COPY chief_of_staff/toolsmith/ ./chief_of_staff/toolsmith/

# Persistent artifact store mount point.
RUN mkdir -p /app/chief_of_staff/data/tools

EXPOSE 8001

CMD ["uvicorn", "chief_of_staff.toolsmith.server:app", "--host", "0.0.0.0", "--port", "8001"]
