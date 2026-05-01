#!/usr/bin/env bash
# Start the Chief of Staff stack: cuga adapter + backend + frontend.
# This script is self-contained and does not touch any sibling apps.
#
# Prereqs (your responsibility):
#   - The cuga-apps Python env has cuga.sdk + langchain installed (whatever
#     you use to run the existing apps/* will work).
#   - The MCP servers are already running:
#         python apps/launch.py
#     (or at least the ones listed in MCP_SERVERS env var).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$ROOT/.." && pwd)"
cd "$ROOT"

ADAPTER_PORT="${ADAPTER_PORT:-8000}"
BACKEND_PORT="${BACKEND_PORT:-8765}"
FRONTEND_PORT="${FRONTEND_PORT:-5174}"

# Backend talks to adapter via this URL (same value the discovery scan reads).
export CUGA_URL="${CUGA_URL:-http://localhost:${ADAPTER_PORT}}"

cleanup() {
  jobs -p | xargs -r kill 2>/dev/null || true
}
trap cleanup EXIT

# 1. Cuga adapter — runs from repo root so apps/_mcp_bridge resolves.
(
  cd "$REPO_ROOT"
  exec uvicorn chief_of_staff.adapters.cuga.server:app \
    --host 0.0.0.0 --port "$ADAPTER_PORT"
) &

# 2. Backend
(
  cd backend
  exec uvicorn main:app --host 0.0.0.0 --port "$BACKEND_PORT" --reload
) &

# 3. Frontend
(
  cd frontend
  if [[ ! -d node_modules ]]; then
    npm install
  fi
  exec npm run dev -- --port "$FRONTEND_PORT" --host
) &

wait
