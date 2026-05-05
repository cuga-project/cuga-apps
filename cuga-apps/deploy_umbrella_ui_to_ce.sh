#!/usr/bin/env bash
# =====================================================================
# deploy_umbrella_ui_to_ce.sh — deploy the umbrella UI to IBM Code Engine.
#
# Sibling of:
#   build_ui_image.sh   — builds + pushes the UI image to Docker Hub
#   deploy_ui.sh        — pushes to Docker Hub (HF Space sync currently disabled)
#   deploy_mcp.sh       — deploys 7 MCP servers + tool-explorer to CE (ICR)
#   deploy_apps.sh      — deploys 21 cuga-apps to CE (ICR)
#
# What this script does:
#   - Pulls the public image `amurthi44g1wd/cuga-apps-ui:<tag>` from
#     Docker Hub and registers it as a CE app named `cuga-apps-ui`.
#   - The container is a static nginx serving the Vite/React SPA on
#     port 7860 (matches ui/Dockerfile + ui/nginx.conf — same port HF
#     uses, so one image works in both contexts).
#   - The SPA's URL-rewrite logic in ui/src/data/deployment.ts
#     already maps each app tile's localhost link to the corresponding
#     CE deployment URL when `VITE_DEPLOYMENT_TARGET=huggingface` (or
#     `ce`) was set at build time, OR when the runtime hostname ends
#     in `.hf.space`. The image you publish to Docker Hub for HF is
#     therefore reusable on CE — the Tile "Launch App" buttons will
#     point at the cuga-apps-* CE deployments automatically when the
#     image was built with `--target huggingface`.
#
# Why no secrets:
#   The umbrella UI is fully static — no LLM keys, no API keys, no env
#   plumbing. Unlike the FastAPI apps, there's nothing to mount.
#
# Why no registry-secret:
#   The image is on public Docker Hub (`docker.io/amurthi44g1wd/...`),
#   not in your private ICR namespace. CE pulls from Docker Hub
#   anonymously — `--registry-secret` is only needed for private
#   registries.
#
# Idempotent. If the app exists, it's updated to the new image; if not,
# it's created with the resource and scaling defaults below.
#
# Prerequisites (NOT done by this script):
#   - ibmcloud login + target region/RG
#   - ibmcloud ce project select --name <your-project>
#   - The image already pushed to Docker Hub. Either:
#       ./build_ui_image.sh                           # auto runtime detect
#       ./build_ui_image.sh --target huggingface      # bake CE link rewrite
#     (The HF target is what you want for CE too — see notes above.)
#
# Usage:
#   ./deploy_umbrella_ui_to_ce.sh                     # deploy :latest
#   IMAGE_TAG=v3 ./deploy_umbrella_ui_to_ce.sh        # versioned tag
#   ./deploy_umbrella_ui_to_ce.sh --build             # rebuild + push first
#   ./deploy_umbrella_ui_to_ce.sh --dry-run           # plan only
#
# Override defaults via env:
#   DOCKERHUB_USER  (default: amurthi44g1wd)
#   IMAGE_NAME      (default: cuga-apps-ui)
#   IMAGE_TAG       (default: latest)
#   APP_NAME        (default: cuga-apps-ui)
#   APP_CPU         (default: 0.25)        — nginx + static files, tiny
#   APP_MEM         (default: 0.5G)        — same
#   MIN_SCALE       (default: 0)           — cold-start OK for a UI
#   MAX_SCALE       (default: 1)
#   PORT            (default: 7860)        — matches ui/Dockerfile EXPOSE
# =====================================================================

set -euo pipefail

DOCKERHUB_USER="${DOCKERHUB_USER:-amurthi44g1wd}"
IMAGE_NAME="${IMAGE_NAME:-cuga-apps-ui}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
IMAGE="docker.io/${DOCKERHUB_USER}/${IMAGE_NAME}:${IMAGE_TAG}"

APP_NAME="${APP_NAME:-cuga-apps-ui}"
APP_CPU="${APP_CPU:-0.25}"
APP_MEM="${APP_MEM:-0.5G}"
MIN_SCALE="${MIN_SCALE:-0}"
MAX_SCALE="${MAX_SCALE:-1}"
PORT="${PORT:-7860}"

DO_BUILD=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build)   DO_BUILD=true ;;
    --dry-run) DRY_RUN=true ;;
    -h|--help)
      sed -n '2,/^# ===/p' "$0" | sed 's/^# \?//'
      exit 0 ;;
    *) echo "ERROR: unknown flag '$1'" >&2; exit 1 ;;
  esac
  shift
done

cd "$(dirname "$0")"

require_cli() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: $1 not on PATH" >&2; exit 1; }; }
require_cli ibmcloud
$DO_BUILD && require_cli docker

# ── Prereq: CE project must be selected ──────────────────────────────
if ! ibmcloud ce project current >/dev/null 2>&1; then
  echo "ERROR: no Code Engine project selected. Run:" >&2
  echo "  ibmcloud ce project select --name <your-project>" >&2
  exit 1
fi

PROJECT=$(ibmcloud ce project current --output json 2>/dev/null \
            | python3 -c 'import sys,json; print(json.load(sys.stdin).get("name","?"))' \
            2>/dev/null || echo '?')

echo "─────────────────────────────────────────────────────────────"
echo "  CE Project:   $PROJECT"
echo "  CE App:       $APP_NAME"
echo "  Image:        $IMAGE"
echo "  Port:         $PORT (nginx in container)"
echo "  CPU/Mem:      $APP_CPU / $APP_MEM"
echo "  Scaling:      min=$MIN_SCALE, max=$MAX_SCALE"
echo "  Build first:  $DO_BUILD"
echo "  Dry run:      $DRY_RUN"
echo "─────────────────────────────────────────────────────────────"
echo

# ── Optional rebuild + push ──────────────────────────────────────────
# We default to --target huggingface so the SPA's localhost → CE URL
# rewriting (in ui/src/data/deployment.ts) runs unconditionally on CE,
# instead of relying on hostname auto-detection (which only matches
# *.hf.space, not *.codeengine.appdomain.cloud).
if $DO_BUILD; then
  echo "── Rebuilding $IMAGE with --target huggingface ──"
  if $DRY_RUN; then
    echo "  [dry-run] DOCKERHUB_USER=$DOCKERHUB_USER IMAGE_NAME=$IMAGE_NAME IMAGE_TAG=$IMAGE_TAG ./build_ui_image.sh --target huggingface"
  else
    DOCKERHUB_USER="$DOCKERHUB_USER" IMAGE_NAME="$IMAGE_NAME" IMAGE_TAG="$IMAGE_TAG" \
      ./build_ui_image.sh --target huggingface
  fi
  echo
fi

# ── Decide create vs. update ─────────────────────────────────────────
ACTION="create"
if ibmcloud ce app get --name "$APP_NAME" >/dev/null 2>&1; then
  ACTION="update"
fi

# ── Deploy ───────────────────────────────────────────────────────────
echo "── [$ACTION] $APP_NAME ──"

if [[ "$ACTION" == "create" ]]; then
  if $DRY_RUN; then
    cat <<EOF
  [dry-run] ibmcloud ce app create \\
    --name $APP_NAME \\
    --image $IMAGE \\
    --port $PORT \\
    --cpu $APP_CPU --memory $APP_MEM \\
    --min-scale $MIN_SCALE --max-scale $MAX_SCALE
EOF
  else
    ibmcloud ce app create \
      --name "$APP_NAME" \
      --image "$IMAGE" \
      --port "$PORT" \
      --cpu "$APP_CPU" --memory "$APP_MEM" \
      --min-scale "$MIN_SCALE" --max-scale "$MAX_SCALE"
  fi
else
  # Update path: roll the image, force a re-pull. We don't change CPU /
  # memory / scaling on update so a hand-tuned app keeps its sizing.
  # Pass --image-pull-policy Always so :latest republishes are picked
  # up even when the tag string didn't change.
  if $DRY_RUN; then
    cat <<EOF
  [dry-run] ibmcloud ce app update \\
    --name $APP_NAME \\
    --image $IMAGE \\
    --force
EOF
  else
    ibmcloud ce app update \
      --name "$APP_NAME" \
      --image "$IMAGE" \
      --force
  fi
fi

echo

# ── Print the public URL ─────────────────────────────────────────────
if ! $DRY_RUN; then
  URL=$(ibmcloud ce app get --name "$APP_NAME" --output url 2>/dev/null || echo '?')
  echo "─────────────────────────────────────────────────────────────"
  echo "  ✅ Done."
  echo "     CE App:  $APP_NAME"
  echo "     URL:     $URL"
  echo "─────────────────────────────────────────────────────────────"
else
  echo "─────────────────────────────────────────────────────────────"
  echo "  ✅ Dry-run complete — nothing was changed."
  echo "─────────────────────────────────────────────────────────────"
fi
