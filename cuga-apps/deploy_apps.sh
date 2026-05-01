#!/usr/bin/env bash
# =====================================================================
# deploy_apps.sh — deploy 21 cuga-apps FastAPI apps to IBM Cloud Code Engine.
#
# All 21 apps run from one shared image (built by build_apps_image.sh).
# Each CE app picks which main.py to run via --command + --argument.
#
# MCP URL resolution is automatic: the apps' _mcp_bridge.py detects CE_APP
# in the environment (auto-injected by Code Engine) and points at the
# deployed MCP servers. No per-app MCP_*_URL env var injection needed —
# but you can still override per-server with that env var if you want.
#
# Idempotent. Retries on transient registry pull errors. Continues past
# per-app failures and reports a summary at the end.
#
# Prerequisites (NOT done by this script):
#   - ibmcloud login + target region/RG + ce project select
#   - ./build_apps_image.sh (image must exist in ICR)
#   - 7 MCP servers + tool-explorer already deployed (./deploy_mcp.sh)
#   - CE secrets `app-env` and `icr-secret-1` exist
#
# Usage:
#   ./deploy_apps.sh                     # all 21
#   ./deploy_apps.sh web_researcher      # one
#   ./deploy_apps.sh paper_scout code_reviewer api_doc_gen   # subset
#   ./deploy_apps.sh recipe_composer city_beat               # the two new apps
#
# Override defaults via env:
#   REGION    (default: us-south)
#   NAMESPACE (default: routing_namespace)
#   IMAGE_TAG (default: latest)
#   APP_CPU   (default: 1)
#   APP_MEM   (default: 2G)
# =====================================================================

set -euo pipefail

REGION="${REGION:-us-south}"
NAMESPACE="${NAMESPACE:-routing_namespace}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
REG="icr.io/${NAMESPACE}"
IMAGE="${REG}/apps:${IMAGE_TAG}"
APP_CPU="${APP_CPU:-1}"
APP_MEM="${APP_MEM:-2G}"
SECRET_MOUNT_DIR="${SECRET_MOUNT_DIR:-/etc/cuga-secrets}"
MAX_RETRIES=3
RETRY_BACKOFF_SECONDS=15

# ── Manifest ───────────────────────────────────────────────────────────
# Each row: <app_dir> <port> <port_method>
#   port_method ∈ {arg, env}
#     arg → pass --port via argparse: python main.py --port <P>
#     env → set PORT=<P> as env var (travel_planner reads it that way)
#
# Tier 1: stateless. min-scale 0 (cold-start on first request, save cost).
# Tier 2: in-memory state. min-scale 1 (state persists between requests).

TIER1=(
  "web_researcher     28798 arg"
  "paper_scout        28808 arg"
  "travel_planner     28090 env"
  "code_reviewer      28807 arg"
  "hiking_research    28805 arg"
  "movie_recommender  28806 arg"
  "webpage_summarizer 28071 arg"
  "wiki_dive          28809 arg"
  "youtube_research   28803 arg"
  "arch_diagram       28804 arg"
  "brief_budget       28816 arg"
  "trip_designer      28817 arg"
  "ibm_cloud_advisor  28812 arg"
  "ibm_docs_qa        28813 arg"
  "ibm_whats_new      28814 arg"
  "api_doc_gen        28811 arg"
  "stock_alert        28801 arg"
  "recipe_composer    28820 arg"
  "city_beat          28821 arg"
)
TIER2=(
  "newsletter         28793 arg"
  "server_monitor     28767 arg"
)

# Tier 2 apps need min-scale 1 to keep their in-memory state alive
# between requests. Tier 1 can scale to zero.
declare -A IS_TIER2=()
for row in "${TIER2[@]}"; do
  read -r name _rest <<< "$row"
  IS_TIER2[$name]=1
done

ALL_APPS=("${TIER1[@]}" "${TIER2[@]}")

# ── Args / filtering ───────────────────────────────────────────────────
# Build the list of valid app names for validation.
VALID_NAMES=()
for row in "${ALL_APPS[@]}"; do
  read -r name _rest <<< "$row"
  VALID_NAMES+=("$name")
done

if [[ $# -gt 0 ]]; then
  TARGETS=()
  for arg in "$@"; do
    found=""
    for row in "${ALL_APPS[@]}"; do
      read -r name _rest <<< "$row"
      if [[ "$name" == "$arg" ]]; then
        TARGETS+=("$row")
        found=1
        break
      fi
    done
    if [[ -z "$found" ]]; then
      echo "ERROR: unknown app '$arg'. Known: ${VALID_NAMES[*]}" >&2
      exit 1
    fi
  done
else
  TARGETS=("${ALL_APPS[@]}")
fi

# ── Prereq checks ──────────────────────────────────────────────────────
require_cli() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: $1 not on PATH" >&2; exit 1; }; }
require_cli ibmcloud

if ! ibmcloud ce project current >/dev/null 2>&1; then
  echo "ERROR: no Code Engine project selected. Run:" >&2
  echo "  ibmcloud ce project select --name <your-project>" >&2
  exit 1
fi
if ! ibmcloud ce secret get --name app-env >/dev/null 2>&1; then
  echo "ERROR: CE secret 'app-env' not found in this project." >&2
  exit 1
fi
if ! ibmcloud ce registry get --name icr-secret-1 >/dev/null 2>&1; then
  echo "ERROR: CE registry-secret 'icr-secret-1' not found in this project." >&2
  exit 1
fi

# ── Banner ─────────────────────────────────────────────────────────────
echo "─────────────────────────────────────────────────────────────"
echo "  Project:  $(ibmcloud ce project current --output json | python3 -c 'import sys,json; print(json.load(sys.stdin).get("name","?"))' 2>/dev/null || echo '?')"
echo "  Image:    $IMAGE"
echo "  Apps:     ${#TARGETS[@]} target(s)"
echo "  CPU/Mem:  $APP_CPU / $APP_MEM"
echo "─────────────────────────────────────────────────────────────"
echo

# ── Deploy one app, with retry on transient registry errors ────────────
deploy_app() {
  local app_dir=$1 port=$2 port_method=$3 min_scale=$4
  local app_name="cuga-apps-${app_dir//_/-}"

  # Decide create-or-update.
  local action="create"
  if ibmcloud ce app get --name "$app_name" >/dev/null 2>&1; then
    action="update"
  fi

  # Construct the port-passing flags (argparse vs env var).
  local -a port_flags=()
  case "$port_method" in
    arg) port_flags=(--argument --port --argument "$port") ;;
    env) port_flags=(--env "PORT=$port") ;;
    *)   echo "    ERROR: unknown port_method '$port_method' for $app_dir" >&2; return 1 ;;
  esac

  for attempt in $(seq 1 $MAX_RETRIES); do
    echo "── [$action] $app_name (port $port, scale $min_scale-1) — attempt $attempt/$MAX_RETRIES ──"

    local rc=0
    local logfile
    logfile=$(mktemp -t "ce-app-${app_dir}-XXXXXX.log")

    if [[ "$action" == "create" ]]; then
      # Run via /entrypoint.sh (NOT python directly) so the entrypoint
      # sources the CE-mounted secret file at $CUGA_SECRETS_FILE before
      # exec'ing python. Passing --command python bypasses the Docker
      # ENTRYPOINT and the secret never gets loaded — that's the exact
      # bug that causes "OPENAI_API_KEY must be set" on CE.
      ibmcloud ce app create \
        --name "$app_name" \
        --image "$IMAGE" \
        --registry-secret icr-secret-1 \
        --port "$port" \
        --command /entrypoint.sh \
        --argument python --argument "/app/apps/$app_dir/main.py" \
        "${port_flags[@]}" \
        --mount-secret "$SECRET_MOUNT_DIR=app-env" \
        --env "CUGA_SECRETS_FILE=$SECRET_MOUNT_DIR/app.env" \
        --cpu "$APP_CPU" --memory "$APP_MEM" \
        --min-scale "$min_scale" --max-scale 1 \
        2>&1 | tee "$logfile" || rc=${PIPESTATUS[0]}
    else
      # Update path: roll the image and re-pull. Doesn't change cpu/memory/
      # scale so existing apps keep their original sizing — bump those by
      # hand if you need to.
      ibmcloud ce app update \
        --name "$app_name" \
        --image "$IMAGE" \
        --force \
        2>&1 | tee "$logfile" || rc=${PIPESTATUS[0]}
    fi

    if [[ $rc -eq 0 ]]; then
      rm -f "$logfile"
      return 0
    fi

    # Retry only on transient registry/network errors.
    if grep -qE "EOF|i/o timeout|TLS handshake|connection reset|temporarily unavailable|503" "$logfile"; then
      echo "    transient error — sleeping ${RETRY_BACKOFF_SECONDS}s before retry"
      rm -f "$logfile"
      sleep "$RETRY_BACKOFF_SECONDS"
      if ibmcloud ce app get --name "$app_name" >/dev/null 2>&1; then
        action="update"
      fi
      continue
    fi

    echo "    permanent error — last log lines:"
    tail -20 "$logfile" | sed 's/^/      /'
    rm -f "$logfile"
    return $rc
  done

  echo "    exhausted $MAX_RETRIES retries"
  return 1
}

# ── Main loop ──────────────────────────────────────────────────────────
declare -a SUCCEEDED=()
declare -a FAILED=()

for row in "${TARGETS[@]}"; do
  read -r app_dir port port_method <<< "$row"
  if [[ -n "${IS_TIER2[$app_dir]:-}" ]]; then
    min_scale=1
  else
    min_scale=0
  fi

  if deploy_app "$app_dir" "$port" "$port_method" "$min_scale"; then
    SUCCEEDED+=("$app_dir")
  else
    FAILED+=("$app_dir")
  fi
  echo
done

# ── Summary ────────────────────────────────────────────────────────────
echo "─────────────────────────────────────────────────────────────"
echo "  Summary"
echo "─────────────────────────────────────────────────────────────"
echo "  Succeeded (${#SUCCEEDED[@]}): ${SUCCEEDED[*]:-<none>}"
echo "  Failed    (${#FAILED[@]}): ${FAILED[*]:-<none>}"
echo

if [[ ${#FAILED[@]} -gt 0 ]]; then
  echo "  Diagnose any failure with:"
  for n in "${FAILED[@]}"; do
    echo "    ibmcloud ce app events --name cuga-apps-${n//_/-} | tail -30"
    echo "    ibmcloud ce app logs   --name cuga-apps-${n//_/-} --tail 100"
  done
  exit 1
fi

echo "  Public URLs:"
for n in "${SUCCEEDED[@]}"; do
  app_name="cuga-apps-${n//_/-}"
  url=$(ibmcloud ce app get --name "$app_name" --output url 2>/dev/null || echo '?')
  printf "    %-22s %s\n" "$n" "$url"
done
