#!/usr/bin/env bash
# build/external/build_external.sh — build an EXTERNAL app's image (its Dockerfile
# lives in its own repo) and push it to IBM Container Registry, ready for
# deploy_external.sh.
#
#   ./build_external.sh <app> <path-to-app-checkout>            # build here + push (default)
#   MODE=ce ./build_external.sh <app> <path-to-app-checkout>    # build in Code Engine instead
#   NO_PUSH=1 ./build_external.sh <app> <path-to-app-checkout>  # build only
#
#   e.g. ./build_external.sh bharat-core-cuga-agent-app ~/src/CUGA-Voice-RAG-Agent
#
# MODE=local (default, same as build/ce/build_and_push.sh) docker — or podman's
#            docker alias — builds --platform linux/amd64 and pushes. Needs
#            `ibmcloud cr login` (podman: `ibmcloud cr login --client podman`).
#            On Apple Silicon without Rosetta the amd64 build is emulated and slow.
# MODE=ce    Code Engine builds from the local checkout natively on amd64 and pushes
#            to ICR. Only what the checkout's .dockerignore allows is uploaded.
# Either way the checkout's .dockerignore must exclude .env and .git — the script
# refuses to run otherwise.
#
# The tag is the checkout's short git SHA (+ "-dirty" with uncommitted changes),
# so every deploy is traceable and rollback is `deploy_external.sh <app> <old-tag>`.
#
# Env overrides: NAMESPACE (routing_namespace), REGISTRY (icr.io),
#                REGISTRY_SECRET (icr-secret-1), IMAGE_TAG (git SHA)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"     # build/external
APP="${1:-}"; SRC="${2:-}"
[[ -n "$APP" && -n "$SRC" ]] || { echo "usage: $0 <app> <path-to-app-checkout>"; exit 1; }
CONF="$HERE/apps/$APP.conf"
[[ -f "$CONF" ]] || { echo "✗ no config: $CONF"; exit 1; }
# shellcheck source=/dev/null
source "$CONF"
SRC="$(cd "$SRC" && pwd)"
[[ -f "$SRC/$DOCKERFILE" ]] || { echo "✗ $SRC/$DOCKERFILE not found"; exit 1; }

MODE="${MODE:-local}"
NAMESPACE="${NAMESPACE:-routing_namespace}"
REGISTRY="${REGISTRY:-icr.io}"
REGISTRY_SECRET="${REGISTRY_SECRET:-icr-secret-1}"

# ── Tag from the checkout's git state ────────────────────────────────────────
if git -C "$SRC" rev-parse --git-dir >/dev/null 2>&1; then
    SHA="$(git -C "$SRC" rev-parse --short HEAD)"
    [[ -n "$(git -C "$SRC" status --porcelain)" ]] && SHA="${SHA}-dirty"
else
    SHA="nogit-$(date -u +%Y%m%d%H%M%S)"
fi
IMAGE_TAG="${IMAGE_TAG:-$SHA}"
IMAGE="${REGISTRY}/${NAMESPACE}/${IMAGE_NAME}:${IMAGE_TAG}"

# ── Secrets must never leave this machine in the build context ───────────────
IGNORE="$SRC/.dockerignore"
[[ -f "$IGNORE" ]] || { echo "✗ $IGNORE missing — refusing to upload/build the whole checkout"; exit 1; }
for pat in ".env" ".git"; do
    grep -qxF "$pat" "$IGNORE" || { echo "✗ $IGNORE must exclude '$pat'"; exit 1; }
done

echo "════════════════════════════════════════════════════════════════"
echo "  Build external app '$APP'"
echo "    source : $SRC  ($(git -C "$SRC" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?'))"
echo "    image  : $IMAGE"
echo "    mode   : $MODE"
echo "════════════════════════════════════════════════════════════════"
[[ "$IMAGE_TAG" == *-dirty ]] && echo "⚠  uncommitted changes in $SRC are included in this image"

case "$MODE" in
  ce)
    command -v ibmcloud >/dev/null || { echo "✗ ibmcloud CLI not found"; exit 1; }
    ibmcloud ce project current >/dev/null 2>&1 || { echo "✗ no Code Engine project selected"; exit 1; }
    RUN="${APP}-$(date -u +%Y%m%d-%H%M%S)"
    ibmcloud ce buildrun submit \
        --name "$RUN" \
        --build-type local --source "$SRC" \
        --strategy dockerfile --dockerfile "$DOCKERFILE" \
        --image "$IMAGE" --registry-secret "$REGISTRY_SECRET" \
        --size "$BUILD_SIZE" --timeout "$BUILD_TIMEOUT" \
        --wait --wait-timeout "$BUILD_TIMEOUT"
    echo "  logs: ibmcloud ce buildrun logs --name $RUN"
    ;;
  local)
    docker build --platform linux/amd64 -f "$SRC/$DOCKERFILE" -t "$IMAGE" "$SRC"
    if [[ "${NO_PUSH:-0}" == "1" ]]; then
        echo "✓ built $IMAGE (NO_PUSH=1 — not pushed)"; exit 0
    fi
    docker push "$IMAGE"
    ;;
  *) echo "✗ MODE must be 'ce' or 'local'"; exit 1 ;;
esac

echo
echo "✓ built + pushed $IMAGE"
echo "  next: ./deploy_external.sh $APP $IMAGE_TAG"
