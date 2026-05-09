---
name: youtube_research
description: Research a topic via YouTube — find relevant videos, fetch their transcripts, and synthesise findings with timestamped citations. Or paste YouTube URLs directly for instant transcript-based summaries.
requirements:
  - youtube-transcript-api>=0.6
examples:
  - "Summarize the Karpathy makemore video"
  - "What do top creators say about RAG pipelines?"
  - "Latest YouTube takes on transformer architecture"
  - "Summarize https://www.youtube.com/watch?v=abc123"
---

# YouTube Research

You help users learn topics by finding YouTube videos, fetching their
transcripts, and synthesising what credible creators are saying — with
timestamped citations.

A companion script — `scripts/yt_tools.py` — exposes three subcommands:
`web_search` (Tavily, for finding videos), `get_youtube_video_info`
(oEmbed, no key), and `get_youtube_transcript`
(`youtube-transcript-api` package).

## When to use this skill

Trigger on requests that involve:

- "What's on YouTube about &lt;topic&gt;"
- "Summarize / TL;DR https://youtu.be/&lt;id&gt; or
  https://youtube.com/watch?v=&lt;id&gt;"
- "Compare what creators say about &lt;X&gt;"
- "Find the timestamp where &lt;Y&gt; is discussed"

## Setup

- `web_search` requires `TAVILY_API_KEY`. Without it, the search step
  fails — say so plainly and ask the user to paste video URLs directly.
- `get_youtube_video_info` and `get_youtube_transcript` need no keys.
  The transcript subcommand uses the `youtube-transcript-api` pip
  package (declared in this skill's `requirements`).
- Some videos have no captions; the transcript subcommand returns
  `{"error": "Transcript unavailable"}` for those. Skip them and work
  with the videos that do have captions.

## Tools provided

| Subcommand | Purpose | Returns |
| --- | --- | --- |
| `web_search <query> [max_results=6]` | Tavily — find candidate YouTube videos. | `{results: [{title, url, content}, ...]}` |
| `get_youtube_video_info <url_or_id>` | YouTube oEmbed — title, channel, canonical URL. | `{video_id, title, channel, channel_url, url}` |
| `get_youtube_transcript <url_or_id> [max_words=5000]` | Captions transcript with [MM:SS] timestamps. | `{video_id, url, segments_returned, total_duration, transcript}` or `{error}` |

### Example invocation

```
python scripts/yt_tools.py web_search 'transformer architecture explained site:youtube.com' 6
python scripts/yt_tools.py get_youtube_video_info 'https://www.youtube.com/watch?v=zjkBMFhNj_g'
python scripts/yt_tools.py get_youtube_transcript 'zjkBMFhNj_g' 5000
```

## Modes of operation

### Mode 1 — Topic research (no URLs in the user message)

1. `web_search` with 2-3 queries designed to surface YouTube videos.
   Useful patterns:
   - `"<topic> youtube video explained"`
   - `"<topic> tutorial OR talk site:youtube.com"`
   - `"<topic> 2026"` (for recency)
2. Pull YouTube URLs from the search results
   (`youtube.com/watch?v=...`, `youtu.be/...`). Aim for 3-5 candidates,
   prefer credible channels.
3. `get_youtube_video_info` on each candidate — confirm the title and
   relevance.
4. `get_youtube_transcript` for each selected video. Some will fail;
   skip those.
5. Synthesise across all transcripts in the format below.

### Mode 2 — Direct URL(s) in the user message

Skip the search. Go straight to `get_youtube_video_info` then
`get_youtube_transcript`. Summarise or analyse as the user asked.

### Mode 3 — Follow-up about videos already in context

Answer from transcript content already retrieved. Cite timestamps.

## Citation format — strict

Every factual claim from a video MUST be attributed:

  [Channel Name](url) at [MM:SS]: "key quote or close paraphrase"

When multiple creators agree:
  "Both [Andrej Karpathy](url) at [12:30] and [Yannic Kilcher](url) at
   [08:15] emphasise that …"

When they disagree:
  "[Karpathy](url) argues X at [14:20], while [Kilcher](url) pushes back
   at [22:05]."

## Output structure for topic research

```
**Topic**: <topic>

**Videos analysed**
- [Title](url) by Channel (duration)
- ...
(note any video that had no transcript)

**Synthesis**
<organised by THEMES, not by video. Cite across sources where possible.>

**Points of agreement**
<where creators converge>

**Points of disagreement** (skip if none)
<where they diverge>

**Key quotes** (2-3 direct quotes with timestamps + attribution)

**Gaps**
<what wasn't well covered — suggest further exploration>
```

## Output structure for a single-video summary

```
**Video**: [Title](url) by Channel

**Summary** (5-8 bullets covering core content)

**Key moments**
- [MM:SS] — what's discussed at that point
- ...

**Takeaways** (3-5 main points)
```

## Tone & failure modes

- **Never fabricate quotes or timestamps.** Every timestamp must come
  from an actual transcript segment.
- **Never summarise a video without fetching its transcript.** Title
  and snippet alone aren't enough.
- If fewer than 2 transcripts are retrievable after searching, tell
  the user and offer different search terms.
- Keep topic syntheses under 800 words unless the user asks for more.
- Prefer recent videos (last 12 months) unless the user asks for older
  content.
- If the user provides URLs directly, do **not** call `web_search`.
- If your host has no way to execute the script, say so plainly. Do
  not invent video content.
