#!/usr/bin/env bash
# build/ce/clone_secret.sh — create a NEW Code Engine secret as a copy of an existing
# one, with optional overrides. For side-by-side copies of the all-in-one, so a copy
# gets production's credentials without anyone writing them to a local file.
#
#   ./clone_secret.sh <source-secret> <new-secret> [KEY=VALUE ...]
#
#   # the cuga-agent-apps-1 copy: same keys, but its own stats object + utterance
#   # archive so it never overwrites production's stats in the shared COS bucket
#   ./clone_secret.sh cuga-agent-apps-env cuga-agent-apps-1-env \
#       USAGE_S3_KEY=rollup/usage_db.cuga-agent-apps-1.json \
#       USAGE_UTTERANCE_PREFIX=utterances-cuga-agent-apps-1
#
# Safety: only ever CREATES. Refuses if <new-secret> exists, or is the production
# secret. Values pass through a mode-600 temp file that is deleted on exit; nothing
# is printed but key names.
set -euo pipefail

SRC="${1:-}"; DST="${2:-}"
[[ -n "$SRC" && -n "$DST" ]] || { echo "usage: $0 <source-secret> <new-secret> [KEY=VALUE ...]"; exit 1; }
shift 2
[[ "$DST" != "cuga-agent-apps-env" ]] || { echo "✗ refusing to write the production secret"; exit 1; }
[[ "$SRC" != "$DST" ]] || { echo "✗ source and destination are the same"; exit 1; }
command -v ibmcloud >/dev/null || { echo "✗ ibmcloud CLI not found"; exit 1; }
ibmcloud ce project current >/dev/null 2>&1 || { echo "✗ no Code Engine project selected"; exit 1; }
if ibmcloud ce secret get --name "$DST" >/dev/null 2>&1; then
    echo "✗ secret '$DST' already exists — this script only creates; edit it with 'ibmcloud ce secret update'"
    exit 1
fi

umask 077
TMP="$(mktemp)"; trap 'rm -f "$TMP"' EXIT

# Source values → KEY=VALUE lines (JSON output carries the values in .data).
ibmcloud ce secret get --name "$SRC" -o json | python3 -c '
import json, sys
overrides = dict(a.split("=", 1) for a in sys.argv[2:])
data = dict(json.load(sys.stdin).get("data") or {})
if not data:
    sys.exit("source secret has no data")
data.update(overrides)
with open(sys.argv[1], "w") as f:
    for k, v in data.items():
        if "\n" in str(v):
            sys.exit(f"value of {k} spans lines; not representable in an env file")
        f.write(f"{k}={v}\n")
print(f"  {len(data)} keys ({len(overrides)} overridden: {sorted(overrides) or []})")
' "$TMP" "$@"

ibmcloud ce secret create --name "$DST" --from-env-file "$TMP" >/dev/null
echo "✓ created secret '$DST' from '$SRC'"
