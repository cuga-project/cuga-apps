#!/usr/bin/env bash
# build/ce/deploy.sh — deploy the ALL-IN-ONE image as ONE Code Engine service.
#
# One image, one CE application, one public URL on port 8080. The umbrella UI,
# all ship-ready apps, the 5 MCP servers, and the stats dashboard all run inside
# this single instance (CUGA_TARGET=local; MCP servers on loopback).
#
#   ./deploy.sh                      # create or update the CE app
#   APP_NAME=my-cuga ./deploy.sh
#
# Env overrides:
#   NAMESPACE        ICR namespace        (default: routing_namespace)
#   IMAGE_TAG        image tag            (default: latest)
#   IMAGE_NAME      image/repo name      (default: cuga-agent-apps)
#   REGISTRY        registry host        (default: icr.io)
#   APP_NAME         CE app name          (default: cuga-agent-apps)
#   REGISTRY_SECRET  CE registry secret   (default: icr-secret-1)
#   ENV_FILE         env file to load     (default: ../.env  i.e. build/.env)
#   CPU / MEMORY     CE sizing            (default: 12 / 48G)
#   EPHEMERAL_STORAGE  disk per instance  (default: 5G — must be ≤ MEMORY)
#   MIN_SCALE / MAX_SCALE                 (default: 1 / 1 — single instance)
#
# Prereqs (one-time — see ./README.md):
#   ibmcloud login --sso && ibmcloud target -r <region> -g <resource-group>
#   ibmcloud ce project select --name <project>
#   ibmcloud ce registry create --name icr-secret-1 --server icr.io \
#       --username iamapikey --password <icr-apikey>
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # build/ce
BUILD_DIR="$(cd "$HERE/.." && pwd)"                      # build/

NAMESPACE="${NAMESPACE:-routing_namespace}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
IMAGE_NAME="${IMAGE_NAME:-cuga-agent-apps}"
REGISTRY="${REGISTRY:-icr.io}"
APP_NAME="${APP_NAME:-cuga-agent-apps}"
REGISTRY_SECRET="${REGISTRY_SECRET:-icr-secret-1}"
ENV_FILE="${ENV_FILE:-$BUILD_DIR/.env}"
CPU="${CPU:-12}"
MEMORY="${MEMORY:-48G}"
EPHEMERAL_STORAGE="${EPHEMERAL_STORAGE:-5G}"
MIN_SCALE="${MIN_SCALE:-1}"
MAX_SCALE="${MAX_SCALE:-1}"
IMAGE="${REGISTRY}/${NAMESPACE}/${IMAGE_NAME}:${IMAGE_TAG}"
ENV_SECRET="${APP_NAME}-env"

MAX_RETRIES=3
RETRY_BACKOFF=15

# ── Preflight ────────────────────────────────────────────────────────────────
command -v ibmcloud >/dev/null || { echo "✗ ibmcloud CLI not found"; exit 1; }
ibmcloud ce project current >/dev/null 2>&1 || {
    echo "✗ No Code Engine project selected."
    echo "  Run: ibmcloud ce project select --name <project>"
    exit 1
}
[[ -f "$ENV_FILE" ]] || { echo "✗ env file not found: $ENV_FILE"; exit 1; }

echo "════════════════════════════════════════════════════════════════"
echo "  Deploy all-in-one → Code Engine (single service)"
echo "    project   : $(ibmcloud ce project current -o json 2>/dev/null | grep -o '\"name\":[^,]*' | head -1 | cut -d'\"' -f4 || echo '?')"
echo "    app       : $APP_NAME"
echo "    image     : $IMAGE"
echo "    sizing    : ${CPU} vCPU / ${MEMORY} / ${EPHEMERAL_STORAGE} disk · scale ${MIN_SCALE}..${MAX_SCALE}"
echo "    env from  : $ENV_FILE  → secret '$ENV_SECRET'"
echo "════════════════════════════════════════════════════════════════"

# ── 1. Sync the env secret from the env file ─────────────────────────────────
# Build --from-literal args from KEY=VALUE lines (skip blanks/comments). The
# values live in the CE secret, NOT on the app's command line / spec.
literals=()
while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"                                   # strip CR
    [[ -z "$line" || "$line" == \#* ]] && continue         # skip blank/comment
    [[ "$line" != *=* ]] && continue                       # must be KEY=VALUE
    key="${line%%=*}"; val="${line#*=}"
    key="$(echo "$key" | xargs)"                           # trim
    [[ -z "$key" ]] && continue
    literals+=( "--from-literal" "${key}=${val}" )
done < "$ENV_FILE"
# CUGA_TARGET must stay 'local' — the MCP servers run in-container.
literals+=( "--from-literal" "CUGA_TARGET=local" )

if ibmcloud ce secret get --name "$ENV_SECRET" >/dev/null 2>&1; then
    echo "→ updating secret $ENV_SECRET"
    ibmcloud ce secret update --name "$ENV_SECRET" "${literals[@]}" >/dev/null
else
    echo "→ creating secret $ENV_SECRET"
    ibmcloud ce secret create --name "$ENV_SECRET" "${literals[@]}" >/dev/null
fi
echo "✓ env secret synced"

# ── 2. Create or update the CE application (with retry on transient errors) ───
app_exists() { ibmcloud ce app get --name "$APP_NAME" >/dev/null 2>&1; }

deploy_once() {
    if app_exists; then
        echo "→ updating app $APP_NAME"
        ibmcloud ce app update \
            --name "$APP_NAME" \
            --image "$IMAGE" \
            --registry-secret "$REGISTRY_SECRET" \
            --port 8080 \
            --cpu "$CPU" --memory "$MEMORY" --ephemeral-storage "$EPHEMERAL_STORAGE" \
            --min-scale "$MIN_SCALE" --max-scale "$MAX_SCALE" \
            --env-from-secret "$ENV_SECRET"
    else
        echo "→ creating app $APP_NAME"
        ibmcloud ce app create \
            --name "$APP_NAME" \
            --image "$IMAGE" \
            --registry-secret "$REGISTRY_SECRET" \
            --port 8080 \
            --cpu "$CPU" --memory "$MEMORY" --ephemeral-storage "$EPHEMERAL_STORAGE" \
            --min-scale "$MIN_SCALE" --max-scale "$MAX_SCALE" \
            --env-from-secret "$ENV_SECRET"
    fi
}

attempt=1
while true; do
    if out="$(deploy_once 2>&1)"; then
        echo "$out"
        break
    fi
    echo "$out"
    if echo "$out" | grep -qiE "EOF|i/o timeout|TLS handshake|connection reset|temporarily unavailable|503"; then
        if (( attempt < MAX_RETRIES )); then
            echo "⟳ transient error — retry $attempt/$((MAX_RETRIES-1)) in ${RETRY_BACKOFF}s…"
            sleep "$RETRY_BACKOFF"; (( attempt++ )); continue
        fi
    fi
    echo "✗ deploy failed"; exit 1
done

# ── 3. Report URL ────────────────────────────────────────────────────────────
URL="$(ibmcloud ce app get --name "$APP_NAME" --output url 2>/dev/null || true)"
echo
echo "✓ deployed."
[[ -n "$URL" ]] && {
    echo "  URL      : $URL"
    echo "  health   : $URL/healthz"
    echo "  stats    : $URL/a/usage-collector/"
}
