# DeckForge — AI Presentation Builder

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

Generate slide decks from a folder of source documents.

**MCP servers consumed:** _none — all tools stay inline (see below)._

**Inline `@tool` defs (kept local because they touch app-specific state):** `list_directory` · `extract_and_index` · `search_knowledge_base` · `add_slide` · `finalize`

<!-- END: MCP usage -->

Generate polished presentation decks from a local folder of documents, PDFs, slides, and recordings.  The agent does all the heavy lifting — you supply a directory and a topic.

---

## Quick Start

```bash
python main.py --port 28802

# Or via launch.py from the apps/ directory
python ../launch.py start deck_forge
```

Open `http://localhost:28802`, enter a folder path and topic, hit **Generate Deck**.

---

## Architecture

```
                        ┌────────────────────────────────────┐
     Browser            │           FastAPI (main.py)         │
  ─────────────         │                                      │
  POST /api/generate ──►│  creates DeckForgeSession           │
  GET  /api/stream   ◄──│  streams SSE progress events        │
  GET  /api/download ◄──│  serves output files                │
                        └──────────────┬─────────────────────┘
                                       │ asyncio.create_task
                                       ▼
                        ┌─────────────────────────────────────┐
                        │     LangGraph ReAct Agent            │
                        │         (agent.py)                   │
                        │                                      │
                        │  ┌───────────────────────────────┐  │
                        │  │  system prompt + user goal    │  │
                        │  └──────────────┬────────────────┘  │
                        │                 │  ReAct loop        │
                        │  ┌──────────────▼────────────────┐  │
                        │  │   Tool calls (async)          │  │
                        │  │                               │  │
                        │  │  list_directory()             │  │
                        │  │  extract_and_index()          │  │
                        │  │  search_knowledge_base()      │  │
                        │  │  add_slide()                  │  │
                        │  │  finalize()                   │  │
                        │  └──────────────┬────────────────┘  │
                        └─────────────────│────────────────────┘
                                          │ progress events
                                          ▼
                        ┌─────────────────────────────────────┐
                        │          session.queue              │
                        │      (asyncio.Queue per run)        │
                        └─────────────────────────────────────┘
```

### RAG Flow

```
  Source file
       │
       │  extract_and_index()
       ▼
  extractors.py ──► raw text
       │
       │  KnowledgeBase.add_document()
       ▼
  rag.py
  ┌────────────────────────────────────┐
  │  chunk text (400 words, 80 overlap)│
  │  embed with all-MiniLM-L6-v2      │
  │  store in ChromaDB (in-memory)    │
  └────────────────────────────────────┘
       │
       │  search_knowledge_base(query)
       ▼
  top-k chunks + sources + scores ──► agent reasoning ──► slide bullets
```

### Agent Process

The agent follows a deterministic 6-step process encoded in the system prompt:

| Step | Action | Tool |
|------|--------|------|
| DISCOVER | List and classify all files | `list_directory` |
| INGEST | Extract text and index each file | `extract_and_index` |
| ASSESS | Broad searches to gauge content | `search_knowledge_base` |
| STRUCTURE | Plan narrative arc (in-context reasoning) | — |
| BUILD | Per-slide focused search + slide creation | `search_knowledge_base` + `add_slide` |
| FINALIZE | Write PPTX + MD to disk | `finalize` |

### Supported Input Formats

| Extension | Extractor |
|-----------|-----------|
| `.pdf` | pdfplumber |
| `.pptx` / `.ppt` | python-pptx |
| `.md` / `.markdown` | plain text |
| `.txt` / `.rst` | plain text |
| `.mp3` / `.wav` / `.m4a` | faster-whisper (Whisper base) |
| `.mp4` / `.webm` / `.mov` | faster-whisper (audio track) |

### Output

Each generation run creates `outputs/{session_id}/`:
```
outputs/
└── a3f8b2c1/
    ├── deck.pptx   ← 16:9 widescreen presentation (navy theme)
    └── deck.md     ← structured Markdown text report
```

---

## File Structure

```
deck_forge/
├── main.py          FastAPI app: HTTP API + SSE streaming
├── agent.py         LangGraph ReAct agent + async tool definitions
├── session.py       DeckForgeSession dataclass (per-request state)
├── extractors.py    PDF / PPTX / MD / audio text extraction
├── rag.py           ChromaDB knowledge base with sentence-transformer embeddings
├── deck_writer.py   python-pptx PPTX builder + Markdown writer
├── static/
│   └── index.html   Single-page frontend (SSE progress, download links)
├── tests/
│   └── test_e2e.py  E2E integration test with auto-generated fixtures
└── outputs/         Created at runtime; one subdirectory per session
```

---

## Agent vs Application: Division of Responsibility

**The application (main.py) is intentionally thin:**
- Accepts two inputs: directory path + topic
- Creates a session with a progress queue
- Kicks off `asyncio.create_task(run_agent(session))`
- Serves SSE events and output file downloads

**The agent owns all content decisions:**
- Which files are relevant to the topic (may skip unrelated files)
- Extraction order (e.g., READMEs first for context orientation)
- Narrative structure (number of slides, section titles, arc)
- What content goes on each slide (via targeted RAG queries)
- Deduplication and synthesis across sources

---

## Adding the CugaAgent

The `generate()` endpoint already accepts `agent_type: "cuga"`.  To wire it up:

1. In `agent.py`, add `build_cuga_agent(session, llm)` that wraps the same tool list.
2. In `main.py`'s `_run()`, branch on `req.agent_type`.
3. The UI's CugaAgent button activates automatically when the backend supports it.

---

## Running the E2E Test

```bash
# Run all tests (unit + integration)
python -m pytest tests/test_e2e.py -v

# Run only unit tests (no LLM required)
python -m pytest tests/test_e2e.py -v -k "not E2E"

# Run only the E2E pipeline (requires LLM key)
python -m pytest tests/test_e2e.py -v -k "E2E"
```

The test auto-generates fixture files.  If network is available, it also downloads the "Attention Is All You Need" arxiv paper as a real PDF to test PDF extraction.

---

## Environment Variables

DeckForge inherits the shared LLM config from `_llm.py`:

| Variable | Provider |
|----------|----------|
| `RITS_API_KEY` | IBM RITS (default priority) |
| `ANTHROPIC_API_KEY` | Anthropic Claude |
| `OPENAI_API_KEY` | OpenAI |
| `WATSONX_APIKEY` | IBM WatsonX |
| `LLM_PROVIDER` | Override auto-detection |
| `LLM_MODEL` | Override default model |
