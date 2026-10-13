#!/usr/bin/env bash
# build/external/deploy_external.sh — deploy an EXTERNAL app (own repo, own image)
# as its own Code Engine app in the cuga-apps project, next to the all-in-one.
#
#   ./deploy_external.sh <app> <image-tag>       # tag printed by build_external.sh
#   ./deploy_external.sh bharat-core-cuga-agent-app 1a2b3c4
#   DRY_RUN=1 ./deploy_external.sh bharat-core-cuga-agent-app 1a2b3c4   # show the secret's keys; write nothing
#
# Same pattern as build/ce/deploy.sh: a CE secret (<CE_APP>-env, assembled from
# the keys listed in apps/<app>.conf) attached with --env-from-secret, then the app is created or
# updated in place, with retries on transient errors. Differences: the port,
# sizing and health probes come from apps/<app>.conf, and images are pinned by
# tag (rollback = re-run with the previous tag).
#
# Prereqs (same one-time setup as build/ce/README.md):
#   ibmcloud login --sso && ibmcloud target -r us-east -g routing
#   ibmcloud ce project select --name ce-project-routing
#   registry pull secret icr-secret-1 exists in the project
#   optional apps/<app>.env for app-only values (copy apps/<app>.env.example; gitignored)
#
# Env overrides: NAMESPACE (routing_namespace), REGISTRY (icr.io),
#                REGISTRY_SECRET (icr-secret-1), ENV_FILE (apps/<app>.env)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"     # build/external
APP="${1:-}"; IMAGE_TAG="${2:-}"
[[ -n "$APP" && -n "$IMAGE_TAG" ]] || { echo "usage: $0 <app> <image-tag>"; exit 1; }
CONF="$HERE/apps/$APP.conf"
[[ -f "$CONF" ]] || { echo "✗ no config: $CONF"; exit 1; }
# shellcheck source=/dev/null
source "$CONF"

NAMESPACE="${NAMESPACE:-routing_namespace}"
REGISTRY="${REGISTRY:-icr.io}"
REGISTRY_SECRET="${REGISTRY_SECRET:-icr-secret-1}"
ENV_FILE="${ENV_FILE:-$HERE/apps/$APP.env}"
IMAGE="${REGISTRY}/${NAMESPACE}/${IMAGE_NAME}:${IMAGE_TAG}"
ENV_SECRET="${CE_APP}-env"
MAX_RETRIES=3
RETRY_BACKOFF=15

# ── Preflight ────────────────────────────────────────────────────────────────
command -v ibmcloud >/dev/null || { echo "✗ ibmcloud CLI not found"; exit 1; }
ibmcloud ce project current >/dev/null 2>&1 || {
    echo "✗ No Code Engine project selected."
    echo "  Run: ibmcloud ce project select --name ce-project-routing"
    exit 1
}
[[ "$IMAGE_TAG" == "latest" ]] && echo "⚠  deploying :latest — prefer the git-SHA tag from build_external.sh"
[[ "$IMAGE_TAG" == *-dirty ]] && echo "⚠  image was built from uncommitted changes"

echo "════════════════════════════════════════════════════════════════"
echo "  Deploy external app '$APP' → Code Engine"
echo "    project  : $(ibmcloud ce project current -o json 2>/dev/null | grep -o '"name":[^,]*' | head -1 | cut -d'"' -f4 || echo '?')"
echo "    app      : $CE_APP"
echo "    image    : $IMAGE"
echo "    sizing   : ${CPU} vCPU / ${MEMORY} / ${EPHEMERAL_STORAGE} disk · scale ${MIN_SCALE}..${MAX_SCALE} · port ${PORT}"
echo "    secret   : '$ENV_SECRET' ← ${SECRET_FROM:+$SECRET_FROM [$SECRET_KEYS] + }${SECRET_SET:+literals + }$( [[ -f "$ENV_FILE" ]] && echo "$ENV_FILE" || echo "(no local env file)")"
echo "════════════════════════════════════════════════════════════════"

# ── 1. Assemble + sync the env secret (least privilege) ─────────────────────
# From apps/<app>.conf: copy ONLY $SECRET_KEYS from $SECRET_FROM, set $SECRET_SET,
# then merge apps/<app>.env if present (app-only values). Values go through a
# mode-600 temp file deleted on exit — never onto a command line, never printed.
[[ "${CE_APP}-env" != "cuga-agent-apps-env" ]] || { echo "✗ refusing to write the production secret"; exit 1; }
umask 077
SECRET_TMP="$(mktemp)"; trap 'rm -f "$SECRET_TMP" "$SECRET_TMP.src"' EXIT
if [[ -n "${SECRET_FROM:-}" ]]; then
    ibmcloud ce secret get --name "$SECRET_FROM" -o json > "$SECRET_TMP.src"
else
    echo '{}' > "$SECRET_TMP.src"
fi
python3 - "$SECRET_TMP" "$SECRET_TMP.src" "${SECRET_KEYS:-}" "${SECRET_SET:-}" "$ENV_FILE" <<'PY'
import json, os, sys
out, src, keys, sets, env_file = sys.argv[1:6]
data = {}
src_data = json.load(open(src)).get("data") or {}
missing = [k for k in keys.split() if k not in src_data]
for k in keys.split():
    if k in src_data:
        data[k] = src_data[k]
for kv in sets.split():
    k, v = kv.split("=", 1); data[k] = v
if os.path.isfile(env_file):
    for line in open(env_file):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1); data[k.strip()] = v
if not data:
    sys.exit("✗ nothing to put in the secret (no SECRET_FROM keys, SECRET_SET or env file)")
with open(out, "w") as f:
    for k, v in data.items():
        f.write(f"{k}={v}\n")
print(f"  secret keys: {sorted(data)}" + (f"  (not in source, skipped: {missing})" if missing else ""))
PY
rm -f "$SECRET_TMP.src"

if [[ "${DRY_RUN:-0}" == "1" ]]; then
    echo "✓ DRY_RUN=1: secret assembled (key names above); nothing created or deployed"
    exit 0
fi

if ibmcloud ce secret get --name "$ENV_SECRET" >/dev/null 2>&1; then
    echo "→ updating secret $ENV_SECRET"
    ibmcloud ce secret update --name "$ENV_SECRET" --from-env-file "$SECRET_TMP" >/dev/null
else
    echo "→ creating secret $ENV_SECRET"
    ibmcloud ce secret create --name "$ENV_SECRET" --from-env-file "$SECRET_TMP" >/dev/null
fi
rm -f "$SECRET_TMP"
echo "✓ env secret synced"

# ── 2. Create or update the app ───────────────────────────────────────────────
common=(
    --name "$CE_APP"
    --image "$IMAGE"
    --registry-secret "$REGISTRY_SECRET"
    --port "$PORT"
    --cpu "$CPU" --memory "$MEMORY" --ephemeral-storage "$EPHEMERAL_STORAGE"
    --min-scale "$MIN_SCALE" --max-scale "$MAX_SCALE"
    --concurrency "$CONCURRENCY"
    --request-timeout "$REQUEST_TIMEOUT"
    --env-from-secret "$ENV_SECRET"
    # Readiness: no traffic until the index is loaded.
    --probe-ready type=http --probe-ready path="$PROBE_READY_PATH"
    --probe-ready interval=10 --probe-ready timeout=10 --probe-ready failure-threshold=10
    # Liveness: restart a hung instance. Code Engine caps initial-delay at 10 s and
    # failure-threshold at 10, so the grace before a restart is 10 + 10 × 10 s ≈ 110 s
    # (startup is ~10 s on amd64).
    --probe-live type=http --probe-live path="$PROBE_LIVE_PATH"
    --probe-live initial-delay=10 --probe-live interval=10 --probe-live timeout=5
    --probe-live failure-threshold=10
)

app_exists() { ibmcloud ce app get --name "$CE_APP" >/dev/null 2>&1; }

deploy_once() {
    if app_exists; then
        echo "→ updating app $CE_APP"
        ibmcloud ce app update "${common[@]}"
    else
        echo "→ creating app $CE_APP"
        ibmcloud ce app create "${common[@]}" --visibility public
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

# ── 3. Report ────────────────────────────────────────────────────────────────
URL="$(ibmcloud ce app get --name "$CE_APP" --output url 2>/dev/null || true)"
echo
echo "✓ deployed $CE_APP @ $IMAGE_TAG"
if [[ -n "$URL" ]]; then
    echo "  URL     : $URL"
    echo "  ready   : $URL$PROBE_READY_PATH"
    echo "  logs    : ibmcloud ce app logs --name $CE_APP --follow"
    echo "  rollback: $0 $APP <previous-tag>"
fi
echo "  UI link : the service list in cuga-apps/ui/src/data/bharatServices.ts"
