#!/usr/bin/env bash
# =====================================================================
# deploy_ui.sh — push the umbrella UI image to Docker Hub, then sync
# the Hugging Face Space so it picks up the new image.
#
# Sibling of:
#   build_ui_image.sh   — builds + pushes to Docker Hub (this script
#                         also pushes, in case build was --no-push)
#   deploy_mcp.sh       — deploys MCP servers to Code Engine
#   deploy_apps.sh      — deploys 19 cuga-apps to Code Engine
#
# Two stages:
#
#   1) Docker Hub push   (assumes ./build_ui_image.sh ran successfully)
#        docker push amurthi44g1wd/cuga-apps-ui:<tag>
#
#   2) HF Space sync     (clone the Space repo, ensure Dockerfile
#                         points at the freshly-pushed image, commit
#                         a marker so Spaces rebuilds, and git-push)
#        https://huggingface.co/spaces/anupamamurthi/agent-apps
#
# Auth:
#   - Docker Hub:  expects you've run `docker login` already (the build
#     script does the same). No token plumbed through env.
#   - HF Space:    git push uses HTTPS basic auth. Set HF_TOKEN in env
#     (see https://huggingface.co/settings/tokens — needs "write" scope
#     for Spaces). HF_USER defaults to anupamamurthi.
#
# Usage:
#   HF_TOKEN=hf_xxx ./deploy_ui.sh                # push + sync, :latest
#   HF_TOKEN=hf_xxx IMAGE_TAG=v3 ./deploy_ui.sh   # versioned tag
#   ./deploy_ui.sh --skip-dockerhub               # only sync the Space
#                                                 # (image already on Hub)
#   ./deploy_ui.sh --skip-hf                      # only push to Docker Hub
#   ./deploy_ui.sh --dry-run                      # plan only, no side effects
#
# Override defaults via env:
#   DOCKERHUB_USER  (default: amurthi44g1wd)
#   IMAGE_NAME      (default: cuga-apps-ui)
#   IMAGE_TAG       (default: latest)
#   HF_USER         (default: anupamamurthi)
#   HF_SPACE        (default: agent-apps)
#   HF_TOKEN        (required for HF stage; "write" scope on the Space)
# =====================================================================

set -euo pipefail

DOCKERHUB_USER="${DOCKERHUB_USER:-amurthi44g1wd}"
IMAGE_NAME="${IMAGE_NAME:-cuga-apps-ui}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
IMAGE="${DOCKERHUB_USER}/${IMAGE_NAME}:${IMAGE_TAG}"

HF_USER="${HF_USER:-ibm-research}"
HF_SPACE="${HF_SPACE:-cuga-apps}"
HF_REPO="https://huggingface.co/spaces/${HF_USER}/${HF_SPACE}"
HF_GIT_USER="${HF_GIT_USER:-$HF_USER}"  # git author name/email when committing

DO_DOCKERHUB=true
DO_HF=false  # HF Space sync disabled — only push to Docker Hub
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-dockerhub) DO_DOCKERHUB=false ;;
    --skip-hf)        DO_HF=false ;;
    --dry-run)        DRY_RUN=true ;;
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
$DO_HF && require_cli git

if $DO_HF && [[ -z "${HF_TOKEN:-}" ]]; then
  echo "ERROR: HF_TOKEN not set. Generate one at https://huggingface.co/settings/tokens" >&2
  echo "       (must have 'write' scope on space ${HF_USER}/${HF_SPACE}), then:" >&2
  echo "       HF_TOKEN=hf_xxx ./deploy_ui.sh" >&2
  exit 1
fi

echo "─────────────────────────────────────────────────────────────"
echo "  Image:          $IMAGE"
echo "  Docker Hub:     $($DO_DOCKERHUB && echo yes || echo skip)"
echo "  HF Space sync:  $($DO_HF && echo "$HF_REPO" || echo skip)"
echo "  Dry run:        $DRY_RUN"
echo "─────────────────────────────────────────────────────────────"
echo

# ── Stage 1: Docker Hub push ──────────────────────────────────────────
if $DO_DOCKERHUB; then
  echo "── Pushing $IMAGE to Docker Hub ──"

  if $DRY_RUN; then
    echo "  [dry-run] docker push $IMAGE"
  else
    # Verify the image exists locally before trying to push it.
    # Skipped under --dry-run so you can plan without having built yet.
    if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
      echo "ERROR: image '$IMAGE' not found locally." >&2
      echo "       Build it first: ./build_ui_image.sh --no-push" >&2
      echo "       (or run ./build_ui_image.sh which also pushes)" >&2
      exit 1
    fi
    if ! docker info 2>/dev/null | grep -q "Username:"; then
      echo "WARN: not logged into Docker Hub. Run 'docker login' first if push fails."
    fi
    docker push "$IMAGE"
  fi
  echo
fi

# ── Stage 2: HF Space sync — DISABLED ─────────────────────────────────
# This whole stage is commented out via a heredoc-discard. Only the
# Docker Hub push above runs. To re-enable: remove the
# `: <<'__HF_DISABLED__'` line below and the matching `__HF_DISABLED__`
# closer after the final `fi`, then set `DO_HF=true` (or stop passing
# `--skip-hf`).
: <<'__HF_DISABLED__'
# Strategy: clone the Space (a git repo at huggingface.co/spaces/USER/SPACE),
# write a Dockerfile that just does `FROM amurthi44g1wd/cuga-apps-ui:<tag>`,
# write the README.md frontmatter HF needs (Space SDK = docker, app port =
# 80), bump a marker so an unchanged image tag still triggers a rebuild,
# and git-push back to HF. The Space build picks the new image up
# automatically because the `FROM` line changed (or because the marker did).
if $DO_HF; then
  echo "── Syncing HF Space ${HF_USER}/${HF_SPACE} ──"

  WORKDIR=$(mktemp -d -t cuga-hf-space-XXXXXX)
  trap 'rm -rf "$WORKDIR"' EXIT

  CLONE_URL="https://${HF_GIT_USER}:${HF_TOKEN}@huggingface.co/spaces/${HF_USER}/${HF_SPACE}"

  if $DRY_RUN; then
    echo "  [dry-run] git clone <hf-space> $WORKDIR"
    echo "  [dry-run] write Dockerfile pinning FROM $IMAGE"
    echo "  [dry-run] write README.md frontmatter (sdk: docker, app_port: 7860)"
    echo "  [dry-run] write .deploy-marker = $(date -u +%Y%m%dT%H%M%SZ)"
    echo "  [dry-run] git commit + push to ${HF_REPO}"
  else
    # Quiet clone so the token doesn't leak into terminal output if something
    # echoes the args. The URL is still visible in `ps` for the duration.
    if ! git clone --quiet "$CLONE_URL" "$WORKDIR"; then
      echo "ERROR: git clone failed. Common causes:" >&2
      echo "       - HF_TOKEN missing 'write' scope on space ${HF_USER}/${HF_SPACE}" >&2
      echo "       - HF_USER does not own the space" >&2
      echo "       - Space does not exist yet — create it once at https://huggingface.co/new-space" >&2
      exit 1
    fi

    # Write the Space's Dockerfile. HF builds whatever Dockerfile is at the
    # repo root; the simplest possible one just inherits the published image.
    cat > "$WORKDIR/Dockerfile" <<EOF
# Autogenerated by deploy_ui.sh — do not hand-edit.
# This Space inherits the umbrella UI image published to Docker Hub.
# Re-run ./deploy_ui.sh from cuga-apps/ to update.
FROM ${IMAGE}
EOF

    # Write the README.md frontmatter HF Spaces requires. Keep any body
    # the user added; only replace the YAML frontmatter block.
    README="$WORKDIR/README.md"
    BODY=""
    if [[ -f "$README" ]]; then
      # Strip existing frontmatter if present (first --- ... ---).
      BODY=$(awk '
        BEGIN { in_fm=0; seen=0 }
        /^---$/ {
          if (!seen) { in_fm=1; seen=1; next }
          if (in_fm)  { in_fm=0; next }
        }
        !in_fm { print }
      ' "$README")
    fi
    # HF Spaces rejects app_port < 1025 (privileged ports). The UI image
     # has nginx listening on 7860 (matches HF's default Spaces port and
     # is fine for local dev too — host maps 3001 → 7860).
    cat > "$README" <<EOF
---
title: Cuga Agent Apps
emoji: 🤖
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

${BODY:-Umbrella UI for the cuga-apps demo suite. Built from \`${IMAGE}\`.}
EOF

    # Bump a marker so HF rebuilds even when the image tag string didn't
    # change (e.g. you republished `:latest` to Docker Hub). Without this,
    # an identical Dockerfile produces no commit and HF sees nothing to do.
    date -u +%Y%m%dT%H%M%SZ > "$WORKDIR/.deploy-marker"

    # Commit + push.
    (
      cd "$WORKDIR"
      git config user.email "${HF_USER}@users.noreply.huggingface.co"
      git config user.name  "$HF_GIT_USER"
      git add Dockerfile README.md .deploy-marker
      if git diff --cached --quiet; then
        echo "  no changes to commit (Space already in sync)"
      else
        git commit --quiet -m "deploy: ${IMAGE} ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
        git push --quiet origin HEAD
        echo "  pushed update to $HF_REPO"
      fi
    )
  fi
  echo
fi
__HF_DISABLED__

echo "─────────────────────────────────────────────────────────────"
echo "  ✅ Done."
$DO_DOCKERHUB && echo "     Docker Hub:  $IMAGE"
$DO_HF        && echo "     HF Space:    $HF_REPO"
echo "─────────────────────────────────────────────────────────────"
