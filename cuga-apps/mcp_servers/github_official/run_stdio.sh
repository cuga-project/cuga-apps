#!/bin/sh
# Start the official GitHub MCP server (github/github-mcp-server) as a read-only stdio server.
#
# CUGA's registry passes a fixed env and cannot read secret files, and the server only takes its
# token from GITHUB_PERSONAL_ACCESS_TOKEN. This wrapper reads the token from the tools' secret dir
# (a Code Engine secret mounted as files) and puts it in the env of this one process, so the token
# never sits in CUGA's environment or in a config file.
#
#   MCP_SECRETS_DIR   dir holding GITHUB_TOKEN               (default /run/secrets/demo-tools)
#   GITHUB_TOOLSETS   comma-separated toolsets               (default repos,issues,pull_requests,actions)
#   GITHUB_MCP_BIN    the server binary                      (default /opt/github-mcp-server/github-mcp-server)
set -eu
token_file="${MCP_SECRETS_DIR:-/run/secrets/demo-tools}/GITHUB_TOKEN"
if [ ! -r "$token_file" ]; then
  echo "github_official: no GitHub token at $token_file" >&2
  exit 1
fi
GITHUB_PERSONAL_ACCESS_TOKEN="$(cat "$token_file")"
export GITHUB_PERSONAL_ACCESS_TOKEN
# strip_nulls.py drops the null optional arguments CUGA sends; the Go server refuses them (see that file).
py="${PYTHON:-/app/.venv/bin/python}"; [ -x "$py" ] || py=python3
exec "$py" "$(dirname "$0")/strip_nulls.py" \
  "${GITHUB_MCP_BIN:-/opt/github-mcp-server/github-mcp-server}" stdio \
  --read-only --toolsets "${GITHUB_TOOLSETS:-repos,issues,pull_requests,actions}"
