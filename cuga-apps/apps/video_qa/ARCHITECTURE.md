# Video Q&A — Architecture

## Design principle

**Everything that can be done deterministically stays in Python.
The agent only handles retrieval and reasoning — not transcription or indexing.**

Transcription (Whisper) and vector indexing (ChromaDB) are mechanical, cached
operations. There is no benefit to routing them through an LLM. The agent is
invoked once per question, not once per video.

---

## Component map

```
┌─────────────────────────────────────────────────────────────────┐
│  App layer                                                      │
│                                                                 │
│  run.py / agent.VideoQAAgent                                    │
│         │                                                       │
│         ▼                                                       │
│  transcriber.py                                                 │
│  ┌──────────────────────────────┐                               │
│  │ ffmpeg → extract audio       │  (skipped for .mp3/.wav)     │
│  │ faster-whisper → segments    │  cached in .cache/transcripts │
│  │ [{start, end, text}, ...]    │                               │
│  └──────────────┬───────────────┘                               │
│                 │                                               │
│                 ▼                                               │
│  index.py                                                       │
│  ┌──────────────────────────────┐                               │
│  │ sentence-transformers embed  │  cached in .cache/chroma      │
│  │ ChromaDB store               │                               │
│  └──────────────┬───────────────┘                               │
│                 │                                               │
│         (Phase 1 complete — no LLM used)                       │
│                                                                 │
│         User asks a question                                    │
│                 │                                               │
│                 ▼                                               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  CugaAgent                                               │   │
│  │                                                          │   │
│  │  tools:                                                  │   │
│  │    transcribe_video(path)   → calls transcriber+index   │   │
│  │    search_transcript(query) → ChromaDB cosine search    │   │
│  │    get_segment_at_time(sec) → lookup by timestamp       │   │
│  │                                                          │   │
│  │  skill: video_qa.md                                     │   │
│  │                                                          │   │
│  │  → answer with [MM:SS] timestamps                       │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## What the app owns

| Responsibility | Component | LLM? |
|---|---|---|
| Audio extraction | ffmpeg via `transcriber.py` | No |
| Transcription | faster-whisper via `transcriber.py` | No |
| Transcript caching | JSON files in `.cache/transcripts/` | No |
| Segment embedding | sentence-transformers via `index.py` | No |
| Vector storage + search | ChromaDB via `index.py` | No |
| Web UI | FastAPI + inline HTML in `run.py` | No |

## What CugaAgent owns

| Responsibility | How | LLM? |
|---|---|---|
| Deciding which segments to retrieve | `search_transcript` tool call | Yes |
| Composing timestamped answers | Agent reasoning over retrieved segments | Yes |
| Handling ambiguous queries | Multi-tool call — search + timestamp lookup | Yes |

---

## Agent configuration

```python
# agent.py
CugaAgent(
    model   = create_llm(...),
    tools   = [transcribe_video, search_transcript, get_segment_at_time],
    plugins = [CugaSkillsPlugin(...)],   # video_qa.md skill
)
```

## Agent tools

| Tool | Calls into | Returns |
|---|---|---|
| `transcribe_video(path, model_size)` | `transcriber.transcribe()` + `index.index_segments()` | `{segments_count, duration_fmt}` |
| `search_transcript(query, n_results)` | `index.search()` → ChromaDB | JSON array of `{text, start_fmt, end_fmt, distance}` |
| `get_segment_at_time(seconds)` | `index.get_at_time()` | `{text, start_fmt, end_fmt}` |

All tool implementations are pure Python calling local functions. No external APIs.

---

## Data flow for a question

```
1.  Video already transcribed and indexed (Phase 1 complete)

2.  User: "Where was M3 discussed?"

3.  agent.invoke("Where was M3 discussed?", thread_id="video-qa")
      → agent calls search_transcript("M3", n_results=6)
            → index.search("M3") → ChromaDB cosine similarity
            → returns top 6 segments: [{text: "M3 chip announced", start_fmt: "00:04", ...}, ...]
      → agent composes answer:
          "[00:04] M3 was introduced as the new chip family.
           [10:02–11:45] Benchmarks were compared with M2: 40% faster single-core..."

4.  Answer returned with timestamps
```

## Data flow for a timestamp query

```
1.  User: "What was said at the 30-minute mark?"

2.  agent calls get_segment_at_time(1800)
      → index.get_at_time(video_path, 1800.0, segments)
      → finds segment where start ≤ 1800 ≤ end
      → returns {text: "...the speaker described the roadmap...", start_fmt: "29:58", end_fmt: "30:14"}

3.  Agent: "At 29:58 the speaker said: '...'"
```

---

## Caching

Transcription is expensive (minutes for a long video). The app caches both levels:

| Cache | Location | Key |
|---|---|---|
| Raw transcript segments | `.cache/transcripts/{hash}_base.json` | SHA256 of file path + model size |
| ChromaDB vectors | `.cache/chroma/` | ChromaDB collection, keyed by segment metadata |

Delete `.cache/` to force full re-transcription.

---

## Why no CugaHost or channels

This is a synchronous, user-driven interaction. The user loads a file, asks
questions, gets answers. There is no background work to schedule, no events to
react to without the user present.

`CugaHost` and channels are appropriate when work should happen autonomously
(on a schedule, in response to file events, etc). For direct interactive Q&A,
they are unnecessary overhead. The `video_qa_new` variant adds pipeline mode
if folder watching is needed.
