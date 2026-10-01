# YouTube Research

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

Topic research via YouTube transcripts; URL-based summaries.

**MCP servers consumed:**
- **mcp-web** — `web_search` · `get_youtube_video_info` · `get_youtube_transcript`

**Inline `@tool` defs:** none — every tool comes from MCP.

<!-- END: MCP usage -->

Research any topic via YouTube: the agent finds relevant videos, fetches
their transcripts, and synthesises findings with citations and timestamps.
Or paste YouTube URLs directly for instant summaries.

**Port:** 28803

---

## Division of Responsibilities

### The App (main.py)

- **Serves the web UI** — chat panel, settings, research history (FastAPI)
- **Persists research log** — SQLite database of past queries and reports
- **Manages credentials** — Tavily key stored in `.store.json`

### CugaAgent

The agent handles all research logic: deciding what to search for, which
videos to select, fetching transcripts, and synthesising across sources.

| Invocation | Input | Output |
|---|---|---|
| Topic research | User topic (e.g. "RLHF") | Synthesis with citations from 3-5 videos |
| Direct URL(s) | YouTube link(s) + question | Summary with timestamps and key moments |

### Agent Tools

| Tool | What it does | Key required |
|---|---|---|
| `web_search` | Tavily web search to find YouTube videos | `TAVILY_API_KEY` |
| `get_video_info` | YouTube oEmbed metadata (title, channel) | No |
| `get_transcript` | Fetch video captions with timestamps | No |

---

## Quick Start

```bash
pip install -r requirements.txt
export TAVILY_API_KEY=your_key   # or set via the UI
python main.py
# open http://127.0.0.1:28803
```

## Try it

Once the app is open, type one of these into the chat box:

- Latest developments in AI agents
- How does RLHF work?
- Best practices for RAG pipelines
- https://youtube.com/watch?v=VIDEO_ID — summarise this video
- Compare what these creators say about fine-tuning: [url1] [url2]

---

## How It Works

### Topic Research Mode

```
User: "Latest developments in AI agents"
      │  POST /ask
      ▼
CugaAgent
      ├─ web_search("AI agents youtube 2026")
      ├─ web_search("AI agent frameworks explained site:youtube.com")
      │     → 8 results, 5 are YouTube links
      │
      ├─ get_video_info(url1) → "AI Agents Explained" by Channel A
      ├─ get_video_info(url2) → "Building AI Agents" by Channel B
      ├─ get_video_info(url3) → "Agent Frameworks 2026" by Channel C
      │
      ├─ get_transcript(url1) → timestamped transcript
      ├─ get_transcript(url2) → timestamped transcript
      ├─ get_transcript(url3) → transcript unavailable (skipped)
      │
      ▼
Synthesis organised by theme, with citations:
"Both Channel A ([12:30]) and Channel B ([08:15]) emphasise that..."
```

### Direct URL Mode

```
User: "https://youtube.com/watch?v=abc123 — summarise this"
      │  POST /ask
      ▼
CugaAgent
      ├─ get_video_info(url) → title, channel
      ├─ get_transcript(url) → timestamped transcript
      ▼
Summary with key moments and timestamps
```

---

## Environment Variables

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | `rits` \| `anthropic` \| `openai` \| `watsonx` \| `litellm` \| `ollama` |
| `LLM_MODEL` | Model name override |
| `TAVILY_API_KEY` | Required for topic research (web search) |

---

## Files

| File | Purpose |
|---|---|
| `main.py` | Agent, web search tool, FastAPI server, inline HTML UI |
| `youtube.py` | `make_youtube_tools()` — video info and transcript fetching |
| `skills/youtube_research.md` | Agent instructions (reference copy; also inlined in main.py) |
| `requirements.txt` | Python dependencies |
| `research.db` | SQLite log of past research (created on first run) |
| `.store.json` | Persisted Tavily key (created on first save) |
