# Drop Summarizer

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

Watches a folder, extracts text via mcp-text, summarises with LLM.

**MCP servers consumed:**
- **mcp-text** — `extract_text`

**Inline `@tool` defs:** none — every tool comes from MCP.

<!-- END: MCP usage -->

Watches an inbox folder for new files. The agent uses tools to extract and summarize each file,
stores the result, and optionally triggers an email alert when the summary matches configured keywords.
Files can then be queried via chat.

**Port:** 28794  
**Supported file types:** `.txt`, `.md`, `.pdf`, `.png`, `.jpg`, `.jpeg`, `.tiff`, `.bmp`, `.gif`

---

## Division of Responsibilities

### The App (main.py)

- **Watches** the inbox folder — asyncio background loop polls every N seconds
- **Stores** both extracted content and the agent's summary in SQLite (`summaries.db`)
- **Checks keywords** against the summary and sends email alerts — no LLM involved
- **Serves the web UI** — upload, summary feed, chat, settings (FastAPI)
- **Persists settings** to `.store.json` (poll interval, watch dir, keywords, email config)

### CugaAgent

The agent has two tools and orchestrates its own extraction and Q&A.

| Tool | Purpose |
|---|---|
| `extract_document(file_path)` | Reads a file — plain text for `.txt`/`.md`, docling for PDF/images |
| `get_document_content(filename)` | Retrieves stored full content from SQLite for Q&A |

| Invocation | What the agent does |
|---|---|
| New file arrives | Calls `extract_document`, then summarizes |
| User asks about a file | Calls `get_document_content`, then answers |
| User asks generally | Receives recent summaries as context, answers directly |

### Agent Instructions

Summarization style and format rules are inlined as `special_instructions` in `make_agent()` inside `main.py`.

---

## Quick Start

```bash
pip install -r requirements.txt
python main.py
# open http://127.0.0.1:28794
```

For PDF and image support:
```bash
pip install docling
```

---

## How Files Flow Through the App

```
File lands in ./inbox/
       │
       ▼  (watcher polls every N seconds)
CugaAgent: extract_document(file_path)
       │  .txt/.md → read text
       │  .pdf/image → docling OCR/parse
       ▼
CugaAgent: summarize(content)
       │
       ▼
App: store { filename, summary, full_content } → SQLite
       │
       ▼
UI: summary card appears in feed
       │
       ▼  (user clicks "Focus" or filename)
CugaAgent: get_document_content(filename) → answer(question)
```

Email alert check runs after summarization — pure string matching, no LLM.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | — | `rits` \| `anthropic` \| `openai` \| `ollama` \| `watsonx` |
| `LLM_MODEL` | — | Model override |
| `WATCH_DIR` | `./inbox` | Folder to watch |
| `POLL_SECONDS` | `15` | Inbox poll interval |
| `SMTP_HOST` | `smtp.gmail.com` | SMTP server |
| `SMTP_USERNAME` | — | Sender email |
| `SMTP_PASSWORD` | — | App password |
| `ALERT_TO` | — | Alert recipient email |

---

## Files

| File | Purpose |
|---|---|
| `main.py` | Everything: watcher, tools, agent, FastAPI UI |
| `_SYSTEM` in `main.py` | Agent instructions — summary style and format (inlined) |
| `summaries.db` | SQLite — full content + summaries (created on first run) |
| `.store.json` | Persisted settings (created on first save) |
| `requirements.txt` | Python dependencies |
