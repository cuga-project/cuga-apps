#!/bin/sh
# Container entrypoint for the `apps` service.
# Launches all 23 apps in the background and waits for them to exit.
#
# MCP servers run as separate services (see docker-compose.yml) and must be
# reachable at http://mcp-<name>:29NN before these apps finish their startup
# handshake. Docker's depends_on: starts them in order but doesn't block on
# readiness — if an app hits the bridge before its MCP server is ready it will
# retry (the MCP client has its own reconnect behavior).

APP_DIR=/app/apps

log() { echo "[start.sh] $*"; }

cd "$APP_DIR" || exit 1

log "Starting web_researcher     on :28798"
python web_researcher/main.py --port 28798 &

log "Starting paper_scout         on :28808"
python paper_scout/main.py --port 28808 &

log "Starting code_reviewer       on :28807"
python code_reviewer/main.py --port 28807 &

log "Starting travel_planner      on :28090"
PORT=28090 python travel_planner/main.py &

log "Starting newsletter          on :28793"
python newsletter/main.py --port 28793 &

log "Starting drop_summarizer     on :28794"
python drop_summarizer/main.py --port 28794 &

log "Starting voice_journal       on :28799"
python voice_journal/main.py --port 28799 &

log "Starting smart_todo          on :28800"
python smart_todo/main.py --port 28800 &

log "Starting server_monitor      on :28767"
python server_monitor/main.py --port 28767 &

log "Starting stock_alert         on :28801"
python stock_alert/main.py --port 28801 &

log "Starting video_qa            on :28766"
python video_qa/run.py --web --port 28766 &

log "Starting deck_forge          on :28802"
python deck_forge/main.py --port 28802 &

log "Starting youtube_research    on :28803"
python youtube_research/main.py --port 28803 &

log "Starting arch_diagram        on :28804"
python arch_diagram/main.py --port 28804 &

log "Starting hiking_research     on :28805"
python hiking_research/main.py --port 28805 &

log "Starting movie_recommender   on :28806"
python movie_recommender/main.py --port 28806 &

log "Starting webpage_summarizer  on :28071"
python webpage_summarizer/main.py --port 28071 &

log "Starting wiki_dive           on :28809"
python wiki_dive/main.py --port 28809 &

log "Starting box_qa              on :28810"
python box_qa/main.py --port 28810 &

log "Starting api_doc_gen         on :28811"
python api_doc_gen/main.py --port 28811 &

log "Starting ibm_cloud_advisor   on :28812"
python ibm_cloud_advisor/main.py --port 28812 &

log "Starting ibm_docs_qa         on :28813"
python ibm_docs_qa/main.py --port 28813 &

log "Starting ibm_whats_new       on :28814"
python ibm_whats_new/main.py --port 28814 &

log "Starting bird_invocable_api_creator on :28815"
python bird_invocable_api_creator/main.py --port 28815 &

log "Starting brief_budget        on :28816"
python brief_budget/main.py --port 28816 &

log "Starting trip_designer       on :28817"
python trip_designer/main.py --port 28817 &

log "Starting recipe_composer     on :28820"
python recipe_composer/main.py --port 28820 &

log "Starting city_beat           on :28821"
python city_beat/main.py --port 28821 &

# code_engine_deployer is local-only — needs host docker + ibmcloud CLI +
# user's IBM auth. Run it from your workstation: `python code_engine_deployer/main.py --port 28818`.

log "All 28 apps launched. Waiting..."
wait
