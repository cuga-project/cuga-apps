#!/usr/bin/env bash
# =====================================================================
# deploy_mcp.sh — deploy the cuga-apps MCP servers + tool explorer to
# IBM Cloud Code Engine.
#
# (Renamed from deploy.sh — sibling of deploy_apps.sh / deploy_ui.sh.)
#
# Idempotent. Retries on transient registry pull errors. Continues past
# per-service failures and reports a summary at the end.
#
# Prerequisites (one-time, NOT done by this script):
#   - ibmcloud login + target region/RG
#   - ibmcloud ce project select --name <your-project>
#   - ibmcloud cr region-set + cr namespace-add + cr login
#   - shared MCP image already built + pushed to ICR
#     (mcp-tool-explorer image too, if you'll deploy the explorer)
#   - CE secrets `icr-secret-1` (registry pull) and `app-env` (env file) created
#
# Usage:
#   ./deploy_mcp.sh                       # all 7 MCPs + tool-explorer
#   ./deploy_mcp.sh web knowledge geo     # subset of MCPs (no explorer)
#   ./deploy_mcp.sh tool-explorer         # just the explorer (assumes MCPs deployed)
#   ./deploy_mcp.sh web tool-explorer     # one MCP plus the explorer
#
# Override defaults via env vars:
#   REGION    (default: us-south)
#   NAMESPACE (default: cuga-apps)
#   IMAGE_TAG (default: latest)
# =====================================================================

set -euo pipefail

REGION="${REGION:-us-south}"
NAMESPACE="routing_namespace"
IMAGE_TAG="${IMAGE_TAG:-latest}"
REG="icr.io/${NAMESPACE}"
IMAGE="${REG}/mcp:${IMAGE_TAG}"
MAX_RETRIES=3
RETRY_BACKOFF_SECONDS=15

# Where to mount the app-env secret inside each container.
# Must NOT be under /run/secrets — Kubernetes mounts its serviceaccount
# token at /var/run/secrets/kubernetes.io/serviceaccount, and /run/secrets
# becomes read-only once we mount our own secret there, which then blocks
# the kube mount and the container fails to start.
SECRET_MOUNT_DIR="${SECRET_MOUNT_DIR:-/etc/cuga-secrets}"

declare -A MCP_PORTS=(
  [web]=29100  [knowledge]=29101  [geo]=29102  [finance]=29103
  [code]=29104 [local]=29105      [text]=29106
)

EXPLORER_TOKEN="tool-explorer"
EXPLORER_PORT=28900
EXPLORER_IMAGE="${REG}/mcp-tool-explorer:${IMAGE_TAG}"
EXPLORER_APP_NAME="cuga-apps-mcp-tool-explorer"

# Decide what to deploy.
#   No args  → all 7 MCPs + explorer.
#   Args     → exactly the items listed (which may include `tool-explorer`).
SERVERS=()
DEPLOY_EXPLORER=false
if [[ $# -gt 0 ]]; then
  for arg in "$@"; do
    if [[ "$arg" == "$EXPLORER_TOKEN" ]]; then
      DEPLOY_EXPLORER=true
    else
      SERVERS+=("$arg")
    fi
  done
else
  SERVERS=(web knowledge geo finance code local text)
  DEPLOY_EXPLORER=true
fi

# Validate any user-supplied MCP names against the known set.
for name in "${SERVERS[@]}"; do
  if [[ -z "${MCP_PORTS[$name]:-}" ]]; then
    echo "ERROR: unknown target '$name'. Known MCPs: ${!MCP_PORTS[*]} (or '$EXPLORER_TOKEN')" >&2
    exit 1
  fi
done

# Sanity check the prerequisites that block every deploy.
require_cli() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: $1 not on PATH" >&2; exit 1; }; }
require_cli ibmcloud

if ! ibmcloud ce project current >/dev/null 2>&1; then
  echo "ERROR: no Code Engine project selected. Run:" >&2
  echo "  ibmcloud ce project select --name <your-project>" >&2
  exit 1
fi

if ! ibmcloud ce secret get --name app-env >/dev/null 2>&1; then
  echo "ERROR: CE secret 'app-env' not found in this project." >&2
  exit 1
fi

if ! ibmcloud ce registry get --name icr-secret-1 >/dev/null 2>&1; then
  echo "ERROR: CE registry-secret 'icr-secret' not found in this project." >&2
  exit 1
fi

echo "─────────────────────────────────────────────────────────────"
echo "  Project:  $(ibmcloud ce project current --output json | python3 -c 'import sys,json; print(json.load(sys.stdin).get("name","?"))' 2>/dev/null || echo '?')"
echo "  MCP image: $IMAGE"
echo "  MCPs:     ${SERVERS[*]:-<none>}"
echo "  Explorer: $($DEPLOY_EXPLORER && echo "yes ($EXPLORER_IMAGE)" || echo "no")"
echo "─────────────────────────────────────────────────────────────"
echo

# ── Deploy one MCP server, with retry on transient registry errors ─────
deploy_mcp() {
  local name=$1
  local port=$2
  local app_name="cuga-apps-mcp-$name"

  # Decide create-or-update based on whether the app already exists.
  local action="create"
  if ibmcloud ce app get --name "$app_name" >/dev/null 2>&1; then
    action="update"
  fi

  for attempt in $(seq 1 $MAX_RETRIES); do
    echo "── [$action] $app_name (port $port) — attempt $attempt/$MAX_RETRIES ──"

    local rc=0
    local logfile
    logfile=$(mktemp -t "ce-deploy-${name}-XXXXXX.log")

    if [[ "$action" == "create" ]]; then
      # Run via /entrypoint.sh (not python directly) so the secret file
      # at $CUGA_SECRETS_FILE actually gets sourced before python starts.
      # Passing --command python overrides the Docker ENTRYPOINT and skips
      # the source step — same bug as the cuga-apps deploy_apps.sh.
      ibmcloud ce app create \
        --name "$app_name" \
        --image "$IMAGE" \
        --registry-secret icr-secret-1 \
        --port "$port" \
        --command /entrypoint.sh \
        --argument python --argument -m --argument "mcp_servers.$name.server" \
        --mount-secret "$SECRET_MOUNT_DIR=app-env" \
        --env "CUGA_SECRETS_FILE=$SECRET_MOUNT_DIR/app.env" \
        --cpu 1 --memory 2G \
        --min-scale 1 --max-scale 1 \
        2>&1 | tee "$logfile" || rc=${PIPESTATUS[0]}
    else
      # Update existing app: roll the image (and --force a re-pull in case
      # of transient pull failures from a prior attempt).
      ibmcloud ce app update \
        --name "$app_name" \
        --image "$IMAGE" \
        --force \
        2>&1 | tee "$logfile" || rc=${PIPESTATUS[0]}
    fi

    if [[ $rc -eq 0 ]]; then
      rm -f "$logfile"
      return 0
    fi

    # Decide retry vs bail: only retry on transient registry/network errors.
    if grep -qE "EOF|i/o timeout|TLS handshake|connection reset|temporarily unavailable|503" "$logfile"; then
      echo "    transient error detected — sleeping ${RETRY_BACKOFF_SECONDS}s before retry"
      rm -f "$logfile"
      sleep "$RETRY_BACKOFF_SECONDS"
      # If we were creating and it half-landed, the next attempt should update.
      if ibmcloud ce app get --name "$app_name" >/dev/null 2>&1; then
        action="update"
      fi
      continue
    fi

    echo "    permanent error — not retrying. Last log lines:"
    tail -20 "$logfile" | sed 's/^/      /'
    rm -f "$logfile"
    return $rc
  done

  echo "    exhausted $MAX_RETRIES retries"
  return 1
}

# ── Deploy mcp-tool-explorer ───────────────────────────────────────────
# Same retry shape as deploy_mcp. Differences:
#   - own image (no shared MCP image)
#   - no secret mount (the explorer doesn't need app.env)
#   - per-MCP URLs as --env flags so the explorer can reach the deployed
#     MCP servers (locally it relies on docker compose service DNS, which
#     CE doesn't have)
deploy_tool_explorer() {
  local app_name="$EXPLORER_APP_NAME"
  local image="$EXPLORER_IMAGE"

  # Build --env flags pointing at the deployed MCPs. Skip any that aren't
  # up yet; the explorer's UI will show those as offline.
  local -a env_args=()
  local missing=()
  for name in web knowledge geo finance code local text; do
    local url
    url=$(ibmcloud ce app get --name "cuga-apps-mcp-$name" --output url 2>/dev/null || true)
    if [[ -n "$url" ]]; then
      env_args+=(--env "MCP_${name^^}_URL=$url/mcp")
    else
      missing+=("$name")
    fi
  done

  if [[ ${#env_args[@]} -eq 0 ]]; then
    echo "ERROR: no MCP server URLs found — deploy at least one MCP before the explorer." >&2
    return 1
  fi
  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "  WARN: explorer will start without URLs for: ${missing[*]}"
  fi

  # Decide create-or-update.
  local action="create"
  if ibmcloud ce app get --name "$app_name" >/dev/null 2>&1; then
    action="update"
  fi

  for attempt in $(seq 1 $MAX_RETRIES); do
    echo "── [$action] $app_name (port $EXPLORER_PORT) — attempt $attempt/$MAX_RETRIES ──"

    local rc=0
    local logfile
    logfile=$(mktemp -t "ce-deploy-explorer-XXXXXX.log")

    if [[ "$action" == "create" ]]; then
      # CE accepts only specific cpu/memory pairs. At 1 vCPU the minimum
      # memory is 2G; for a thin proxy 0.5 vCPU + 1G is the smallest valid
      # combo. See https://cloud.ibm.com/docs/codeengine?topic=codeengine-mem-cpu-combo
      ibmcloud ce app create \
        --name "$app_name" \
        --image "$image" \
        --registry-secret icr-secret-1 \
        --port "$EXPLORER_PORT" \
        "${env_args[@]}" \
        --cpu 0.5 --memory 1G \
        --min-scale 0 --max-scale 1 \
        2>&1 | tee "$logfile" || rc=${PIPESTATUS[0]}
    else
      # Re-apply env vars on update so URL changes (e.g. MCPs redeployed
      # to a different hash) get picked up.
      ibmcloud ce app update \
        --name "$app_name" \
        --image "$image" \
        --force \
        "${env_args[@]}" \
        2>&1 | tee "$logfile" || rc=${PIPESTATUS[0]}
    fi

    if [[ $rc -eq 0 ]]; then
      rm -f "$logfile"
      return 0
    fi

    if grep -qE "EOF|i/o timeout|TLS handshake|connection reset|temporarily unavailable|503" "$logfile"; then
      echo "    transient error detected — sleeping ${RETRY_BACKOFF_SECONDS}s before retry"
      rm -f "$logfile"
      sleep "$RETRY_BACKOFF_SECONDS"
      if ibmcloud ce app get --name "$app_name" >/dev/null 2>&1; then
        action="update"
      fi
      continue
    fi

    echo "    permanent error — not retrying. Last log lines:"
    tail -20 "$logfile" | sed 's/^/      /'
    rm -f "$logfile"
    return $rc
  done

  echo "    exhausted $MAX_RETRIES retries"
  return 1
}

# ── Main loop ──────────────────────────────────────────────────────────
declare -a SUCCEEDED=()
declare -a FAILED=()

for name in "${SERVERS[@]}"; do
  port=${MCP_PORTS[$name]}
  if deploy_mcp "$name" "$port"; then
    SUCCEEDED+=("$name")
  else
    FAILED+=("$name")
  fi
  echo
done

if $DEPLOY_EXPLORER; then
  if deploy_tool_explorer; then
    SUCCEEDED+=("$EXPLORER_TOKEN")
  else
    FAILED+=("$EXPLORER_TOKEN")
  fi
  echo
fi

# ── Summary ────────────────────────────────────────────────────────────
echo "─────────────────────────────────────────────────────────────"
echo "  Summary"
echo "─────────────────────────────────────────────────────────────"
echo "  Succeeded (${#SUCCEEDED[@]}): ${SUCCEEDED[*]:-<none>}"
echo "  Failed    (${#FAILED[@]}): ${FAILED[*]:-<none>}"
echo

if [[ ${#FAILED[@]} -gt 0 ]]; then
  echo "  Diagnose any failure with:"
  for name in "${FAILED[@]}"; do
    if [[ "$name" == "$EXPLORER_TOKEN" ]]; then
      echo "    ibmcloud ce app events --name $EXPLORER_APP_NAME | tail -30"
      echo "    ibmcloud ce app logs   --name $EXPLORER_APP_NAME --tail 100"
    else
      echo "    ibmcloud ce app events --name cuga-apps-mcp-$name | tail -30"
      echo "    ibmcloud ce app logs   --name cuga-apps-mcp-$name --tail 100"
    fi
  done
  exit 1
fi

echo "  Public URLs:"
for name in "${SUCCEEDED[@]}"; do
  if [[ "$name" == "$EXPLORER_TOKEN" ]]; then
    url=$(ibmcloud ce app get --name "$EXPLORER_APP_NAME" --output url 2>/dev/null || echo '?')
    printf "    TOOL_EXPLORER_URL=%s\n" "$url"
  else
    url=$(ibmcloud ce app get --name "cuga-apps-mcp-$name" --output url 2>/dev/null || echo '?')
    printf "    MCP_%s_URL=%s/mcp\n" "${name^^}" "$url"
  fi
done
