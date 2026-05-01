#!/usr/bin/env bash
# =====================================================================
# build_apps_image.sh — build and push the shared cuga-apps image.
#
# One image, used by all 19 deployable cuga-apps. Each CE app picks which
# main.py to run via `--command python --argument /app/apps/<name>/main.py`,
# so we don't need 19 different images — just one shared one with all
# apps baked in.
#
# Always builds for linux/amd64 (Code Engine runs amd64; Apple Silicon
# would otherwise emit unrunnable arm64 images).
#
# Usage:
#   ./build_apps_image.sh                    # build + push :latest
#   IMAGE_TAG=v3 ./build_apps_image.sh       # build + push :v3
#   ./build_apps_image.sh --no-push          # build only (skip the push)
#
# Override defaults via env:
#   REGION    (default: us-south)
#   NAMESPACE (default: routing_namespace)
#   IMAGE_TAG (default: latest)
# =====================================================================

set -euo pipefail

REGION="${REGION:-us-south}"
NAMESPACE="${NAMESPACE:-routing_namespace}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
REG="icr.io/${NAMESPACE}"
IMAGE="${REG}/apps:${IMAGE_TAG}"

PUSH=true
for arg in "$@"; do
  case "$arg" in
    --no-push) PUSH=false ;;
    -h|--help)
      sed -n '2,/^# ===/p' "$0" | sed 's/^# \?//'
      exit 0 ;;
    *) echo "ERROR: unknown flag '$arg'" >&2; exit 1 ;;
  esac
done

cd "$(dirname "$0")"

require_cli() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: $1 not on PATH" >&2; exit 1; }; }
require_cli docker

if $PUSH; then
  require_cli ibmcloud
  if ! ibmcloud cr images >/dev/null 2>&1; then
    echo "WARN: ibmcloud cr not authenticated — run 'ibmcloud cr login' if push fails"
  fi
fi

echo "─────────────────────────────────────────────────────────────"
echo "  Image:     $IMAGE"
echo "  Context:   $(pwd)"
echo "  Push:      $PUSH"
echo "─────────────────────────────────────────────────────────────"
echo

echo "── Building $IMAGE ──"
docker build --platform linux/amd64 -f Dockerfile.apps -t "$IMAGE" .

if $PUSH; then
  echo
  echo "── Pushing $IMAGE ──"
  docker push "$IMAGE"
fi

echo
echo "✅ Done."
echo "   Image: $IMAGE"
if $PUSH; then
  echo "   Verify with: ibmcloud cr image-list | grep apps"
fi
