#!/usr/bin/env bash
# build/ce/build_and_push.sh — build the ALL-IN-ONE image and push it to IBM
# Container Registry (ICR), ready for a single Code Engine deployment.
#
# The all-in-one image (build/Dockerfile, context = repo root) bundles the
# umbrella UI + every ship-ready app + the 5 MCP servers + the stats dashboard
# behind one nginx port (8080). One image → one CE service.
#
#   ./build_and_push.sh                 # build + push icr.io/<ns>/cuga-agent-apps:latest
#   NAMESPACE=myns IMAGE_TAG=v3 ./build_and_push.sh
#   ./build_and_push.sh --no-push       # build only (local image)
#
# Env overrides:
#   NAMESPACE              ICR namespace        (default: routing_namespace)
#   IMAGE_TAG              image tag            (default: latest)
#   IMAGE_NAME            image/repo name      (default: cuga-agent-apps)
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
IMAGE_NAME="${IMAGE_NAME:-cuga-agent-apps}"
REGISTRY="${REGISTRY:-icr.io}"
DOCKER_BUILD_NETWORK="${DOCKER_BUILD_NETWORK:-host}"
IMAGE="${REGISTRY}/${NAMESPACE}/${IMAGE_NAME}:${IMAGE_TAG}"

PUSH=1
[[ "${1:-}" == "--no-push" ]] && PUSH=0

# ── Build provenance ─────────────────────────────────────────────────────────
# Compute git commit + build time on the HOST (the image build can't run git —
# `.git` isn't in the context) and pass them as build-args. The all-in-one image
# bakes them into env vars; the stats dashboard surfaces them so you can tell
# which build is live. A working tree with uncommitted changes is flagged
# "-dirty" (builds use the working tree, not a clean checkout).
git_() { git -C "$REPO_ROOT" "$@" 2>/dev/null; }
BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if git_ rev-parse --git-dir >/dev/null; then
    GIT_SHA="$(git_ rev-parse HEAD)"
    GIT_COMMIT="$(git_ rev-parse --short HEAD)"
    GIT_BRANCH="$(git_ rev-parse --abbrev-ref HEAD)"
    GIT_SUBJECT="$(git_ log -1 --pretty=%s)"
    GIT_COMMIT_TIME="$(git_ log -1 --date=iso-strict --pretty=%cd)"
    [[ -n "$(git_ status --porcelain)" ]] && GIT_COMMIT="${GIT_COMMIT}-dirty"
else
    GIT_SHA=""; GIT_COMMIT="unknown"; GIT_BRANCH=""; GIT_SUBJECT=""; GIT_COMMIT_TIME=""
fi

echo "════════════════════════════════════════════════════════════════"
echo "  Build all-in-one image"
echo "    image      : $IMAGE"
echo "    dockerfile : build/Dockerfile  (context: repo root)"
echo "    network    : $DOCKER_BUILD_NETWORK"
echo "    build time : $BUILD_TIME"
echo "    git commit : ${GIT_BRANCH:+$GIT_BRANCH@}$GIT_COMMIT"
echo "    push       : $([[ $PUSH == 1 ]] && echo yes || echo 'no (--no-push)')"
echo "════════════════════════════════════════════════════════════════"

# CE only runs linux/amd64. Host networking lets apt/npm/pip resolve DNS on
# hosts whose docker bridge inherits an unreachable resolver.
docker build \
    --platform linux/amd64 \
    --network="$DOCKER_BUILD_NETWORK" \
    --build-arg CUGA_BUILD_TIME="$BUILD_TIME" \
    --build-arg CUGA_GIT_COMMIT="$GIT_COMMIT" \
    --build-arg CUGA_GIT_SHA="$GIT_SHA" \
    --build-arg CUGA_GIT_BRANCH="$GIT_BRANCH" \
    --build-arg CUGA_GIT_SUBJECT="$GIT_SUBJECT" \
    --build-arg CUGA_GIT_COMMIT_TIME="$GIT_COMMIT_TIME" \
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
