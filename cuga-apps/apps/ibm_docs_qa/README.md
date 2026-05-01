# IBM Docs Q&A

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

Q&A over IBM Cloud / IBM product docs (web search + page fetch).

**MCP servers consumed:**
- **mcp-web** — `web_search` · `fetch_webpage`

**Inline `@tool` defs:** none — every tool comes from MCP.

<!-- END: MCP usage -->

A FastAPI app that answers IBM Cloud questions by searching real IBM
documentation and synthesising sourced answers.

**Port:** 28813 → http://localhost:28813

## How it works

1. The user types a question.
2. The agent calls `web_search` (mcp-web, Tavily) with `site:ibm.com OR site:cloud.ibm.com` appended to the query.
3. For each promising hit, it calls `fetch_webpage` to read the full page.
4. It synthesises a precise answer with cited source links.

## Run

```bash
python main.py --port 28813
# open http://127.0.0.1:28813
```

Required env: `LLM_PROVIDER`, `LLM_MODEL`, `TAVILY_API_KEY` (consumed by mcp-web).
