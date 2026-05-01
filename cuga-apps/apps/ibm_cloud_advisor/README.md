# IBM Cloud Architecture Advisor

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

Recommend IBM services from natural-language requirements.

**MCP servers consumed:**
- **mcp-web** — `web_search`

**Inline `@tool` defs (kept local because they touch app-specific state):** `search_ibm_catalog`

<!-- END: MCP usage -->

A FastAPI app that recommends IBM Cloud services for a described use case,
explains how they connect, and provides `ibmcloud` CLI commands.

**Port:** 28812 → http://localhost:28812

## How it works

1. User describes what they want to build (e.g. "real-time order processing").
2. The agent calls `search_ibm_catalog` (inline) — IBM Cloud Global Catalog —
   to find services that match each capability.
3. The agent calls `web_search` (mcp-web) with `site:ibm.com OR site:cloud.ibm.com`
   for architecture patterns and pricing comparisons.
4. It returns 3-7 candidate services with role, integration sketch, and CLI provisioning.

## Run

```bash
python main.py --port 28812
# open http://127.0.0.1:28812
```

Required env: `LLM_PROVIDER`, `LLM_MODEL`, `TAVILY_API_KEY` (consumed by mcp-web).
