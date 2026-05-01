#!/usr/bin/env bash
# =====================================================================
# build_ui_image.sh — build and push the umbrella UI image to Docker Hub.
#
# This image is published publicly on Docker Hub and consumed by the
# Hugging Face Space that hosts the live demo. The image is the same
# whether running locally or on HF: the SPA detects its deployment
# context at runtime (via hostname suffix `.hf.space`) and rewrites
# "Try it" / "Launch App" links accordingly. You can also force the
# behavior at build time with VITE_DEPLOYMENT_TARGET=huggingface, which
# bakes the flag into the bundle.
#
# Two build modes:
#
#   Default (auto-detect)   — one image works in both contexts. Local
#       docker compose users hit localhost links; HF visitors auto-get
#       Code Engine URLs because window.location.hostname matches *.hf.space.
#
#   --target huggingface    — same code, but bakes VITE_DEPLOYMENT_TARGET
#       into the bundle so the rewrite happens unconditionally. Useful
#       when serving the image behind a CDN where the runtime hostname
#       doesn't end in hf.space.
#
# No secrets in the image:
#   - Build context is ui/ only (apps/.env physically outside it).
#   - ui/.dockerignore explicitly excludes .env, *.key, *-credentials.json
#     etc., as a defensive layer if someone ever changes the context.
#
# Usage:
#   ./build_ui_image.sh                                 # build :latest, push
#   ./build_ui_image.sh --no-push                       # build only
#   ./build_ui_image.sh --target huggingface            # bake HF flag, push
#   IMAGE_TAG=v3 ./build_ui_image.sh                    # versioned tag
#   DOCKERHUB_USER=someone-else ./build_ui_image.sh     # different user/org
# =====================================================================

set -euo pipefail

DOCKERHUB_USER="${DOCKERHUB_USER:-amurthi44g1wd}"
IMAGE_NAME="${IMAGE_NAME:-cuga-apps-ui}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
IMAGE="${DOCKERHUB_USER}/${IMAGE_NAME}:${IMAGE_TAG}"

# Defaults
PUSH=true
TARGET="auto"   # "auto" leaves the build arg empty (runtime hostname detection)
                # "huggingface" bakes VITE_DEPLOYMENT_TARGET into the bundle

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-push) PUSH=false ;;
    --target)
      shift
      TARGET="${1:-}"
      if [[ "$TARGET" != "auto" && "$TARGET" != "huggingface" && "$TARGET" != "local" ]]; then
        echo "ERROR: --target must be one of: auto, huggingface, local" >&2
        exit 1
      fi
      ;;
    -h|--help)
      sed -n '2,/^# ===/p' "$0" | sed 's/^# \?//'
      exit 0 ;;
    *) echo "ERROR: unknown flag '$1'" >&2; exit 1 ;;
  esac
  shift
done

cd "$(dirname "$0")"

require_cli() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: $1 not on PATH" >&2; exit 1; }; }
require_cli docker

# Build args: only set VITE_DEPLOYMENT_TARGET when explicitly requested.
# Empty string = unset → runtime hostname detection takes over.
BUILD_ARGS=()
if [[ "$TARGET" == "huggingface" ]]; then
  BUILD_ARGS+=(--build-arg "VITE_DEPLOYMENT_TARGET=huggingface")
elif [[ "$TARGET" == "local" ]]; then
  BUILD_ARGS+=(--build-arg "VITE_DEPLOYMENT_TARGET=local")
fi

echo "─────────────────────────────────────────────────────────────"
echo "  Image:    $IMAGE"
echo "  Context:  $(pwd)/ui"
echo "  Target:   $TARGET"
echo "  Push:     $PUSH"
echo "─────────────────────────────────────────────────────────────"
echo

echo "── Building $IMAGE ──"
docker build \
  --platform linux/amd64 \
  -f ui/Dockerfile \
  -t "$IMAGE" \
  "${BUILD_ARGS[@]}" \
  ui/

if $PUSH; then
  echo
  echo "── Pushing $IMAGE to Docker Hub ──"
  if ! docker info 2>/dev/null | grep -q "Username:"; then
    echo "WARN: not logged into Docker Hub. Run 'docker login' first if push fails."
  fi
  docker push "$IMAGE"
fi

echo
echo "✅ Done."
echo "   Image: $IMAGE"
if $PUSH; then
  echo "   Pull on HF Space:  docker pull $IMAGE"
fi

# Quick reminder of how this gets used.
cat <<EOF

   Hugging Face Space (Docker SDK) — minimal README.md frontmatter:

     ---
     title: Cuga Apps Umbrella UI
     emoji: 🤖
     colorFrom: indigo
     colorTo: purple
     sdk: docker
     app_port: 80
     ---

   And under the Space's "Files" tab, a Dockerfile that simply does:

     FROM ${IMAGE}

   Or — if you want to bake VITE_DEPLOYMENT_TARGET=huggingface explicitly
   for HF, rebuild + push with:

     ./build_ui_image.sh --target huggingface

EOF
