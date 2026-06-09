#!/usr/bin/env bash
# =====================================================================
# build_mcp_image.sh — build and push the MCP server image and the
# mcp-tool-explorer image used by Code Engine.
#
# Two images, both required by ./deploy_mcp.sh:
#   icr.io/<ns>/mcp:<tag>                — shared image, all 7 MCP servers
#   icr.io/<ns>/mcp-tool-explorer:<tag>  — separate image, the explorer UI
#
# The MCP image is shared across web / knowledge / geo / finance / code /
# local / text — each CE app picks which server to run via
# `python -m mcp_servers.<name>.server`, so we don't need 7 different
# images. The tool-explorer has a different dep set (no docling /
# faster-whisper / tiktoken downloads) and lives in its own image.
#
# Always builds for linux/amd64 (Code Engine runs amd64; Apple Silicon
# would otherwise emit unrunnable arm64 images).
#
# Usage:
#   ./build_mcp_image.sh                     # build + push both, :latest
#   IMAGE_TAG=v3 ./build_mcp_image.sh        # build + push both, :v3
#   ./build_mcp_image.sh --no-push           # build only (skip the push)
#   ./build_mcp_image.sh mcp                 # only the shared MCP image
#   ./build_mcp_image.sh tool-explorer       # only the explorer image
#   ./build_mcp_image.sh mcp tool-explorer   # explicit "both" (same as no args)
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
MCP_IMAGE="${REG}/mcp:${IMAGE_TAG}"
EXPLORER_IMAGE="${REG}/mcp-tool-explorer:${IMAGE_TAG}"

PUSH=true
TARGETS=()
for arg in "$@"; do
  case "$arg" in
    --no-push)       PUSH=false ;;
    -h|--help)
      sed -n '2,/^# ===/p' "$0" | sed 's/^# \?//'
      exit 0 ;;
    mcp|tool-explorer) TARGETS+=("$arg") ;;
    *) echo "ERROR: unknown arg '$arg'" >&2; exit 1 ;;
  esac
done

# Default to building both when no positional targets given.
if [[ ${#TARGETS[@]} -eq 0 ]]; then
  TARGETS=(mcp tool-explorer)
fi

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
echo "  Targets:    ${TARGETS[*]}"
echo "  MCP image:  $MCP_IMAGE"
echo "  Explorer:   $EXPLORER_IMAGE"
echo "  Context:    $(pwd)"
echo "  Push:       $PUSH"
echo "─────────────────────────────────────────────────────────────"
echo

build_one() {
  local image=$1
  local dockerfile=$2

  echo "── Building $image (-f $dockerfile) ──"
  docker build --platform linux/amd64 -f "$dockerfile" -t "$image" .

  if $PUSH; then
    echo
    echo "── Pushing $image ──"
    docker push "$image"
  fi
  echo
}

declare -a SUCCEEDED=()
declare -a FAILED=()

for tgt in "${TARGETS[@]}"; do
  case "$tgt" in
    mcp)
      if build_one "$MCP_IMAGE" "Dockerfile.mcp"; then
        SUCCEEDED+=("$MCP_IMAGE")
      else
        FAILED+=("$MCP_IMAGE")
      fi
      ;;
    tool-explorer)
      # The tool-explorer's Dockerfile lives in its own subdir but expects
      # the cuga-apps repo root as the build context (so it can COPY both
      # mcp_tool_explorer/ and apps/_ports.py). Pass it via -f, not cd.
      if build_one "$EXPLORER_IMAGE" "mcp_tool_explorer/Dockerfile"; then
        SUCCEEDED+=("$EXPLORER_IMAGE")
      else
        FAILED+=("$EXPLORER_IMAGE")
      fi
      ;;
  esac
done

echo "─────────────────────────────────────────────────────────────"
echo "  Summary"
echo "─────────────────────────────────────────────────────────────"
echo "  Succeeded (${#SUCCEEDED[@]}):"
for img in "${SUCCEEDED[@]}"; do echo "    $img"; done
if [[ ${#FAILED[@]} -gt 0 ]]; then
  echo "  Failed    (${#FAILED[@]}):"
  for img in "${FAILED[@]}"; do echo "    $img"; done
  exit 1
fi
echo
if $PUSH; then
  echo "  Verify with: ibmcloud cr image-list | grep -E 'mcp|tool-explorer'"
  echo "  Deploy with: ./deploy_mcp.sh"
fi
