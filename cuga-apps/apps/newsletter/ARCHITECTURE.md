# Newsletter Intelligence — Architecture

## What kind of app this is

A **configurable RSS intelligence and alerting system**. Two modes share the same
agent and tools:

- **Query mode** — user asks a free-form question; the agent fetches live feed data
  and answers directly.
- **Alert mode** — scheduled monitors check feeds for keyword matches and email
  the user when hits are found.

The key design choice: **the app owns the schedule and delivery; the agent owns
the judgment**. The scheduler fires on a timer. The agent decides what's worth
surfacing.

---

## Division of labor

```
[Background scheduler]     fires every 60 seconds, checks alert schedules
      ↓
[CugaAgent]                fetches feeds, searches for keywords, writes summary
      ↓
[smtplib]                  sends email if agent response starts with "ALERT:"

[FastAPI]                  serves browser UI, handles query + management endpoints
```

The agent earns its place by:

1. **Understanding context** — not just "keyword found" but "3 papers about
   agentic AI, here's the most significant one"
2. **Filtering noise** — suppresses non-matches cleanly without emailing
3. **Answering free-form queries** — "compare these feeds", "what's trending"
   is not a rule, it's a question

---

## Files

| File | Purpose |
|---|---|
| `main.py` | Entry point — FastAPI web UI, background scheduler, email, store |
| `feeds.py` | LangChain tools: `fetch_feed`, `search_feeds` |
| `skills/newsletter_curation.md` | Agent instructions: tool usage, alert format, query format |
| `requirements.txt` | Python dependencies |

Legacy files (`chat.py`, `agent.py`, `host_factories.py`) from the previous
CugaHost-based architecture are preserved but not used.

---

## Agent tools

Provided by `feeds.make_feed_tools()`:

| Tool | What it does |
|---|---|
| `fetch_feed(url)` | Fetches and parses a single RSS/Atom feed — up to 20 items |
| `search_feeds(feed_urls, keywords)` | Searches across multiple feeds for keyword matches |

Both tools use `feedparser` — no API key required for standard RSS feeds.

---

## Persistent store — `.store.json`

```json
{
  "email":  { "host": "...", "user": "...", "password": "...", "to": "..." },
  "feeds":  ["https://arxiv.org/rss/cs.AI", "https://huggingface.co/blog/feed.xml"],
  "alerts": [
    {
      "id":       "a1b2c3d4",
      "keywords": "agentic AI",
      "schedule": "daily",
      "enabled":  true,
      "last_run": "2026-04-08T14:30:00+00:00"
    }
  ]
}
```

State is restored on startup — feeds, email config, and alerts all survive restarts.

---

## Alert data flow

```
_alert_scheduler (asyncio loop, sleeps 60s)
    → for each enabled alert with schedule "hourly" or "daily"
        → check elapsed time since last_run
        → if due:
            → _run_alert_now(agent, alert, feeds)
                → CugaAgent.invoke(
                    "Check feeds for: {keywords}. Start with ALERT: if found."
                  )
                → answer starts with "ALERT:"?
                    yes → _send_email(subject, answer)
                    no  → log "No matches" — no email
            → update last_run in .store.json
```

"On demand" alerts are never auto-run — only via the "Run Now" button.

---

## Query data flow

```
POST /ask  {question: "What's new in open source AI?"}
    → inject configured feed URLs into prompt
    → CugaAgent.invoke(prompt, thread_id="query")
        → fetch_feed / search_feeds (as needed)
        → answer
    → return {answer: "..."}
    → UI shows result + "Email this" button
```

All queries share `thread_id="query"` so follow-up questions have context.

---

## Why no CugaHost or pipelines

This app manages its own schedule (asyncio + sleep) and its own delivery
(smtplib directly). `CugaRuntime` and `CugaHost` are not needed:

- No multi-app routing — this is a single focused tool
- No channel abstraction — RSS and email are inlined in `feeds.py` and `main.py`
- No factory pattern — `make_agent()` is called once at startup

If you extended this to support multiple users with separate feed configs, or
wanted to run newsletter alongside other apps, `CugaHost` with registered apps
would make sense. For a single-instance demo, it's unnecessary overhead.

---

## Output

| Destination | When |
|---|---|
| Browser UI | Always — query results and alert log shown inline |
| Email (SMTP_SSL port 465) | When an alert fires and email is configured |
| Server log | Always — one-line summary of every alert run |
