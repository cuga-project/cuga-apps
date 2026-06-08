#!/usr/bin/env bash
# build/hf/build.sh — build the LIGHTWEIGHT umbrella UI for a Hugging Face
# Static Space.
#
# This UI is a "dumb" launcher: it only LINKS into the single all-in-one Code
# Engine service ( <ALLINONE_BASE>/a/<app>/ ). No apps, no MCP, no Python ship
# with it — the heavy backend is the one CE container. Output is plain static
# files ready to push to an HF Static Space.
#
#   ./build.sh                                  # uses the default CE base below
#   ALLINONE_BASE=https://my-ce-host ./build.sh
#   ./build.sh https://my-ce-host               # base as 1st arg
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"          # build/hf
UI_DIR="$(cd "$HERE/../../cuga-apps/ui" && pwd)"
OUT_DIR="$HERE/dist"

# The CE all-in-one base URL (baked into the build). Pass your real one; the
# default matches the repo's CE project — see CE_PROJECT_HASH / CE_REGION in
# cuga-apps/ui/src/data/deployment.ts and APP_NAME in build/ce/deploy.sh.
DEFAULT_BASE="https://cuga-allinone.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud"
ALLINONE_BASE="${ALLINONE_BASE:-${1:-$DEFAULT_BASE}}"
ALLINONE_BASE="${ALLINONE_BASE%/}"                            # strip trailing slash

echo "════════════════════════════════════════════════════════════════"
echo "  Build lightweight umbrella UI for Hugging Face (static)"
echo "    mode      : remote-allinone"
echo "    CE base   : $ALLINONE_BASE"
echo "    app links : $ALLINONE_BASE/a/<app>/"
echo "    output    : build/hf/dist/"
echo "════════════════════════════════════════════════════════════════"

cd "$UI_DIR"
[ -d node_modules ] || npm ci

VITE_DEPLOYMENT_TARGET=remote-allinone \
VITE_ALLINONE_BASE="$ALLINONE_BASE" \
    npm run build

# Stage a complete HF Static Space: built SPA + the space README (frontmatter)
# + a 404 fallback so client-side routes survive a hard refresh on static hosts.
rm -rf "$OUT_DIR"; mkdir -p "$OUT_DIR"
cp -r dist/. "$OUT_DIR/"
cp "$HERE/space-README.md" "$OUT_DIR/README.md"
cp "$OUT_DIR/index.html" "$OUT_DIR/404.html"

echo
echo "✓ static space staged at build/hf/dist/"
echo "  Publish: push the CONTENTS of build/hf/dist/ to your HF Space git repo:"
echo "    git clone https://huggingface.co/spaces/<user>/<space> /tmp/space"
echo "    cp -r build/hf/dist/. /tmp/space/ && cd /tmp/space && git add -A && git commit -m ui && git push"
