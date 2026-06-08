#!/usr/bin/env bash
# build/ce/build_and_push.sh — build the ALL-IN-ONE image and push it to IBM
# Container Registry (ICR), ready for a single Code Engine deployment.
#
# The all-in-one image (build/Dockerfile, context = repo root) bundles the
# umbrella UI + every ship-ready app + the 5 MCP servers + the stats dashboard
# behind one nginx port (8080). One image → one CE service.
#
#   ./build_and_push.sh                 # build + push icr.io/<ns>/cuga-allinone:latest
#   NAMESPACE=myns IMAGE_TAG=v3 ./build_and_push.sh
#   ./build_and_push.sh --no-push       # build only (local image)
#
# Env overrides:
#   NAMESPACE              ICR namespace        (default: routing_namespace)
#   IMAGE_TAG              image tag            (default: latest)
#   REGISTRY              registry host        (default: icr.io)
#   DOCKER_BUILD_NETWORK  docker build network (default: host — needed where the
#                         container's default bridge can't resolve DNS; set to
#                         "default" on hosts where host networking is unavailable)
set -euo pipefail

# ── Locate the repo root (build context) ─────────────────────────────────────
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # build/ce
REPO_ROOT="$(cd "$HERE/../.." && pwd)"                   # repo root
DOCKERFILE="$REPO_ROOT/build/Dockerfile"

NAMESPACE="${NAMESPACE:-routing_namespace}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
REGISTRY="${REGISTRY:-icr.io}"
DOCKER_BUILD_NETWORK="${DOCKER_BUILD_NETWORK:-host}"
IMAGE="${REGISTRY}/${NAMESPACE}/cuga-allinone:${IMAGE_TAG}"

PUSH=1
[[ "${1:-}" == "--no-push" ]] && PUSH=0

echo "════════════════════════════════════════════════════════════════"
echo "  Build all-in-one image"
echo "    image      : $IMAGE"
echo "    dockerfile : build/Dockerfile  (context: repo root)"
echo "    network    : $DOCKER_BUILD_NETWORK"
echo "    push       : $([[ $PUSH == 1 ]] && echo yes || echo 'no (--no-push)')"
echo "════════════════════════════════════════════════════════════════"

# CE only runs linux/amd64. Host networking lets apt/npm/pip resolve DNS on
# hosts whose docker bridge inherits an unreachable resolver.
docker build \
    --platform linux/amd64 \
    --network="$DOCKER_BUILD_NETWORK" \
    -f "$DOCKERFILE" \
    -t "$IMAGE" \
    "$REPO_ROOT"

echo "✓ built $IMAGE"

if [[ $PUSH == 1 ]]; then
    echo "→ pushing to $REGISTRY (run 'ibmcloud cr login' first if this fails)…"
    docker push "$IMAGE"
    echo "✓ pushed $IMAGE"
    echo
    echo "Next: ./deploy.sh    (creates/updates the CE app from this image)"
fi
