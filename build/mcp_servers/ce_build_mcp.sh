#!/usr/bin/env bash
# =====================================================================
# build/mcp_servers/ce_build_mcp.sh — build the standalone MCP images IN CODE
# ENGINE (native amd64, no local Docker) and push them to ICR:
#
#   icr.io/routing_namespace/mcp:<tag>                (cuga-apps/Dockerfile.mcp)
#   icr.io/routing_namespace/mcp-tool-explorer:<tag>  (cuga-apps/mcp_tool_explorer/Dockerfile)
#
# The context is staged from git's view of cuga-apps/ (.gitignore'd files such as
# .env and venvs never leave this machine). Builds run in ce-project-routing,
# which holds the ICR push secret; the previous target is restored on exit.
#
# Usage:
#   IMAGE_TAG=2026-11-09-mcp2 build/mcp_servers/ce_build_mcp.sh            # both images
#   IMAGE_TAG=... build/mcp_servers/ce_build_mcp.sh mcp                    # one of them
# Then deploy with build/mcp_servers/deploy_mcp.sh (IMAGE_TAG=<same tag>).
# =====================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
IMAGE_TAG="${IMAGE_TAG:-$(date +%Y-%m-%d)-$(git -C "$REPO" rev-parse --short HEAD)}"
REG="${REGISTRY:-icr.io}/${NAMESPACE:-routing_namespace}"
BUILD_PROJECT="${BUILD_PROJECT:-ce-project-routing}"
BUILD_REGION="${BUILD_REGION:-us-east}"
BUILD_RG="${BUILD_RG:-routing}"
REGISTRY_SECRET="${REGISTRY_SECRET:-icr-secret-1}"
TARGETS=("$@"); [[ ${#TARGETS[@]} -eq 0 ]] && TARGETS=(mcp mcp-tool-explorer)

PREV_REGION="$(ibmcloud target --output json 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin).get("region",{}).get("name",""))' 2>/dev/null || true)"
PREV_RG="$(ibmcloud target --output json 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin).get("resource_group",{}).get("name",""))' 2>/dev/null || true)"
PREV_PROJECT="$(ibmcloud ce project current --output json 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin).get("name",""))' 2>/dev/null || true)"

STAGE="$(mktemp -d -t cuga-mcp-XXXXXX)"
restore() {
  rm -rf "$STAGE"
  [[ -n "$PREV_REGION" ]] && ibmcloud target -r "$PREV_REGION" ${PREV_RG:+-g "$PREV_RG"} -q >/dev/null 2>&1 || true
  [[ -n "$PREV_PROJECT" ]] && ibmcloud ce project select --name "$PREV_PROJECT" >/dev/null 2>&1 || true
}
trap restore EXIT

# Stage cuga-apps/ as the context root (what both Dockerfiles COPY).
cd "$REPO/cuga-apps"
git ls-files -co --exclude-standard -- \
    Dockerfile.mcp entrypoint.sh requirements.mcp.txt \
    apps/_ports.py apps/__init__.py mcp_servers mcp_tool_explorer \
  | grep -vE '(^|/)(__pycache__|tests|\.pytest_cache)(/|$)|\.pyc$' > "$STAGE.files"
rsync -a --files-from="$STAGE.files" ./ "$STAGE/"
rm -f "$STAGE.files"
if find "$STAGE" \( -name '.env' -o -name '.env.*' ! -name '.env.example' -o -name '*.key' -o -name '*.pem' -o -name '.venv*' \) | grep -q .; then
  echo "ABORT: secret-looking file in the build context"; exit 1
fi
echo "Staged context: $(du -sh "$STAGE" | cut -f1), $(find "$STAGE" -type f | wc -l | tr -d ' ') files"

ibmcloud target -r "$BUILD_REGION" -g "$BUILD_RG" -q >/dev/null
ibmcloud ce project select --name "$BUILD_PROJECT" >/dev/null

build_one() {  # $1 image name, $2 dockerfile (relative to cuga-apps/)
  local image="$REG/$1:$IMAGE_TAG" name="cuga-$1-$(date +%s)"
  echo "Building $image (buildrun $name) ..."
  ibmcloud ce buildrun submit --name "$name" --source "$STAGE" \
    --strategy dockerfile --dockerfile "$2" --image "$image" \
    --registry-secret "$REGISTRY_SECRET" --size xlarge --timeout 3600 \
    --wait --wait-timeout 3600 || true
  local status
  status=$(ibmcloud ce buildrun get -n "$name" -o json 2>/dev/null | python3 -c 'import sys,json
d=json.load(sys.stdin); s=d.get("status")
if isinstance(s,dict):
    s=s.get("reason") or next((c.get("reason") for c in s.get("conditions",[]) if c.get("type")=="Succeeded"),"")
print(str(s or "unknown").lower())' 2>/dev/null || echo unknown)
  echo "buildrun $name: $status"
  if [[ "$status" != "succeeded" ]]; then
    ibmcloud ce buildrun logs -n "$name" 2>/dev/null | tail -40
    return 1
  fi
  echo "✓ $image"
}

for t in "${TARGETS[@]}"; do
  case "$t" in
    mcp)               build_one mcp Dockerfile.mcp ;;
    mcp-tool-explorer) build_one mcp-tool-explorer mcp_tool_explorer/Dockerfile ;;
    *) echo "unknown target $t (mcp | mcp-tool-explorer)"; exit 1 ;;
  esac
done
echo "Deploy with: IMAGE_TAG=$IMAGE_TAG build/mcp_servers/deploy_mcp.sh"
