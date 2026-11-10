#!/usr/bin/env bash
# Deploy the GitHub channels + events demo: two Code Engine apps from the cuga-github-demo image.
#
#   cuga-core-demo        CUGA + the github_repo_activity roster; runs the GitHub MCP + repo_pulse as stdio
#   cuga-events-svc-demo  channels (Discord, Slack, Telegram, WhatsApp), GitHub webhooks, native cron
#
# Steps (each idempotent):
#   secrets          database + demo-{core,events,tools}-secrets, copied from Nightwatch (demo_secrets.py prepare)
#   core             create/replace cuga-core-demo
#   events           create/replace cuga-events-svc-demo (pointed at cuga-core-demo)
#   seed             arm the automations in cuga-agent's automations.yaml (needs WATCH_REPO, REPORT_REPO,
#                    WATCH_CHANNEL_ID, NEWS_CHANNEL_ID)
#   discord          guilds | setup GUILD_ID: create #ask-cuga, #cuga-watch, #cuga-news with the bot
#   fire ID          run one armed automation now (daily-report, poll-new-items, watch-new-…), real path
#   nightwatch-off   silence Nightwatch's channels and let it scale to zero (bot tokens are single-owner)
#   nightwatch-on    undo nightwatch-off
#   urls             print the two URLs and the webhook/Slack/WhatsApp endpoints
#
# Env: IMAGE (default build/github_demo/.last_image), CE_PROJECT/CE_REGION/CE_RESOURCE_GROUP,
#      REGISTRY_SECRET, CUGA_AGENT_DIR (for seed), PYTHON (with psycopg, for secrets)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
CE_PROJECT="${CE_PROJECT:-ce-cugaplusplus}"
CE_REGION="${CE_REGION:-eu-gb}"
CE_RESOURCE_GROUP="${CE_RESOURCE_GROUP:-cugaplusplus}"
REGISTRY_SECRET="${REGISTRY_SECRET:-icr-routing-pull}"
IMAGE="${IMAGE:-$(cat "$HERE/.last_image" 2>/dev/null || true)}"
CUGA_AGENT_DIR="${CUGA_AGENT_DIR:-$(cd "$REPO/.." && pwd)/cuga-agent}"
PYTHON="${PYTHON:-python3}"
PREFIX="${PREFIX:-demo}"
CORE_APP="cuga-core-$PREFIX"
EVENTS_APP="cuga-events-svc-$PREFIX"
# Nightwatch (the on-call demo) holds the same bot tokens in another project
NW_PROJECT="${NW_PROJECT:-ce-project-routing}"
NW_REGION="${NW_REGION:-us-east}"
NW_RG="${NW_RG:-routing}"

target() {
  ibmcloud target -r "$CE_REGION" -g "$CE_RESOURCE_GROUP" -q >/dev/null
  ibmcloud ce project select --name "$CE_PROJECT" >/dev/null
}

recreate() {  # name, args...
  local name="$1"; shift
  if ibmcloud ce app get --name "$name" >/dev/null 2>&1; then
    ibmcloud ce app delete --name "$name" --force --wait --ignore-not-found >/dev/null
  fi
  echo "== creating $name ($IMAGE)"
  ibmcloud ce app create --name "$name" "$@" --wait --wait-timeout 900 >/dev/null
}

url_of() { ibmcloud ce app get --name "$1" --output url 2>/dev/null || true; }

step_secrets() { "$PYTHON" "$HERE/demo_secrets.py" prepare; }

step_core() {
  [[ -n "$IMAGE" ]] || { echo "IMAGE not set and no build/github_demo/.last_image (run build_push.sh)"; exit 1; }
  local events_url; events_url="$(url_of "$EVENTS_APP")"
  recreate "$CORE_APP" \
    --image "$IMAGE" --registry-secret "$REGISTRY_SECRET" --port 7860 \
    --min-scale 1 --max-scale 1 --cpu 2 --memory 8G --ephemeral-storage 4G --request-timeout 600 \
    --env-from-secret "$PREFIX-core-secrets" \
    --mount-secret "/run/secrets/demo-tools=$PREFIX-tools-secrets" \
    --env "CUGA_EVENTS_ENABLED=true" --env "DEPLOY_REV=$(date +%s)" \
    --env "DYNACONF_SUPERVISOR__REGISTRY_ENABLED=true" \
    --env "DYNACONF_STORAGE__MODE=local" \
    ${events_url:+--env "EVENTS_API_URL=$events_url"} \
    --command /usr/local/bin/entrypoint.sh \
    --argument uv --argument run --argument cuga --argument start --argument demo
  echo "CORE_URL=$(url_of "$CORE_APP")"
}

step_events() {
  [[ -n "$IMAGE" ]] || { echo "IMAGE not set"; exit 1; }
  local core_url; core_url="$(url_of "$CORE_APP")"
  [[ -n "$core_url" ]] || { echo "$CORE_APP not found; run '$0 core' first"; exit 1; }
  recreate "$EVENTS_APP" \
    --image "$IMAGE" --registry-secret "$REGISTRY_SECRET" --port 8100 \
    --min-scale 1 --max-scale 1 --cpu 1 --memory 4G --ephemeral-storage 4G --request-timeout 600 \
    --env-from-secret "$PREFIX-events-secrets" \
    --env "EVENTS_SERVICE_PORT=8100" --env "EVENTS_HOST=0.0.0.0" --env "CUGA_URL=$core_url" \
    --env "EVENTS_SCHEDULER=native" --env "EVENTS_TELEGRAM_BACKEND=direct" --env "EVENTS_DISCORD_BACKEND=direct" \
    --env "EVENTS_SLACK_BACKEND=direct" --env "EVENTS_DISCORD_CHAT=mention" --env "EVENTS_SLACK_CHAT=mention" \
    --env "DEPLOY_REV=$(date +%s)" --env "EVENTS_CORS_ORIGINS=$core_url" \
    --command /usr/local/bin/entrypoint.sh \
    --argument uv --argument run --argument python --argument -m --argument cuga.backend.events.service
  local events_url; events_url="$(url_of "$EVENTS_APP")"
  ibmcloud ce app update --name "$EVENTS_APP" --env "EVENTS_PUBLIC_URL=$events_url" --wait >/dev/null
  ibmcloud ce app update --name "$CORE_APP" --env "EVENTS_API_URL=$events_url" --wait >/dev/null
  step_urls
}

step_seed() {
  local envfile; envfile="$(mktemp -t demo-local-env-XXXXXX)"
  trap 'rm -f "$envfile"' RETURN
  "$PYTHON" "$HERE/demo_secrets.py" local-env "$envfile" >/dev/null
  # shellcheck disable=SC1090
  ( set -a; . "$envfile"; set +a
    cd "$CUGA_AGENT_DIR" && uv run --quiet python events/scripts/seed_automations.py \
      events/examples/github_repo_activity/automations.yaml "$@" )
}

step_discord() {  # guilds | setup GUILD_ID — runs discord_channels.py with the bot token from the secret
  local envfile; envfile="$(mktemp -t demo-local-env-XXXXXX)"
  trap 'rm -f "$envfile"' RETURN
  "$PYTHON" "$HERE/demo_secrets.py" local-env "$envfile" >/dev/null
  # shellcheck disable=SC1090
  ( set -a; . "$envfile"; set +a; python3 "$HERE/discord_channels.py" "$@" )
}

step_fire() {  # AUTOMATION_ID — run one armed automation NOW, exactly as its trigger would
  # Reads the armed row from the events database and posts the same /invoke envelope the native
  # scheduler posts (native_scheduler._invoke_body), so the run goes through the real path: the
  # supervisor, the sub-agent, its tools, the POLL change gate, and delivery to its channel.
  # A GitHub watcher has no stored event, so for those this sends a sample one-line event instead.
  local id="${1:?usage: $0 fire AUTOMATION_ID}" envfile; envfile="$(mktemp -t demo-local-env-XXXXXX)"
  trap 'rm -f "$envfile"' RETURN
  "$PYTHON" "$HERE/demo_secrets.py" local-env "$envfile" >/dev/null
  local events_url; events_url="$(url_of "$EVENTS_APP")"
  # shellcheck disable=SC1090
  ( set -a; . "$envfile"; set +a; export FIRE_ID="$id" EVENTS_URL="$events_url"
    cd "$CUGA_AGENT_DIR" && uv run --quiet python - <<'PY'
import json, os, time, urllib.request
from cuga.backend.events import native_scheduler
from cuga.backend.events.subscriptions import SubscriptionStore

sub = SubscriptionStore(os.environ["EVENTS_DB"]).get(os.environ["FIRE_ID"])
if sub is None:
    raise SystemExit(f"no armed automation {os.environ['FIRE_ID']!r} (run: deploy.sh seed)")
body = native_scheduler._invoke_body(sub)
if sub.mode == "PUSH":  # a webhook watcher: give it a sample event in the shape the GitHub route sends
    body["text"] = (f"{sub.prompt}\n\nThe watched event just happened: [github/{sub.event}] "
                    f"TEST event from deploy.sh fire on {sub.config.get('repo')} — by someone")
    body["source"] = {"type": "integration", "name": "github", "thread_id": sub.thread_id}
    body["event"] = {"kind": sub.event, "payload": {}}
req = urllib.request.Request(os.environ["EVENTS_URL"] + "/invoke", data=json.dumps(body).encode(), method="POST",
                             headers={"Content-Type": "application/json", "X-Gateway-Token": os.environ["GATEWAY_TOKEN"]})
t = time.time()
d = json.load(urllib.request.urlopen(req, timeout=600))
poll = d.get("poll")
print(f"{sub.id} ({sub.mode}) → {sub.target_agent}: {time.time() - t:.0f}s"
      + (f", poll changed={poll.get('changed')} ({poll.get('reason')})" if poll else ""))
print((d.get("answer") or d.get("error") or "")[:1500])
PY
  )
}

nightwatch() {  # on|off
  ibmcloud target -r "$NW_REGION" -g "$NW_RG" -q >/dev/null
  ibmcloud ce project select --name "$NW_PROJECT" >/dev/null
  if [[ "$1" == off ]]; then
    ibmcloud ce app update --name cuga-events-svc --min-scale 0 \
      --env LOCAL_HONOR_DISCORD=false --env LOCAL_HONOR_TELEGRAM=false \
      --env LOCAL_HONOR_SLACK=false --env LOCAL_HONOR_WHATSAPP=false --wait >/dev/null
    ibmcloud ce app update --name cuga-core --min-scale 0 --wait >/dev/null
    echo "Nightwatch ($NW_PROJECT): channels silenced, min-scale 0"
  else
    ibmcloud ce app update --name cuga-events-svc --min-scale 1 \
      --env-rm LOCAL_HONOR_DISCORD --env-rm LOCAL_HONOR_TELEGRAM \
      --env-rm LOCAL_HONOR_SLACK --env-rm LOCAL_HONOR_WHATSAPP --wait >/dev/null
    ibmcloud ce app update --name cuga-core --min-scale 1 --wait >/dev/null
    echo "Nightwatch ($NW_PROJECT): channels restored, min-scale 1"
  fi
  target
}

step_urls() {
  local core events; core="$(url_of "$CORE_APP")"; events="$(url_of "$EVENTS_APP")"
  printf 'CORE_URL=%s\nEVENTS_URL=%s\n' "$core" "$events" | tee "$HERE/.urls.env"
  echo "GitHub webhook:   $events/api/events/github/events   (content type application/json, secret GITHUB_WEBHOOK_SECRET)"
  echo "Slack Request URL: $events/api/events/slack/events"
  echo "WhatsApp callback: $events/api/events/whatsapp/events"
}

target
trap target EXIT
cmd="${1:-}"; shift || true
case "$cmd" in
  secrets) step_secrets ;;
  core) step_core ;;
  events) step_events ;;
  seed) step_seed "$@" ;;
  discord) step_discord "$@" ;;
  fire) step_fire "$@" ;;
  nightwatch-off) nightwatch off ;;
  nightwatch-on) nightwatch on ;;
  urls) step_urls ;;
  *) echo "usage: $0 secrets|core|events|seed [--dry-run|--remove]|discord guilds|discord setup GUILD_ID|fire AUTOMATION_ID|nightwatch-off|nightwatch-on|urls"; exit 2 ;;
esac
