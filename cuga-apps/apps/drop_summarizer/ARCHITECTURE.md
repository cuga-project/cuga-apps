# Drop Summarizer — Architecture

## Design principle

**The app handles all state, I/O, and side effects. The agent handles text.**

Nothing that can be done without an LLM is delegated to the agent. The agent
does not read files, send emails, query the database, or poll directories.
It receives extracted text and returns a summary or an answer.

---

## Component map

```
┌─────────────────────────────────────────────────────────────────┐
│  App layer (main.py)                                            │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │ asyncio      │    │  _extract_   │    │  summaries.db    │  │
│  │ watcher loop │───▶│  content()   │    │  (SQLite)        │  │
│  │ polls inbox  │    │  txt/md: read│    │  filename        │  │
│  └──────────────┘    │  pdf/img:    │    │  summary         │  │
│         │            │  docling     │    │  content (full)  │  │
│         │            └──────┬───────┘    │  alerted         │  │
│         │                   │            └────────┬─────────┘  │
│         │                   ▼                     │            │
│         │            ┌──────────────┐             │            │
│         │            │  CugaAgent   │             │            │
│         │            │  (no tools)  │             │            │
│         │            │  summarize   │─────────────┘            │
│         │            └──────────────┘  store summary+content   │
│         │                                                       │
│         ▼                                                       │
│  keyword match? ──yes──▶ smtplib email (no LLM)                │
│                                                                 │
│  ┌──────────────────────────────────────────────┐              │
│  │  FastAPI web UI                              │              │
│  │  /upload  → save to inbox                   │              │
│  │  /ask     → inject full content → CugaAgent │              │
│  │  /summaries → read SQLite                   │              │
│  │  /settings  → read/write .store.json        │              │
│  └──────────────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

---

## What the app owns

| Responsibility | How |
|---|---|
| File detection | asyncio loop, `pathlib.iterdir()` |
| Content extraction | `_extract_content()` — docling or plain read |
| Storage | SQLite via stdlib `sqlite3` |
| Keyword alerting | String matching on summary, `smtplib` for delivery |
| Settings persistence | `.store.json` via `json` stdlib |
| Web UI | FastAPI + inline HTML |
| Q&A context injection | Fetches full content from SQLite, prepends to prompt |

## What CugaAgent owns

| Responsibility | How |
|---|---|
| Summarization | Agent receives extracted text, returns markdown summary |
| File Q&A | Agent receives full content + question, returns answer |
| General Q&A | Agent receives recent summaries as context, returns answer |

---

## Agent configuration

```python
CugaAgent(
    model   = create_llm(...),
    tools   = [],                          # no tools
    plugins = [CugaSkillsPlugin(...)],     # summarizer.md skill
)
```

The agent does not need tools because extraction happens before the agent is
called. The app passes text; the agent returns text.

---

## Data flow for a new file

```
1.  File appears in ./inbox/filename.pdf
2.  Watcher moves it to ./inbox/processed/filename.pdf  (prevents reprocessing)
3.  App: content = _extract_content(dest)
          → docling runs, returns markdown
4.  Agent: summary = await agent.invoke(f"Summarize:\n\n{content[:12000]}")
5.  App: keyword_match = any(kw in summary for kw in alert_keywords)
6.  App: if keyword_match → smtplib.send_email(summary)
7.  App: db.insert(filename, summary, content)
8.  Browser feed auto-refreshes every 10s → card appears
```

## Data flow for a focused Q&A

```
1.  User clicks "Focus" on a summary card
2.  Browser: POST /ask { question, filename }
3.  App: content = db.get_content(filename)   ← full stored content
4.  Agent: answer = await agent.invoke(
              f"File: {filename}\nFull content:\n{content[:16000]}\n\nQ: {question}"
            )
5.  Browser: display answer
```

---

## Why content is stored in the DB

The original file is moved to `./inbox/processed/` after ingestion. The DB is
the durable store. Q&A needs the full extracted text, not just the summary —
so both are stored on ingestion. This means Q&A works correctly even after the
app restarts, and the original file is no longer required.

---

## What docling provides

For PDF and image files, docling runs locally and returns markdown that preserves:
- Tables (converted to markdown table syntax)
- Headings and structure
- OCR text from images / scanned pages

For plain text and markdown, `Path.read_text()` is used directly — docling is
not invoked.
