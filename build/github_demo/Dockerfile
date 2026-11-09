# cuga-github-demo: the stock CUGA events image + the GitHub tools + the github_repo_activity roster.
# Nothing in CUGA itself changes; this layer only adds files.
#
#   BASE              a CUGA events image built from cuga-agent (events/deploy/1_build_push_image.sh)
#   /opt/github-mcp-server   the official GitHub MCP server binary (pinned, checksum-verified)
#   /opt/cuga-apps    cuga-apps MCP servers (repo_pulse + the github_official wrapper), run by CUGA's Python
#   /app/github_repo_activity   roster, MCP registry and automations, copied from cuga-agent
ARG BASE=icr.io/routing_namespace/cuga-events:nov4-68894670-precheck
FROM ${BASE}

ARG GITHUB_MCP_VERSION=2.1.0
ARG GITHUB_MCP_SHA256=a442f9db287cea01008bcb55fe6bc0292270301046c3edbd1a8b22d6e4157b2b
RUN set -eux; \
    mkdir -p /opt/github-mcp-server; cd /tmp; \
    curl -fsSL -o gh-mcp.tgz "https://github.com/github/github-mcp-server/releases/download/v${GITHUB_MCP_VERSION}/github-mcp-server_Linux_x86_64.tar.gz"; \
    echo "${GITHUB_MCP_SHA256}  gh-mcp.tgz" | sha256sum -c -; \
    tar -xzf gh-mcp.tgz -C /opt/github-mcp-server github-mcp-server; \
    rm gh-mcp.tgz; \
    /opt/github-mcp-server/github-mcp-server --version

COPY cuga-apps/mcp_servers/  /opt/cuga-apps/mcp_servers/
COPY cuga-apps/apps/__init__.py cuga-apps/apps/_ports.py  /opt/cuga-apps/apps/
COPY roster/  /app/github_repo_activity/

ENV MCP_SERVERS_FILE=/app/github_repo_activity/mcp_servers.yaml
ENV CUGA_SUPERVISOR_ROSTER=/app/github_repo_activity/github_repo_activity.yaml
