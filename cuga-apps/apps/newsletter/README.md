# Newsletter Intelligence

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

RSS/Atom feed digests, alerts on keyword matches, scheduled email.

**MCP servers consumed:**
- **mcp-web** — `fetch_feed` · `search_feeds`

**Inline `@tool` defs:** none — every tool comes from MCP.

<!-- END: MCP usage -->

Monitor RSS feeds, ask questions over live articles, and configure keyword
alerts that email you when matches are found.

```bash
python main.py
```

Then open **http://127.0.0.1:28793**

---

## UI

Two panels in the browser:

### Feed Query

Ask any question over your configured feeds. Quick chips for common queries.

```
Question: Summarize the latest AI research papers from my feeds
          Find anything about agentic AI or multi-agent systems
          What new LLM releases happened this week?
```

The agent fetches live feed data and answers in plain language.
Use the **Email this** button to send the response to your inbox.

### Scheduled Alerts

Configure keyword monitors that run on a schedule. When the agent finds
matching articles it emails you automatically.

```
Keywords: agentic AI    Schedule: Daily

[+ Add Alert]

● agentic AI  · daily  · last: Apr 8, 14:30   [Run Now] [Disable] [×]
● LLM release · hourly · last: Apr 8, 09:00   [Run Now] [Disable] [×]
```

Use **Run Now** to trigger any alert immediately regardless of schedule.
Recent outputs appear below the alert list.

---

## Getting started

### 1. Add RSS feeds (left panel)

Paste any RSS/Atom URL and click **+ Add**. Suggestions:

```
https://arxiv.org/rss/cs.AI
https://huggingface.co/blog/feed.xml
https://hnrss.org/newest?q=LLM
https://venturebeat.com/category/ai/feed/
https://www.technologyreview.com/feed/
```

Feeds are saved and restored on restart.

### 2. Configure email (left panel — optional)

Set SMTP credentials to enable alert emails and the **Email this** button.
Without email, alerts appear in the server log instead.

```bash
export SMTP_HOST=smtp.gmail.com
export SMTP_USERNAME=you@example.com
export SMTP_PASSWORD=your_app_password
export ALERT_TO=you@example.com
```

Or configure directly in the UI — settings are persisted.

### 3. Add alerts

Type keywords and pick a schedule. The agent searches your feeds and emails
you when it finds matches.

---

## Run

```bash
python main.py                    # default port 28793
python main.py --port 8080
python main.py --provider anthropic
```

---

## Persistence

All state is saved to `.store.json` next to `main.py`:

- Configured feed URLs
- Email settings
- Alert configurations (keywords, schedule, last run time)

Everything is restored on restart — no reconfiguration needed.

---

## Dependencies

```bash
pip install -r requirements.txt
```

No API keys required for RSS feeds — `feedparser` handles standard RSS/Atom.

---

## Environment variables

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | `rits` \| `anthropic` \| `openai` \| `watsonx` \| `litellm` \| `ollama` |
| `LLM_MODEL` | Model name override (optional) |
| `SMTP_HOST` | SMTP server (default: `smtp.gmail.com`) |
| `SMTP_USERNAME` | Sender email / SMTP login |
| `SMTP_PASSWORD` | SMTP password or app password |
| `ALERT_TO` | Recipient email for alerts |
