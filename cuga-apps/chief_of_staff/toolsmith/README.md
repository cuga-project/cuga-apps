# Toolsmith service

The durable, LLM-driven acquisition agent. Listens on **port 8001**.

This is the brain that owns *building tools to fill gaps the planner
hits*. The cuga adapter is swappable; Toolsmith is the side that stays.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | service status + coder + LLM availability + artifact count |
| `POST` | `/acquire` | run the ReAct loop: `{gap}` → `{success, artifact_id, summary, transcript, artifact}` |
| `GET` | `/tools` | list installed artifacts (summaries) |
| `GET` | `/tools/{id}` | full artifact (manifest + code + last probe) |
| `DELETE` | `/tools/{id}` | remove an artifact |
| `GET` | `/specs/all_artifacts` | every artifact as `mcp_tool_spec` — used by backend to rebuild the cuga adapter's `extra_tools` |

## Configuration (env)

| Var | Default | Notes |
|---|---|---|
| `TOOLSMITH_LLM_PROVIDER` | `rits` | LLM for ReAct orchestration reasoning |
| `TOOLSMITH_LLM_MODEL` | `gpt-oss-120b` | same |
| `TOOLSMITH_CODER` | `gpt_oss` | `gpt_oss` or `claude` — the swappable Coder |
| `TOOLSMITH_CODER_PROVIDER` | falls back to `TOOLSMITH_LLM_PROVIDER` | only used by `LLMCoder` |
| `TOOLSMITH_CODER_MODEL` | falls back to `TOOLSMITH_LLM_MODEL` for gpt_oss; `claude-sonnet-4-6` for claude | |
| `ANTHROPIC_API_KEY` | unset | required iff `TOOLSMITH_CODER=claude` |
| `RITS_API_KEY` | unset | required iff using rits provider |
| `BACKEND_NOTIFY_URL` | `http://chief-of-staff-backend:8765/internal/artifacts_changed` | Toolsmith calls this when artifacts change |

## Internal architecture

```
Toolsmith service (this directory)
├── server.py        FastAPI front
├── agent.py         LangGraph ReAct agent
├── tools/build.py   Internal tool belt (NOT MCP — agent tools)
│   ├── search_catalog
│   ├── search_openapi_index
│   ├── describe_openapi_endpoint
│   ├── generate_tool_code        ← calls into Coder
│   ├── probe_generated_tool
│   ├── register_tool_artifact
│   ├── list_existing_tools
│   ├── remove_tool_artifact
│   └── check_secret_available
├── coders/
│   ├── base.py      CoderClient Protocol
│   ├── llm_coder.py LangChain BaseChatModel adapter (gpt-oss default)
│   └── claude_coder.py Anthropic Sonnet adapter
└── artifact.py      ToolArtifact + ArtifactStore (disk persistence)
```

## Tool format

Every tool Toolsmith ships is a **ToolArtifact** persisted to
`data/tools/<id>/`:

```
data/tools/openapi__get_country_by_name/
├── manifest.yaml   identity, parameters, provenance
├── tool.py         single async def — the entry point
└── probe.json      last probe result
```

The same artifact compiles to:
- a LangChain `StructuredTool` (cuga consumes this)
- an MCP tool spec (the cuga adapter mounts this via `/agent/reload`)
- a docs page (future)

## Replacing the Coder

Drop a new file in `coders/` that implements `CoderClient`, then set
`TOOLSMITH_CODER=<your_name>`. The whole rest of the system stays still.
