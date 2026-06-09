---
name: newsletter
description: Fetch RSS / Atom feeds the user supplies, optionally filter by keywords, and produce a digest of recent items with links. Use when the user names feed URLs and asks for a "digest", "what's new in my feeds", or wants keyword-filtered headlines.
requirements:
  - feedparser>=6.0
examples:
  - "Digest these feeds: https://hnrss.org/frontpage, https://www.theverge.com/rss/index.xml"
  - "Latest items from https://blog.langchain.dev/rss/ — filter for 'agents' or 'rag'"
  - "Watchlist of feeds — show me items mentioning 'kubernetes' across them"
  - "What's new in https://anthropic.com/news/rss?"
---

# Newsletter — RSS feed digest

You produce digests from RSS / Atom feeds the user supplies. Two
modes: **single feed** ("what's new in this feed?") or
**multi-feed keyword filter** ("show me items mentioning &lt;X&gt;
across these feeds").

A companion script — `scripts/feed_tools.py` — exposes two
subcommands: `fetch_feed` (single feed) and `search_feeds` (many
feeds, keyword-filtered). Uses `feedparser` (declared in this
skill's `requirements`) to handle the messy world of real-world feeds.

This skill is the **read/digest** half of the original `newsletter`
app, not the cron + email watchdog.

## When to use this skill

Trigger on any request that involves:

- "Digest / summarise / latest items from &lt;feed URL&gt;"
- "What's new in &lt;feed&gt;"
- "&lt;Multiple feeds&gt; — items mentioning &lt;keyword&gt;"
- A pasted list of feed URLs with no other ask — assume "digest each"
- Keywords + feed URLs combined

For ad-hoc web research (no specific feed URLs), prefer
`web_researcher`. For a single arbitrary webpage, prefer
`webpage_summarizer`.

## Setup

`feedparser` is declared in this skill's `requirements:` — most hosts
auto-install it on `load_skill`. If your host doesn't honour
`requirements:`, install with `pip install feedparser>=6.0` or
`uv pip install feedparser>=6.0` before running.

## Tools provided

| Subcommand | Purpose | Returns |
| --- | --- | --- |
| `fetch_feed <url> [max_items=20]` | Fetch and parse one RSS/Atom feed. Returns title + recent entries. | `{feed_title, items: [{title, link, summary, published}, ...]}` |
| `search_feeds <feed_urls_csv> <keywords_csv> [max_per_feed=50]` | Fetch multiple feeds, keep only entries whose title or summary matches any keyword (case-insensitive). | `{matches: [{feed, title, link, summary, published}, ...], count}` |

`feed_urls_csv` is a comma-separated list of feed URLs. `keywords_csv`
is a comma-separated list of keywords. Both `search_feeds` arguments
are quoted as a single shell argument.

### Example invocation

```
python scripts/feed_tools.py fetch_feed 'https://hnrss.org/frontpage' 15

python scripts/feed_tools.py search_feeds \
  'https://blog.langchain.dev/rss/,https://anthropic.com/news/rss' \
  'agents,rag,reasoning' 50
```

## Workflow

### Single-feed digest

1. `fetch_feed(url, max_items=15)` — pull recent items.
2. If the feed errors (404, malformed XML), surface it plainly.
3. Group items by date (today / this week / older). Drop items older
   than 30 days unless the user asked for older content.
4. Reply in the format below.

### Multi-feed keyword filter

1. `search_feeds(feed_urls_csv, keywords_csv, max_per_feed=50)` —
   filter all feeds in one call.
2. The result is a flat list of matches across all feeds. Group by
   feed in your reply so the user sees which sources are surfacing
   what.
3. If the result is empty, say so plainly and offer to broaden
   keywords or fetch the feeds unfiltered.

## Output format

### Single feed

```
**<Feed title>** — <feed_url>

**Today** (or "Recent" if no clear "today")
- [<item title>](<link>) — <one-line summary>
- ...

**This week**
- [<item title>](<link>) — ...
- ...

**Older** (last 30 days, optional)
- ...
```

Cap each section at ~6 items. End with a one-line takeaway about the
feed's overall direction this week ("Heavy on agents and tool-use
this week"; "Quiet stretch — only 2 posts").

### Multi-feed keyword filter

```
**Keyword digest** — feeds: <N>; keywords: <list>; matches: <count>

### <Feed name 1>
- [<item title>](<link>) — <published date> — <one-line context>
- ...

### <Feed name 2>
- [<item title>](<link>) — ...
- ...
```

Order feeds by match count (most-matching first). Within each feed,
order items newest first.

## Tone & failure modes

- **Concise summaries** — one sentence per item, distilled from the
  RSS `summary` field if it's available; otherwise just the title.
- **Cite every item with a real `<link>`** from the feed. Don't
  fabricate URLs.
- If a feed fails to parse, surface the error for that feed and keep
  going for the others. Don't abort the whole digest because one feed
  is malformed.
- If `feedparser` isn't installed, the script returns an error
  pointing at the skill's `requirements:` — surface that to the user
  and stop.
- If a feed has no recent items (last 30 days), say "Quiet — no items
  in the last 30 days" rather than padding with old content.
- For keyword search with zero matches, suggest broader synonyms or
  removing the filter entirely.
- **No filler.** The user is here for headlines, not commentary.
- If your host has no way to execute the script, say so plainly.
  Without RSS access, this skill cannot answer feed questions.
