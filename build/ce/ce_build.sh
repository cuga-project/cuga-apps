#!/usr/bin/env bash
# =====================================================================
# build/ce/ce_build.sh — build the all-in-one image IN CODE ENGINE (native
# amd64, no local Docker/Podman disk or QEMU emulation) and push it to ICR.
#
# The build context is staged from git's view of the working tree
# (`git ls-files -co --exclude-standard`, so .gitignore'd files — .env, venvs,
# local databases — never leave this machine), limited to what build/Dockerfile
# COPYs, and then filtered by build/Dockerfile.dockerignore. The script aborts
# if anything secret-looking is left in the context.
#
# Usage:
#   IMAGE_TAG=2026-11-09-cuga045 build/ce/ce_build.sh
#   IMAGE_NAME=cuga-agent-apps-1 IMAGE_TAG=... build/ce/ce_build.sh
#
# Code Engine builds have no --build-arg, so the build-provenance ARGs
# (CUGA_GIT_COMMIT, ...) are written into the staged Dockerfile's ARG defaults.
# The build runs in ce-project-routing (which holds the ICR push secret); the
# previously selected region / resource group / project is restored on exit.
# =====================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # build/ce
REPO="$(cd "$HERE/../.." && pwd)"

IMAGE_NAME="${IMAGE_NAME:-cuga-agent-apps-1}"
IMAGE_TAG="${IMAGE_TAG:-$(date +%Y-%m-%d)-$(git -C "$REPO" rev-parse --short HEAD)}"
IMAGE="${REGISTRY:-icr.io}/${NAMESPACE:-routing_namespace}/${IMAGE_NAME}:${IMAGE_TAG}"
BUILD_PROJECT="${BUILD_PROJECT:-ce-project-routing}"
BUILD_REGION="${BUILD_REGION:-us-east}"
BUILD_RG="${BUILD_RG:-routing}"
REGISTRY_SECRET="${REGISTRY_SECRET:-icr-secret-1}"
BUILD_SIZE="${BUILD_SIZE:-xlarge}"
BUILD_TIMEOUT="${BUILD_TIMEOUT:-3600}"

if [[ "$IMAGE_NAME" == "cuga-agent-apps" && "${CONFIRM_PROD:-0}" != "1" ]]; then
  echo "✗ refusing to build the PRODUCTION image name ($IMAGE). Set CONFIRM_PROD=1 to mean it."
  exit 1
fi

# Remember the current target so we can put it back.
PREV_REGION="$(ibmcloud target --output json 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin).get("region",{}).get("name",""))' 2>/dev/null || true)"
PREV_RG="$(ibmcloud target --output json 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin).get("resource_group",{}).get("name",""))' 2>/dev/null || true)"
PREV_PROJECT="$(ibmcloud ce project current --output json 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin).get("name",""))' 2>/dev/null || true)"

STAGE="$(mktemp -d -t cuga-allinone-XXXXXX)"
restore() {
  rm -rf "$STAGE" "$STAGE.files" "$STAGE.filter.py"
  [[ -n "$PREV_REGION" ]] && ibmcloud target -r "$PREV_REGION" ${PREV_RG:+-g "$PREV_RG"} -q >/dev/null 2>&1 || true
  [[ -n "$PREV_PROJECT" ]] && ibmcloud ce project select --name "$PREV_PROJECT" >/dev/null 2>&1 || true
}
trap restore EXIT

# ── 1. stage the context (only what build/Dockerfile COPYs) ──────────────
cd "$REPO"
cat > "$STAGE.filter.py" <<'PY'
import fnmatch, sys
pats = [l.strip() for l in open(sys.argv[1]) if l.strip() and not l.startswith("#")]
def ignored(path):
    parts = path.split("/")
    for p in pats:
        bare = p[3:] if p.startswith("**/") else p
        if fnmatch.fnmatch(path, p) or fnmatch.fnmatch(path, bare):
            return True
        # a pattern naming a directory ignores everything under it
        for i in range(1, len(parts)):
            prefix = "/".join(parts[:i])
            if fnmatch.fnmatch(prefix, bare) or (p.startswith("**/") and fnmatch.fnmatch(parts[i - 1], bare)):
                return True
        if p.startswith("**/") and fnmatch.fnmatch(parts[-1], bare):
            return True
    return False
for line in sys.stdin:
    f = line.rstrip("\n")
    if f and not ignored(f):
        print(f)
PY
git ls-files -co --exclude-standard -- \
    cuga-apps/ui cuga-apps/apps cuga-apps/mcp_servers cuga-apps/requirements.apps.txt \
    build/Dockerfile build/constraints.allinone.txt build/requirements.mcp.txt \
    build/patch-deployment.cjs build/generate.py \
  | python3 "$STAGE.filter.py" "$REPO/build/Dockerfile.dockerignore" > "$STAGE.files"
rm -f "$STAGE.filter.py"
rsync -a --files-from="$STAGE.files" "$REPO/" "$STAGE/"
rm -f "$STAGE.files"

# Provenance → ARG defaults (CE builds take no --build-arg).
GIT_SHA="$(git rev-parse HEAD)"; GIT_COMMIT="$(git rev-parse --short HEAD)"
[[ -n "$(git status --porcelain)" ]] && GIT_COMMIT="${GIT_COMMIT}-dirty"
GIT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
GIT_SUBJECT="$(git log -1 --pretty=%s | tr -d '"\\')"
GIT_COMMIT_TIME="$(git log -1 --date=iso-strict --pretty=%cd)"
BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
python3 - "$STAGE/build/Dockerfile" <<PY
import sys
p = sys.argv[1]; s = open(p).read()
vals = {"CUGA_BUILD_TIME": "$BUILD_TIME", "CUGA_GIT_COMMIT": "$GIT_COMMIT",
        "CUGA_GIT_SHA": "$GIT_SHA", "CUGA_GIT_BRANCH": "$GIT_BRANCH",
        "CUGA_GIT_SUBJECT": "$GIT_SUBJECT", "CUGA_GIT_COMMIT_TIME": "$GIT_COMMIT_TIME"}
for k, v in vals.items():
    s = s.replace(f'ARG {k}=""', f'ARG {k}="{v}"')
open(p, "w").write(s)
PY

if find "$STAGE" \( -name '.env' -o -name '.env.*' ! -name '.env.example' -o -name '*.key' -o -name '*.pem' \
                    -o -name '.venv*' \) | grep -q .; then
  echo "ABORT: secret-looking file in the build context:"
  find "$STAGE" \( -name '.env' -o -name '.env.*' ! -name '.env.example' -o -name '*.key' -o -name '*.pem' -o -name '.venv*' \)
  exit 1
fi
echo "Staged context: $(du -sh "$STAGE" | cut -f1), $(find "$STAGE" -type f | wc -l | tr -d ' ') files"

# ── 2. build in Code Engine ──────────────────────────────────────────────
ibmcloud target -r "$BUILD_REGION" -g "$BUILD_RG" -q >/dev/null
ibmcloud ce project select --name "$BUILD_PROJECT" >/dev/null
NAME="cuga-allinone-$(date +%s)"
echo "Building $IMAGE (buildrun $NAME in $BUILD_PROJECT, size $BUILD_SIZE) ..."
ibmcloud ce buildrun submit --name "$NAME" --source "$STAGE" \
  --strategy dockerfile --dockerfile build/Dockerfile --image "$IMAGE" \
  --registry-secret "$REGISTRY_SECRET" --size "$BUILD_SIZE" --timeout "$BUILD_TIMEOUT" \
  --wait --wait-timeout "$BUILD_TIMEOUT" || true

STATUS=$(ibmcloud ce buildrun get -n "$NAME" -o json 2>/dev/null | python3 -c 'import sys,json
d=json.load(sys.stdin); s=d.get("status")
if isinstance(s,dict):
    s=s.get("reason") or next((c.get("reason") for c in s.get("conditions",[]) if c.get("type")=="Succeeded"),"")
print(str(s or "unknown").lower())' 2>/dev/null || echo unknown)
echo "buildrun $NAME: $STATUS"
if [[ "$STATUS" != "succeeded" ]]; then
  ibmcloud ce buildrun logs -n "$NAME" 2>/dev/null | tail -60
  exit 1
fi
echo "$IMAGE" > "$HERE/.last_image"
echo "✓ Image: $IMAGE"
