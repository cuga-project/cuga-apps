"""
Port registry for the cuga-apps clone.

Single source of truth — all ports live here. Referenced by:
  - apps/launch.py          (per-app default_port)
  - start.sh                (via `python -c "from apps._ports import …"`)
  - mcp_servers/*/server.py (via MCP_*_PORT env or the constants below)
  - docker-compose.yml      (must be kept in sync manually — it's static YAML)
  - ui/src/data/usecases.ts (must be kept in sync manually — it's TypeScript)

Naming: all ports shifted to 28xxx (apps) / 29xxx (MCP servers) / 3001 (UI)
so the clone coexists with the original agent-apps stack.
"""
from __future__ import annotations

# ── UI ───────────────────────────────────────────────────────────
UI_PORT = 3001

# ── MCP servers (29100–29107) ────────────────────────────────────
MCP_WEB_PORT            = 29100
MCP_KNOWLEDGE_PORT      = 29101
MCP_GEO_PORT            = 29102
MCP_FINANCE_PORT        = 29103
MCP_CODE_PORT           = 29104
MCP_LOCAL_PORT          = 29105
MCP_TEXT_PORT           = 29106
MCP_INVOCABLE_APIS_PORT = 29107

MCP_PORTS: dict[str, int] = {
    "web":            MCP_WEB_PORT,
    "knowledge":      MCP_KNOWLEDGE_PORT,
    "geo":            MCP_GEO_PORT,
    "finance":        MCP_FINANCE_PORT,
    "code":           MCP_CODE_PORT,
    "local":          MCP_LOCAL_PORT,
    "text":           MCP_TEXT_PORT,
    "invocable_apis": MCP_INVOCABLE_APIS_PORT,
}

# ── Apps (28xxx) ─────────────────────────────────────────────────
# Original → New mapping: each old port + 10000, with collisions resolved.
APP_PORTS: dict[str, int] = {
    "newsletter":         28793,
    "drop_summarizer":    28794,
    "web_researcher":     28798,
    "voice_journal":      28799,
    "smart_todo":         28800,
    "server_monitor":     28767,
    "stock_alert":        28801,
    "video_qa":           28766,
    "travel_planner":     28090,
    "deck_forge":         28802,
    "youtube_research":   28803,
    "arch_diagram":       28804,
    "hiking_research":    28805,
    "movie_recommender":  28806,
    "webpage_summarizer": 28071,
    "code_reviewer":      28807,
    "paper_scout":        28808,
    "wiki_dive":          28809,
    "box_qa":             28810,
    "api_doc_gen":        28811,
    "ibm_cloud_advisor":  28812,
    "ibm_docs_qa":        28813,
    "ibm_whats_new":      28814,
    "bird_invocable_api_creator": 28815,
    "brief_budget":               28816,
    "trip_designer":              28817,
    "code_engine_deployer":       28818,
    "recipe_composer":            28820,
    "city_beat":                  28821,
}
