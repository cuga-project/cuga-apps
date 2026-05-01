# Trip Designer

A travel-itinerary planner with a deliberately **light, goal-shaped system
prompt** — under 30 lines, prescribes nothing about workflow or tool order.
The agent decides its own decomposition; the UI streams the plan and tool
calls live so you can see what it chose and why.

**Port:** 28817 → http://localhost:28817

---

## Why this exists

The existing `travel_planner` app prescribes a 6-step workflow in its system
prompt — Wikipedia → weather → geocode → attractions → web → write itinerary.
That works, but it absorbs the planner's job: the agent just executes a script.

This app strips the prescription out and asks CUGA to plan. Same domain, same
MCP tools, same input shape — but the agent has to **decide**:

- How to decompose the task (days × themes? geographic zones? practicalities
  vs experiences?).
- Which tools to call for which sub-task.
- The order of investigation.
- The final itinerary's shape.

The full system prompt is in [main.py](main.py) under `_SYSTEM`. It's
~25 lines and contains exactly two requirements (call `propose_plan` first;
cite real sources) plus one constraint clarification.

## What you'll see

1. **Plan panel** — populates within a few seconds with the agent's
   self-chosen decomposition. If it replans mid-flight, you'll see a `v2`
   plan card appear at the top with the older plan(s) below.
2. **Tool calls** — each call streams in real-time, color-coded by family
   (geo, encyclopedic, web). No budget — the agent calls what it needs.
3. **Itinerary** — renders as markdown when synthesis finishes.

## Run

```bash
python main.py --port 28817
# open http://127.0.0.1:28817
```

Or via Docker:

```bash
docker compose build apps && docker compose up -d apps
open http://localhost:28817
```

## Inputs

| Field | Required | Notes |
|---|---|---|
| Destination | yes | "Berlin", "Kyoto", "Lisbon" |
| Days | yes | int |
| Month | recommended | for weather + seasonality |
| Origin city | optional | influences flight/transit hints |
| Interests | optional | comma-separated; what the agent should weight |
| Travel style | optional | budget / mid-range / luxury / backpacker / family |
| Hard constraints | optional | natural language — *"must end at airport by 3pm Friday", "max 30 min between activities", "vegetarian only"* |

## Environment variables

| Var | Required | Description |
|---|---|---|
| `LLM_PROVIDER`, `LLM_MODEL` | yes | LLM backend |
| `AGENT_SETTING_CONFIG` | yes (defaulted) | per-provider TOML |
| `TAVILY_API_KEY` | optional | improves `web_search` |
| `OPENTRIPMAP_API_KEY` | optional | improves `search_attractions` |

## API surface

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/run` | start a session — body: trip details → `{session_id}` |
| `GET`  | `/api/stream/{session_id}` | SSE — `init`, `plan`, `tool_call`, `tool_result`, `itinerary`, `done`, `error` |
| `GET`  | `/api/result/{session_id}` | full session snapshot |
| `GET`  | `/health` | liveness |
| `GET`  | `/` | UI |

## Compare to `travel_planner`

| Aspect | `travel_planner` | `trip_designer` |
|---|---|---|
| System prompt | ~30 lines, fully procedural (6 prescribed tool calls in fixed order) | ~25 lines, only two rules: plan first, cite real sources |
| Workflow | hardcoded in prompt | agent's choice |
| Decomposition | implicit (the prompt is the decomposition) | explicit, visible in `propose_plan` output |
| Replanning | not supported by prompt | first-class — agent can call `propose_plan` again at any time |
| Live plan visibility | none | SSE-streamed plan panel + tool log |
| Backend | CUGA + LangGraph ReAct (interchangeable) | CUGA only — exercises planner subagent |

## A/B with `travel_planner`

Both apps accept the same kind of input. To compare them on a query:

1. Open http://localhost:28090 (travel_planner) — enter a destination + days.
2. Open http://localhost:28817 (trip_designer) — same destination + days.
3. Watch how each agent handles the work. trip_designer's plan + tool log
   panels show what it decided; travel_planner just runs through its script.

For a contrast slide, the question is: does giving the agent freedom to plan
produce a better itinerary? Or does the unstructured prompt result in
inconsistent / unreliable behavior? That's the experiment this app exists to
run.

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

Travel itinerary planner with a goal-shaped prompt; CUGA owns the workflow.

**MCP servers consumed:**
- **mcp-web** — `web_search` · `fetch_webpage` · `fetch_webpage_links` · feed/youtube tools
- **mcp-knowledge** — `search_wikipedia` · `get_wikipedia_article` · `get_article_*` · `get_related_articles` · `search_arxiv` · `search_semantic_scholar`
- **mcp-geo** — `geocode` · `find_hikes` · `search_attractions` · `get_weather`

**Inline `@tool` defs:** `propose_plan` (free; records the agent's plan).
Plus a wrapper around every MCP tool that streams `tool_call` + `tool_result`
events to the UI.

<!-- END: MCP usage -->
