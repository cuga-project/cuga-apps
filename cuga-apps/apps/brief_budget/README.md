# Brief Budget

A research-brief generator on a hard tool-call budget. Designed to **exercise
CUGA's planner** — the system prompt is goal-shaped (no prescribed sub-topics
or tool order); the agent must decide its own decomposition, allocate budget,
execute, and replan when needed.

**Port:** 28816 → http://localhost:28816

---

## What it does

You give it:
- A research question (e.g. *"What's the state of MoE architectures in LLMs?"*).
- A hard tool-call budget (5–40, default 15).

The agent:
1. Calls **`propose_plan`** first — a free tool that just records the agent's
   plan. The UI renders it live as soon as it lands.
2. Executes the plan by calling MCP tools (web, knowledge). Each non-plan
   call decrements the budget.
3. Replans if a sub-topic dries up.
4. Synthesizes a structured brief with citations.

Plan + every tool call streams to the UI over SSE so the planner's work is
visible end-to-end.

## Why this exists

Every other app in the cuga-apps lineup uses a **procedural** system prompt
("step 1 do X, step 2 do Y") which absorbs the planner's job. This one
deliberately doesn't:

- **No prescribed sub-topics** — the agent decomposes per question.
- **No prescribed tool order** — the agent picks per sub-topic.
- **A hard budget** — forces the agent to allocate before executing,
  not just react.

Result: the planner has actual decomposition work to do, and you can watch
it do it.

## Run

```bash
python main.py --port 28816
# open http://127.0.0.1:28816
```

Or via Docker, just rebuild the apps image and bring it up:

```bash
docker compose build apps && docker compose up -d apps
open http://localhost:28816
```

## Environment variables

| Var | Required | Description |
|---|---|---|
| `LLM_PROVIDER` | yes | `rits` \| `anthropic` \| `openai` \| `watsonx` \| `litellm` \| `ollama` |
| `LLM_MODEL` | yes | model name |
| `AGENT_SETTING_CONFIG` | yes (defaulted) | CUGA settings TOML; defaulted per-provider in `make_agent()` |
| `TAVILY_API_KEY` | optional | improves `web_search` quality (mcp-web fallback otherwise) |

## Example questions

- *"What's the state of MoE architectures in LLMs?"*
- *"Compare the major RAG benchmarks of 2025–2026."*
- *"Open problems in agent observability."*
- *"Recent advances in LoRA fine-tuning of code models."*
- *"How are AI agents being applied to bug triage?"*

## API surface

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/run` | start a brief — body: `{question, budget}` → `{session_id}` |
| `GET`  | `/api/stream/{session_id}` | SSE event stream — `init`, `plan`, `tool_call`, `tool_result`, `brief`, `done`, `error` |
| `GET`  | `/api/result/{session_id}` | full result snapshot (plan history, tool calls, brief) |
| `GET`  | `/health` | liveness |
| `GET`  | `/` | UI |

## Architecture

```
Browser
   │  POST /api/run {question, budget}
   ▼
FastAPI ──► BriefSession (id, budget counter, queue)
   │             │
   │             ▼
   │       asyncio.create_task( _execute(session) )
   │             │
   │             ▼
   │       CugaAgent + tools
   │       ┌──────────────────────────────────────┐
   │       │ propose_plan       — free, records   │
   │       │ web/knowledge MCP  — wrapped:        │
   │       │   each call decrements session.used  │
   │       │   emits SSE events to session.queue  │
   │       └──────────────────────────────────────┘
   │
   ▼
GET /api/stream/{id}  ──►  EventSource ──►  UI updates
                            (plan, tool_call, tool_result,
                             budget_exhausted, brief, done)
```

The system prompt prescribes the meta-process (plan → execute → replan →
synthesize) but **deliberately does not** prescribe sub-topics or tool order
per sub-topic. That's the planner's job. See [main.py](main.py) `_SYSTEM`.

## What you'll see

When you click Generate brief on a question:

1. **Plan panel** populates within a few seconds with the agent's
   decomposition, budget split, and tool plan per sub-topic.
2. **Tool calls** stream in below — each row shows tool name, args, and a
   running `used / budget` counter. Color-coded by tool family (academic,
   encyclopedic, web).
3. **Brief** renders at the bottom when synthesis finishes — sub-topic
   sections, bulleted findings with citations, and a budget tally.

If the agent revises mid-flight, you'll see a new "v2" plan card appear at
the top, with the older plan(s) below.

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

Research brief generator on a hard tool-call budget; planner-driven.

**MCP servers consumed:**
- **mcp-web** — `web_search` · `fetch_webpage` · `fetch_webpage_links` ·
  `fetch_feed` · `search_feeds` · `get_youtube_video_info` · `get_youtube_transcript`
- **mcp-knowledge** — `search_arxiv` · `get_arxiv_paper` · `search_semantic_scholar` ·
  `get_paper_references` · `search_wikipedia` · `get_wikipedia_article` ·
  `get_article_summary` · `get_article_sections` · `get_related_articles`

**Inline `@tool` defs:** `propose_plan` (free; records the agent's plan). Plus a
budget-aware wrapper around every MCP tool that decrements `session.used` and
emits an SSE event per call.

<!-- END: MCP usage -->
