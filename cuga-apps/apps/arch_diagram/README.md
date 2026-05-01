# Architecture Diagram Generator

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

Mermaid diagrams generated from natural-language system descriptions.

**MCP servers consumed:**
- **mcp-web** — `web_search`

**Inline `@tool` defs:** none — every tool comes from MCP.

<!-- END: MCP usage -->

Describe a system in plain English, get a rendered architecture diagram.
The agent generates Mermaid.js code and the browser renders it as SVG.
Supports iterative refinement — ask the agent to modify the diagram
conversationally.

**Port:** 28804

---

## Division of Responsibilities

### The App (main.py)

- **Serves the web UI** — input panel, diagram renderer, history (FastAPI)
- **Renders diagrams** — Mermaid.js runs client-side, converting code to SVG
- **Persists diagram log** — SQLite database of past queries, responses, and Mermaid code
- **Extracts Mermaid code** — regex-parses the agent's response to separate diagram from explanation

### CugaAgent

The agent handles all architecture reasoning: understanding the system
description, choosing the diagram type, generating valid Mermaid syntax,
and modifying diagrams iteratively.

| Invocation | Input | Output |
|---|---|---|
| New diagram | System description | Mermaid code + explanation |
| Modification | "Add a cache layer" | Updated Mermaid code + change notes |
| Research | Unfamiliar technology | web_search → then diagram |

### Agent Tools

| Tool | What it does | Key required |
|---|---|---|
| `web_search` | Tavily web search for researching unfamiliar systems | `TAVILY_API_KEY` (optional) |

### Diagram Types

The agent picks the best type automatically:

| Type | When used |
|---|---|
| `graph TD` / `graph LR` | System architecture, data flow |
| `sequenceDiagram` | Request/response flows over time |
| `erDiagram` | Database schema and relationships |
| `stateDiagram-v2` | Lifecycles and state transitions |

---

## Quick Start

```bash
pip install -r requirements.txt    # optional: tavily-python for web search
python main.py
# open http://127.0.0.1:28804
```

No API keys required for core functionality. Tavily key is optional for
researching unfamiliar systems before diagramming.

---

## How It Works

```
User: "Design a microservices e-commerce platform"
      │  POST /ask
      ▼
CugaAgent
      │  (decides: flowchart is best for this)
      │  (generates Mermaid code)
      ▼
Response:
  ┌─────────────────────────────────────────┐
  │ ```mermaid                              │
  │ graph TD                                │
  │   Client["Browser"] -->|HTTPS| GW[...] │
  │   ...                                   │
  │ ```                                     │
  │                                         │
  │ ## Components                           │
  │ - **API Gateway**: Routes requests...   │
  │ - **User Service**: Handles auth...     │
  └─────────────────────────────────────────┘
      │
      ▼
Frontend:
  - Extracts ```mermaid block via regex
  - Renders SVG via mermaid.js
  - Shows explanation below
  - Download SVG / Copy code buttons

User: "Add a Redis cache between the services and the database"
      │
      ▼
CugaAgent → updated Mermaid code with cache node added
```

---

## Environment Variables

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | `rits` \| `anthropic` \| `openai` \| `watsonx` \| `litellm` \| `ollama` |
| `LLM_MODEL` | Model name override |
| `TAVILY_API_KEY` | Optional — enables web search for researching systems |

---

## Files

| File | Purpose |
|---|---|
| `main.py` | Agent, web search tool, FastAPI server, inline HTML + mermaid.js UI |
| `skills/arch_diagram.md` | Agent instructions (reference copy; also inlined in main.py) |
| `requirements.txt` | Python dependencies (tavily-python only) |
| `diagrams.db` | SQLite log of past diagrams (created on first run) |
| `.store.json` | Persisted Tavily key (created on first save) |
