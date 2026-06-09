# Meetup Finder — CUGA Demo App (Playwright / browser automation)

Give a location and your interests (tech/AI by default) — *"AI meetups in San
Francisco this week"*, *"LLM and data-eng events near Austin this weekend"* —
and the agent returns a ranked board of upcoming events with date, venue,
host, and an RSVP link.

This is the app that exercises **CUGA's browser capability**, not just an API
call. Meetup, Luma, and Eventbrite all deprecated their public *search* APIs
but still render rich, structured event pages — so the agent drives a real
**headless Chromium via Playwright**, opens each discovery page, and extracts
events from the page's embedded **JSON-LD / Next.js data** (far more robust
than scraping CSS classes).

## How it works

Playwright is wrapped as **inline `@tool` defs** and the CugaAgent planner
orchestrates them — the same pattern as `chief_of_staff`'s browser-runner. No
MCP servers, no API keys.

| Tool | Role |
| ---- | ---- |
| `set_search` | record interests / location / timeframe |
| `build_event_urls` | construct Meetup + Luma + Eventbrite discovery URLs |
| `fetch_events` | **open each URL in headless Chromium**, extract events from JSON-LD / `__NEXT_DATA__` |
| `save_events` | persist the ranked board the right panel renders |

**CUGA policies** harden it: a `tool_guide` keeps the agent honest ("only
report events fetch_events returned; try every URL; drop past/duplicate
events") and an `output_formatter` locks the save-board + reply contract.

The agent: records the search → builds discovery URLs → browses each one →
merges/dedupes/filters by date → ranks by interest fit → saves the board →
replies with a short ranked rundown.

## Run

```bash
cd apps/meetup_finder
pip install -r requirements.txt        # plus: pip install cuga
python -m playwright install chromium  # one-time: fetch the browser binary
python main.py --port 28826
# watch the browser instead of headless:  MEETUP_HEADLESS=0 python main.py
```

Then open <http://127.0.0.1:28826> and try:

- `AI agent meetups in San Francisco this week`
- `LLM and data engineering events near New York`
- `Startup / founder events in London this month`
- `ML research talks in Boston this weekend`

## Endpoints

| Method | Path                   | Purpose                                            |
| ------ | ---------------------- | -------------------------------------------------- |
| GET    | `/`                    | Two-panel UI                                       |
| POST   | `/ask`                 | `{question, thread_id}` → `{answer, thread_id}`    |
| GET    | `/session/{thread_id}` | Session state (search context + ranked events)     |
| GET    | `/health`              | `{"ok": true}`                                     |

## Environment

| Var                    | Required | Notes                                       |
| ---------------------- | -------- | ------------------------------------------- |
| `LLM_PROVIDER`         | yes      | rits \| anthropic \| openai \| watsonx \| … |
| `LLM_MODEL`            | no       | model override                              |
| `AGENT_SETTING_CONFIG` | no       | defaulted in `make_agent`                   |
| `MEETUP_HEADLESS`      | no       | `0` to watch the browser (default headless) |

## Notes & caveats

- **Browser-dependent**: needs the `playwright` package **and** a Chromium
  binary (`python -m playwright install chromium`). It is therefore *not* on a
  standard browserless apps image or `start.sh` launcher — run it locally, or
  bake it into a Playwright-enabled image (see `chief_of_staff`'s Dockerfile for
  a working browser image).
- Extraction relies on each site's embedded JSON-LD / Next.js data. Those
  layouts drift; `fetch_events` returns an empty list (with a note) rather than
  failing when a page changes, and the agent reports which sources came back
  empty. If a source consistently returns nothing, update its URL builder in
  `_discovery_urls` or the harvest logic in `_extract_events`.
- Meetup/Eventbrite occasionally gate discovery behind bot checks; Luma is the
  most reliably extractable. Running non-headless (`MEETUP_HEADLESS=0`) helps
  when debugging.
- Be a courteous crawler — this opens a handful of pages per query, serialized.
