# Cuga adapter

Thin FastAPI service that wraps an in-process `CugaAgent` and exposes it over
HTTP at `/chat`. Chief of Staff's orchestrator only ever talks to the
adapter — it never imports `cuga.sdk` directly. That HTTP boundary is what
makes the planner backend swappable.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | adapter status + loaded tool count |
| `GET` | `/tools` | live tool catalog |
| `POST` | `/chat` | `{message, thread_id}` → `{response, thread_id, error}` |

## Run

The adapter assumes the **cuga-apps Python environment** is active — i.e.
`cuga.sdk`, `langchain`, `langchain-mcp-adapters` are importable. That's the
same env your existing `apps/*` use. The MCP servers under `mcp_servers/*`
must also be running (start them via `python apps/launch.py`).

```bash
# from cuga-apps/
uvicorn chief_of_staff.adapters.cuga.server:app --port 8000
```

## Configuration

| Env var | Default | Notes |
|---|---|---|
| `MCP_SERVERS` | `web,knowledge,geo,finance,code,local,text,invocable_apis` | Comma-separated subset |
| `LLM_PROVIDER` | auto-detected | Same as `apps/_llm.py` (rits, anthropic, openai, etc.) |
| `OPENAI_API_KEY` | placeholder if unset | CUGAAgent validates this internally |

## Replacing cuga

Drop a sibling directory next to this one (e.g. `adapters/gpt_oss/server.py`)
that exposes the same three endpoints, then point chief_of_staff at it via
`CUGA_URL=http://localhost:<port>`. No changes to `chief_of_staff/backend/`.
