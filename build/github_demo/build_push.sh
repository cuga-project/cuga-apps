#!/usr/bin/env bash
# Build the GitHub demo image on Code Engine (no local docker): stock CUGA events image + the
# official GitHub MCP server + cuga-apps' repo_pulse + the github_repo_activity roster from cuga-agent.
#
#   CUGA_AGENT_DIR  checkout of cuga-agent (roster, MCP registry, automations)  default: ../cuga-agent next to this repo
#   BASE_IMAGE      CUGA events image to extend      default: icr.io/routing_namespace/cuga-events:nov4-68894670-precheck
#   IMAGE           image to produce                 default: icr.io/routing_namespace/cuga-github-demo:<git sha>[-dirty-<ts>]
#   BUILD_PROJECT / BUILD_REGION / BUILD_RG / REGISTRY_SECRET   where the buildrun runs (needs a push secret)
#   RESTORE_PROJECT / RESTORE_REGION / RESTORE_RG               CLI target restored afterwards
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
CUGA_AGENT_DIR="${CUGA_AGENT_DIR:-$(cd "$REPO/.." && pwd)/cuga-agent}"
BUILD_PROJECT="${BUILD_PROJECT:-ce-project-routing}"
BUILD_REGION="${BUILD_REGION:-us-east}"
BUILD_RG="${BUILD_RG:-routing}"
REGISTRY_SECRET="${REGISTRY_SECRET:-icr-secret-1}"
RESTORE_PROJECT="${RESTORE_PROJECT:-ce-cugaplusplus}"
RESTORE_REGION="${RESTORE_REGION:-eu-gb}"
RESTORE_RG="${RESTORE_RG:-cugaplusplus}"
BASE_IMAGE="${BASE_IMAGE:-icr.io/routing_namespace/cuga-events:nov4-68894670-precheck}"
TAG="$(git -C "$REPO" rev-parse --short HEAD)$( [ -z "$(git -C "$REPO" status --porcelain)" ] || echo "-dirty-$(date +%m%d%H%M)")"
IMAGE="${IMAGE:-icr.io/routing_namespace/cuga-github-demo:$TAG}"
EX="$CUGA_AGENT_DIR/events/examples"
for f in "$EX/rosters/github_repo_activity.yaml" "$EX/github_repo_activity/mcp_servers.yaml" "$EX/github_repo_activity/automations.yaml"; do
  [[ -f "$f" ]] || { echo "not found: $f (set CUGA_AGENT_DIR)"; exit 1; }
done

STAGE="$(mktemp -d -t cuga-github-demo-XXXXXX)"
restore() { ibmcloud target -r "$RESTORE_REGION" -g "$RESTORE_RG" -q >/dev/null 2>&1 || true
            ibmcloud ce project select --name "$RESTORE_PROJECT" >/dev/null 2>&1 || true; }
trap 'rm -rf "$STAGE"; restore' EXIT
mkdir -p "$STAGE/cuga-apps/mcp_servers" "$STAGE/cuga-apps/apps" "$STAGE/build/github_demo" "$STAGE/roster"
for d in __init__.py _core repo_pulse github_official; do
  rsync -a --exclude '__pycache__/' --exclude 'tests/' "$REPO/cuga-apps/mcp_servers/$d" "$STAGE/cuga-apps/mcp_servers/"
done
cp "$REPO/cuga-apps/apps/__init__.py" "$REPO/cuga-apps/apps/_ports.py" "$STAGE/cuga-apps/apps/"
# `ibmcloud ce buildrun submit` has no --build-arg, so the base image is written into the staged copy
sed "s|^ARG BASE=.*|ARG BASE=$BASE_IMAGE|" "$HERE/Dockerfile" > "$STAGE/build/github_demo/Dockerfile"
cp "$EX/rosters/github_repo_activity.yaml" "$EX/github_repo_activity/mcp_servers.yaml" "$EX/github_repo_activity/automations.yaml" "$STAGE/roster/"
# never ship local env/secret files
if find "$STAGE" \( -name '.env*' -o -name '*.key' -o -name '*.pem' \) | grep -q .; then echo "ABORT: secret-looking file in build context"; exit 1; fi

ibmcloud target -r "$BUILD_REGION" -g "$BUILD_RG" -q >/dev/null
ibmcloud ce project select --name "$BUILD_PROJECT" >/dev/null
NAME="cuga-github-demo-$(date +%s)"
echo "Building $IMAGE from $BASE_IMAGE (buildrun $NAME in $BUILD_PROJECT) ..."
ibmcloud ce buildrun submit --name "$NAME" --source "$STAGE" \
  --strategy dockerfile --dockerfile build/github_demo/Dockerfile --image "$IMAGE" \
  --registry-secret "$REGISTRY_SECRET" --size large --timeout 1800 --wait --wait-timeout 1800 \
  >"$STAGE.submit.log" 2>&1 || { echo "-- buildrun submit output:"; tail -15 "$STAGE.submit.log"; }
rm -f "$STAGE.submit.log"
STATUS=$(ibmcloud ce buildrun get -n "$NAME" -o json 2>/dev/null | python3 -c 'import sys,json
d=json.load(sys.stdin); s=d.get("status")
if isinstance(s,dict):
    s=s.get("reason") or next((c.get("reason") for c in s.get("conditions",[]) if c.get("type")=="Succeeded"),"")
print(str(s or "unknown").lower())' 2>/dev/null || echo unknown)
echo "buildrun $NAME: $STATUS"
if [[ "$STATUS" != "succeeded" ]]; then ibmcloud ce buildrun logs -n "$NAME" | tail -40; exit 1; fi
echo "$IMAGE" > "$HERE/.last_image"
echo "Image: $IMAGE"
