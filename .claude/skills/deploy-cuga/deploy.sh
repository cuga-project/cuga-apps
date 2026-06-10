#!/usr/bin/env bash
# =====================================================================
# deploy.sh — ship cuga-apps to one or more targets:
#
#   local   refresh the local all-in-one (docker compose) on :8080
#   ce      build+push the all-in-one image and roll the Code Engine
#           service `cuga-agent-apps`
#   hf      rebuild the static umbrella UI and publish it to the
#           Hugging Face Space (it links into the CE service)
#
# Usage:
#   ./deploy.sh                 # all three (local, ce, hf)
#   ./deploy.sh ce              # just Code Engine
#   ./deploy.sh ce hf           # CE then HF
#   ./deploy.sh local           # just the local container
#   ./deploy.sh --dry-run all   # print the plan, run nothing
#
# Order note: when both `ce` and `hf` run, CE goes first — the HF build
# bakes in the CE service URL, so CE should be live first.
#
# Env overrides:
#   # Code Engine / image
#   NAMESPACE   ICR namespace        (default: routing_namespace)
#   IMAGE_TAG   image tag            (default: latest)
#   APP_NAME    CE app name          (default: cuga-agent-apps)
#   # Hugging Face
#   HF_SPACE    owner/space          (default: anupamamurthi/cuga-agent-apps)
#   HF_USER     git username for push (default: owner part of HF_SPACE)
#   HF_TOKEN    HF write token; if set it's used for the push, else your
#               cached git credentials / SSH are used
#   ALLINONE_BASE  CE base URL baked into the HF build (default: the CE
#                  host for APP_NAME; see build/hf/build.sh)
# =====================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"     # .claude/skills/deploy-cuga
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"                  # repo root

DRY=0
TARGETS=()
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    all)       TARGETS+=(local ce hf) ;;
    local|ce|hf) TARGETS+=("$a") ;;
    -h|--help) sed -n '2,/^# ===/p' "$0" | sed 's/^# \?//'; exit 0 ;;
    *) echo "ERROR: unknown target '$a' (want: local | ce | hf | all)" >&2; exit 2 ;;
  esac
done
[[ ${#TARGETS[@]} -eq 0 ]] && TARGETS=(local ce hf)

# De-dupe while keeping a stable order, and force ce-before-hf.
have() { printf '%s\n' "${TARGETS[@]}" | grep -qx "$1"; }
ORDERED=()
for t in local ce hf; do have "$t" && ORDERED+=("$t"); done
TARGETS=("${ORDERED[@]}")

say()  { echo "── $* ──"; }
run()  { echo "+ $*"; [[ $DRY == 1 ]] && return 0; "$@"; }
die()  { echo "ERROR: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "$1 not on PATH ($2)"; }

echo "════════════════════════════════════════════════════════════════"
echo "  cuga-apps deploy"
echo "    repo    : $REPO_ROOT"
echo "    targets : ${TARGETS[*]}"
echo "    dry-run : $([[ $DRY == 1 ]] && echo yes || echo no)"
echo "════════════════════════════════════════════════════════════════"

declare -a OK=() FAIL=()
mark() { if [[ $1 == 0 ]]; then OK+=("$2"); else FAIL+=("$2"); fi; }

# ── local: rebuild + run the all-in-one container on :8080 ────────────
do_local() {
  say "LOCAL — rebuild + run all-in-one (docker compose) on :8080"
  need docker "local container build"
  ( cd "$REPO_ROOT/build" || exit 1
    [[ -f .env ]] || { [[ -f .env.example ]] && cp .env.example .env && echo "  (created build/.env from .env.example — add keys)"; }
    run docker compose up --build -d
  )
}

# ── ce: build+push the image, then roll the CE service ───────────────
do_ce() {
  say "CODE ENGINE — build+push image, then deploy cuga-agent-apps"
  need docker "image build"
  need ibmcloud "Code Engine deploy"
  if [[ $DRY == 0 ]]; then
    ibmcloud ce project current >/dev/null 2>&1 \
      || die "no Code Engine project selected — run: ibmcloud ce project select --name <project>"
  fi
  run "$REPO_ROOT/build/ce/build_and_push.sh" || return 1
  run "$REPO_ROOT/build/ce/deploy.sh"          || return 1
}

# ── hf: rebuild the static UI, then push it to the HF Space ───────────
do_hf() {
  say "HUGGING FACE — rebuild static umbrella UI, publish to Space"
  need git "HF Space push"
  local space="${HF_SPACE:-anupamamurthi/cuga-agent-apps}"
  local user="${HF_USER:-${space%%/*}}"

  # Build the static SPA (ALLINONE_BASE, if set, is baked in).
  if [[ -n "${ALLINONE_BASE:-}" ]]; then
    run env ALLINONE_BASE="$ALLINONE_BASE" "$REPO_ROOT/build/hf/build.sh" || return 1
  else
    run "$REPO_ROOT/build/hf/build.sh" || return 1
  fi
  [[ $DRY == 1 ]] && { echo "+ (dry-run) would publish build/hf/dist → $space"; return 0; }

  local url="https://huggingface.co/spaces/$space"
  [[ -n "${HF_TOKEN:-}" ]] && url="https://${user}:${HF_TOKEN}@huggingface.co/spaces/$space"

  local tmp; tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN
  echo "+ git clone $space"
  git clone --depth 1 "$url" "$tmp" \
    || die "could not clone HF Space $space — set HF_TOKEN or configure git/HF auth"
  # Replace the Space contents with the fresh build (keep .git).
  find "$tmp" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
  cp -r "$REPO_ROOT/build/hf/dist/." "$tmp/"
  ( cd "$tmp" || exit 1
    git add -A
    if git diff --cached --quiet; then
      echo "  (no changes to publish)"
    else
      git commit -m "deploy: update umbrella UI ($(date -u +%Y-%m-%dT%H:%MZ))" >/dev/null
      git push || die "git push to HF Space failed — check HF_TOKEN / credentials"
      echo "  ✓ pushed to $space"
    fi
  )
}

for t in "${TARGETS[@]}"; do
  echo
  case "$t" in
    local) do_local; mark $? local ;;
    ce)    do_ce;    mark $? ce ;;
    hf)    do_hf;    mark $? hf ;;
  esac
done

echo
echo "════════════════════════════════════════════════════════════════"
echo "  Summary"
echo "    succeeded: ${OK[*]:-<none>}"
echo "    failed   : ${FAIL[*]:-<none>}"
echo "════════════════════════════════════════════════════════════════"
[[ ${#FAIL[@]} -eq 0 ]] || exit 1
