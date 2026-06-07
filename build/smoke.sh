#!/usr/bin/env bash
# =====================================================================
# build/smoke.sh — verify the all-in-one image is truly working.
#
# Run it AFTER `docker compose up` (from build/). It hits only the single
# public port, so it works the same against localhost or a Code Engine URL.
# Output is HTTP statuses + structural checks — NO secrets — so it's safe to
# paste back into a chat for debugging.
#
# Usage:
#   ./smoke.sh                         # against http://localhost:8080
#   ./smoke.sh https://<ce-url>        # against a deployed CE URL
#   ./smoke.sh http://localhost:8080 --ask                 # also do one real /ask
#   ./smoke.sh http://localhost:8080 --ask find-a-doctor "cardiologist in Boston"
#
# Exit code is non-zero if any structural check fails.
# =====================================================================
set -u

BASE="${1:-http://localhost:8080}"
BASE="${BASE%/}"
shift || true

DO_ASK=0
ASK_APP="github-trending"
ASK_PROMPT="What is trending in python this week?"
if [[ "${1:-}" == "--ask" ]]; then
  DO_ASK=1; shift || true
  [[ $# -ge 1 ]] && ASK_APP="$1" && shift
  [[ $# -ge 1 ]] && ASK_PROMPT="$1" && shift
fi

# The 21 ship-ready path segments (must match build/generate.py).
APPS=(
  stock-alert server-monitor newsletter web-researcher travel-planner
  youtube-research arch-diagram hiking-research movie-recommender
  webpage-summarizer paper-scout wiki-dive ibm-cloud-advisor ibm-docs-qa
  recipe-composer city-beat ouroboros github-trending ai-labs-news
  find-a-doctor meetup-finder
)

pass=0; fail=0
ok()   { echo "  [PASS] $*"; pass=$((pass+1)); }
bad()  { echo "  [FAIL] $*"; fail=$((fail+1)); }

code() { curl -s -m 15 -o /dev/null -w '%{http_code}' "$1"; }

echo "=== Smoke test against $BASE ==="
echo

echo "── front door ──"
c=$(code "$BASE/healthz"); [[ "$c" == "200" ]] && ok "/healthz ($c)" || bad "/healthz ($c)"
ui=$(curl -s -m 15 "$BASE/")
if echo "$ui" | grep -qi "<!doctype html"; then ok "/ serves the umbrella UI"; else bad "/ did not return HTML"; fi
echo

echo "── ship-ready apps (proxy + path-prefix rewrite) ──"
for seg in "${APPS[@]}"; do
  url="$BASE/a/$seg/"
  body=$(curl -s -m 20 -w $'\n%{http_code}' "$url")
  status="${body##*$'\n'}"
  html="${body%$'\n'*}"
  if [[ "$status" != "200" ]]; then
    bad "$seg → HTTP $status"
    continue
  fi
  # The nginx sub_filter must have injected the base href + fetch shim, proving
  # both the proxy AND the path-prefix rewrite work for this app.
  if echo "$html" | grep -q "<base href=\"/a/$seg/\"" && echo "$html" | grep -q "window.fetch"; then
    ok "$seg → 200, prefix rewrite injected"
  else
    bad "$seg → 200 but MISSING injected base/shim (fetch calls will 404)"
  fi
done
echo

if [[ "$DO_ASK" == "1" ]]; then
  echo "── live agent call (needs LLM creds in the container) ──"
  echo "  POST $BASE/a/$ASK_APP/ask   prompt: \"$ASK_PROMPT\""
  resp=$(curl -s -m 180 -w $'\n%{http_code}' -X POST "$BASE/a/$ASK_APP/ask" \
           -H 'Content-Type: application/json' \
           -d "{\"question\":$(printf '%s' "$ASK_PROMPT" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))'),\"thread_id\":\"smoke\"}")
  status="${resp##*$'\n'}"
  doc="${resp%$'\n'*}"
  if [[ "$status" == "200" ]]; then
    ok "agent /ask returned 200"
    echo "  answer (first 300 chars): $(echo "$doc" | python3 -c 'import json,sys;print((json.load(sys.stdin).get("answer") or "")[:300])' 2>/dev/null || echo "$doc" | head -c 300)"
  else
    bad "agent /ask → HTTP $status"
    echo "  body (first 300 chars): $(echo "$doc" | head -c 300)"
  fi
  echo
fi

echo "=== Result: $pass passed, $fail failed ==="
[[ "$fail" == "0" ]]
