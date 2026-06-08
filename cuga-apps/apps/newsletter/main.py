"""
Newsletter Intelligence — web UI powered by cuga++
===================================================

Starts a browser UI with two panels:

  Feed Query        — ask questions over your configured RSS feeds
  Scheduled Alerts  — keyword monitors that run on a schedule and email on hits

Run:
    python main.py
    python main.py --port 8080
    python main.py --provider anthropic

Then open: http://127.0.0.1:18793

Prerequisites:
    pip install -r requirements.txt

    Email alerts (optional — falls back to server log if not set):
        export SMTP_HOST=smtp.gmail.com
        export SMTP_USERNAME=you@example.com
        export SMTP_PASSWORD=your_app_password
        export ALERT_TO=you@example.com

Environment variables:
    LLM_PROVIDER    rits | anthropic | openai | ollama | watsonx | litellm
    LLM_MODEL       model override
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

_DIR       = Path(__file__).parent
_DEMOS_DIR = _DIR.parent

for _p in [str(_DIR), str(_DEMOS_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Persistent store — .store.json next to main.py
# ---------------------------------------------------------------------------

_STORE_PATH = _DIR / ".store.json"


def _load_store() -> dict:
    try:
        return json.loads(_STORE_PATH.read_text()) if _STORE_PATH.exists() else {}
    except Exception as exc:
        log.warning("Could not read store: %s", exc)
        return {}


def _save_store(data: dict) -> None:
    try:
        _STORE_PATH.write_text(json.dumps(data, indent=2))
    except Exception as exc:
        log.warning("Could not write store: %s", exc)


def _update_store(**fields) -> None:
    data = _load_store()
    data.update(fields)
    _save_store(data)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

_SYSTEM = """\
# Newsletter Intelligence

Applies when processing RSS feeds for summaries, keyword alerts, or free-form questions.

## Tools

You have two tools:

| Tool | When to use |
|---|---|
| `fetch_feed(url)` | Summarising one specific feed, or when given a single URL |
| `search_feeds(feed_urls, keywords)` | Finding articles matching a topic across multiple feeds |

Always call a tool to get live data. Never invent article titles, summaries, or URLs.

---

## Summarise mode

When asked to summarise feeds:
1. Call `fetch_feed(url)` for each relevant feed URL.
2. Deduplicate items with very similar titles.
3. Group by theme: **Research**, **Products & Launches**, **Tools & Open Source**, **Community**.
4. For each item include: title (linked if URL available), 1–2 sentence summary, source name, date.
5. Lead with the most significant item in each section.
6. Omit empty sections.

Format rules:
- Scannable — use section headers and brief bullets.
- Include relative date where possible ("today", "yesterday", "3 days ago").
- No disclaimers. No filler.

---

## Alert mode

When checking feeds for a keyword to decide if an alert is warranted:
1. Call `search_feeds(feed_urls, keywords)` with the provided feeds and keywords.
2. **If matches found:**
   - Begin your response with exactly `ALERT:` on the first line.
   - List each matching item: title, 1–2 sentence summary, source, URL.
   - Keep it short — this is a notification, not a newsletter.
3. **If no matches:**
   - Respond with exactly: `No matches for: <keywords>` — nothing more.

---

## Query mode

When asked a free-form question about feeds:
- Use `search_feeds` or `fetch_feed` as appropriate.
- Answer concisely and directly.
- Always include article titles and URLs when citing sources.
- If no feeds are configured, answer from your own knowledge and note that no feeds were provided.

---

## Format rules (all modes)

- Use **bold** for article titles and key terms.
- No bullet walls — prefer short paragraphs for summaries.
- Never add unsolicited advice, disclaimers, or "as an AI" hedges.
- Always include 24h publication context when available.
"""


def make_agent():
    from cuga import CugaAgent
    from feeds import make_feed_tools
    from _llm import create_llm

    return CugaAgent(
        model=create_llm(
            provider=os.getenv("LLM_PROVIDER"),
            model=os.getenv("LLM_MODEL"),
        ),
        tools=make_feed_tools(),
        special_instructions=_SYSTEM,
        cuga_folder=str(_DIR / ".cuga"),
    )


# ---------------------------------------------------------------------------
# Alert runner + background scheduler
# ---------------------------------------------------------------------------

_alert_log: list[dict] = []   # in-memory recent results, capped at 20


async def _run_alert_now(agent, alert: dict, feeds: list[str]) -> dict:
    """Run one alert immediately. Returns a log entry dict."""
    if not feeds:
        entry = {
            "alert_id":  alert["id"],
            "keywords":  alert["keywords"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "result":    "No feeds configured — add feed URLs in the left panel.",
        }
        _alert_log.insert(0, entry)
        if len(_alert_log) > 20:
            _alert_log.pop()
        return entry

    feed_urls_csv = ", ".join(feeds)
    prompt = (
        f"Check these feeds for articles matching: {alert['keywords']}\n"
        f"Feeds: {feed_urls_csv}\n\n"
        f"If you find relevant matches, start your response with 'ALERT:' and list them.\n"
        f"If no matches, respond with 'No matches for: {alert['keywords']}'"
    )
    try:
        result = await agent.invoke(prompt, thread_id=f"alert-{alert['id']}")
        answer = result.answer
    except Exception as exc:
        answer = f"Error running alert: {exc}"

    entry = {
        "alert_id":  alert["id"],
        "keywords":  alert["keywords"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "result":    answer,
        "matched":   answer.startswith("ALERT"),
    }
    _alert_log.insert(0, entry)
    if len(_alert_log) > 20:
        _alert_log.pop()

    log.info("[ALERT] %s → %s", alert["keywords"], answer[:80])
    return entry


async def _alert_scheduler(agent) -> None:
    """Background task: checks and runs scheduled alerts every 60 seconds."""
    while True:
        await asyncio.sleep(60)
        data   = _load_store()
        alerts = data.get("alerts", [])
        feeds  = data.get("feeds", [])
        now    = datetime.now(timezone.utc)
        changed = False

        for alert in alerts:
            if not alert.get("enabled", True):
                continue
            schedule = alert.get("schedule", "daily")
            if schedule == "on_demand":
                continue

            last_run = alert.get("last_run")
            due = False
            if last_run is not None:
                try:
                    last_dt = datetime.fromisoformat(last_run)
                    elapsed = (now - last_dt).total_seconds()
                    if schedule == "hourly" and elapsed >= 3600:
                        due = True
                    elif schedule == "daily" and elapsed >= 86400:
                        due = True
                except Exception:
                    pass

            if not due:
                continue

            await _run_alert_now(agent, alert, feeds)
            alert["last_run"] = now.isoformat()
            changed = True

        if changed:
            _save_store(data)


# ---------------------------------------------------------------------------
# Request models  (must be at module level for FastAPI body parsing)
# ---------------------------------------------------------------------------

from pydantic import BaseModel  # noqa: E402


class AskReq(BaseModel):
    question: str


class FeedAddReq(BaseModel):
    url: str


class FeedRemoveReq(BaseModel):
    url: str


class AlertAddReq(BaseModel):
    keywords: str
    schedule: str = "daily"   # "hourly" | "daily" | "on_demand"


class AlertDeleteReq(BaseModel):
    id: str


class AlertToggleReq(BaseModel):
    id: str
    enabled: bool


class AlertRunReq(BaseModel):
    id: str


# ---------------------------------------------------------------------------
# Web UI
# ---------------------------------------------------------------------------

def _web(port: int) -> None:
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse

    app = FastAPI(title="Newsletter Intelligence · CugaAgent", docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    _agent = make_agent()

    _stored = _load_store()

    if _stored.get("alerts"):
        log.info("Restored %d alert(s)", len(_stored["alerts"]))

    if _stored.get("feeds"):
        log.info("Restored %d feed(s)", len(_stored["feeds"]))
    else:
        _update_store(feeds=["https://rss.arxiv.org/rss/cs"])
        log.info("Initialized default feed: rss.arxiv.org/rss/cs")

    # start background scheduler — must run after uvicorn starts the loop;
    # asyncio.get_event_loop() raises in Python 3.13 if no loop is current.
    @app.on_event("startup")
    async def _start_scheduler():
        asyncio.create_task(_alert_scheduler(_agent))

    # ── Feed endpoints ─────────────────────────────────────────────────────

    @app.post("/feeds/add")
    def feeds_add(req: FeedAddReq):
        data  = _load_store()
        feeds = data.get("feeds", [])
        url   = req.url.strip()
        if url and url not in feeds:
            feeds.append(url)
            data["feeds"] = feeds
            _save_store(data)
        return {"feeds": _load_store().get("feeds", [])}

    @app.post("/feeds/remove")
    def feeds_remove(req: FeedRemoveReq):
        data  = _load_store()
        feeds = [f for f in data.get("feeds", []) if f != req.url]
        data["feeds"] = feeds
        _save_store(data)
        return {"feeds": feeds}

    @app.get("/feeds/list")
    def feeds_list():
        return {"feeds": _load_store().get("feeds", [])}

    # ── Query endpoint ─────────────────────────────────────────────────────

    @app.post("/ask")
    async def ask(req: AskReq):
        from _usage import track_utterance; track_utterance(req.question)
        feeds = _load_store().get("feeds", [])
        if feeds:
            feed_list = "\n".join(f"- {url}" for url in feeds)
            prompt = f"Configured feeds:\n{feed_list}\n\nQuestion: {req.question}"
        else:
            prompt = req.question
        try:
            result = await _agent.invoke(prompt, thread_id=uuid.uuid4().hex)
            return {"answer": result.answer}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    # ── Alert endpoints ────────────────────────────────────────────────────

    @app.post("/alerts/add")
    def alerts_add(req: AlertAddReq):
        data   = _load_store()
        alerts = data.get("alerts", [])
        alerts.append({
            "id":       str(uuid.uuid4())[:8],
            "keywords": req.keywords.strip(),
            "schedule": req.schedule,
            "enabled":  True,
            "last_run": None,
        })
        data["alerts"] = alerts
        _save_store(data)
        return {"alerts": alerts}

    @app.post("/alerts/delete")
    def alerts_delete(req: AlertDeleteReq):
        data   = _load_store()
        alerts = [a for a in data.get("alerts", []) if a["id"] != req.id]
        data["alerts"] = alerts
        _save_store(data)
        return {"alerts": alerts}

    @app.post("/alerts/toggle")
    def alerts_toggle(req: AlertToggleReq):
        data = _load_store()
        for a in data.get("alerts", []):
            if a["id"] == req.id:
                a["enabled"] = req.enabled
        _save_store(data)
        return {"alerts": data.get("alerts", [])}

    @app.get("/alerts/list")
    def alerts_list():
        return {"alerts": _load_store().get("alerts", [])}

    @app.post("/alerts/run")
    async def alerts_run(req: AlertRunReq):
        data   = _load_store()
        feeds  = data.get("feeds", [])
        alerts = data.get("alerts", [])
        alert  = next((a for a in alerts if a["id"] == req.id), None)
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")

        entry = await _run_alert_now(_agent, alert, feeds)

        # update last_run
        for a in alerts:
            if a["id"] == req.id:
                a["last_run"] = entry["timestamp"]
        data["alerts"] = alerts
        _save_store(data)
        return entry

    @app.get("/alerts/recent")
    def alerts_recent():
        return {"log": _alert_log}

    # ── HTML ───────────────────────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    def ui():
        return _WEB_HTML

    print(f"\n  Newsletter Intelligence · CugaAgent  →  http://127.0.0.1:{port}\n")
    # Public deployment: layered, in-memory rate limiting on POST.
    from _ratelimit import install_rate_limit
    install_rate_limit(app)
    from _usage import install_usage
    install_usage(app)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

_WEB_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Newsletter Intelligence · CugaAgent</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  /* Carbon White (g10) */
  --cds-background:#ffffff;
  --cds-layer-01:#f4f4f4;
  --cds-layer-02:#ffffff;
  --cds-layer-hover:#e8e8e8;
  --cds-layer-accent:#e0e0e0;
  --cds-field-01:#f4f4f4;
  --cds-border-subtle:#e0e0e0;
  --cds-border-strong:#8d8d8d;
  --cds-text-primary:#161616;
  --cds-text-secondary:#525252;
  --cds-text-helper:#6f6f6f;
  --cds-text-placeholder:#a8a8a8;
  --cds-link-primary:#0f62fe;
  --cds-link-hover:#0043ce;
  /* IBM Blue interaction ramp */
  --cds-interactive:#0f62fe;
  --cds-button-primary:#0f62fe;
  --cds-button-primary-hover:#0353e9;
  --cds-button-primary-active:#002d9c;
  --cds-focus:#0f62fe;
  --cds-support-error:#da1e28;
  --cds-support-success:#24a148;
  --cds-support-warning:#f1c21b;
  --cds-support-info:#0043ce;
  --cds-font-sans:'IBM Plex Sans',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
  --cds-font-mono:'IBM Plex Mono',ui-monospace,'SFMono-Regular',Menlo,monospace;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--cds-font-sans);background:var(--cds-background);color:var(--cds-text-primary);min-height:100vh;padding:40px 24px 80px;-webkit-font-smoothing:antialiased;letter-spacing:.16px}
::selection{background:var(--cds-interactive);color:#fff}
header{text-align:center;margin-bottom:32px}
/* App intro band: one-line blurb + the tools this app uses */
.app-intro{display:flex;align-items:center;gap:16px;flex-wrap:wrap;padding:10px 24px;background:var(--cds-layer-01);border-bottom:1px solid var(--cds-border-subtle);max-width:1060px;margin:0 auto 24px}
.app-intro__blurb{font-size:13px;color:var(--cds-text-secondary);line-height:1.5;max-width:48rem}
.app-intro__blurb strong{color:var(--cds-text-primary);font-weight:600}
.app-intro__tools{margin-left:auto;display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.app-intro__tools .tools-label{font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:var(--cds-text-helper);margin-right:4px}
.tool-pill{font-size:11px;color:var(--cds-text-secondary);background:var(--cds-layer-02);border:1px solid var(--cds-border-subtle);border-radius:999px;padding:3px 10px;white-space:nowrap}
h1{font-size:22px;font-weight:600;color:var(--cds-text-primary);margin-bottom:4px;letter-spacing:0}
.sub{font-size:13px;color:var(--cds-text-secondary)}.sub span{color:var(--cds-link-primary);font-weight:500}
.layout{display:grid;grid-template-columns:290px 1fr;gap:20px;max-width:1060px;margin:0 auto;align-items:start}
@media(max-width:720px){.layout{grid-template-columns:1fr}}
.card{background:var(--cds-layer-01);border:1px solid var(--cds-border-subtle);border-radius:0;padding:18px;margin-bottom:16px}
.card:last-child{margin-bottom:0}
.card-title{font-size:11px;font-weight:600;color:var(--cds-text-secondary);letter-spacing:.08em;text-transform:uppercase;margin-bottom:14px}
.section-label{font-size:11px;font-weight:600;color:var(--cds-text-helper);letter-spacing:.06em;text-transform:uppercase;margin:16px 0 10px;padding-top:16px;border-top:1px solid var(--cds-border-subtle)}
.section-label:first-child{margin-top:0;padding-top:0;border-top:none}
label{display:block;font-size:11px;color:var(--cds-text-secondary);margin-bottom:4px;font-weight:400;text-transform:uppercase;letter-spacing:.05em}
input[type=text],input[type=password],select{width:100%;background:var(--cds-field-01);border:none;border-bottom:1px solid var(--cds-border-strong);border-radius:0;padding:8px 12px;font-size:13px;color:var(--cds-text-primary);font-family:var(--cds-font-sans);outline:none;transition:outline .11s,background .11s}
input:focus,select:focus{outline:2px solid var(--cds-focus);outline-offset:-2px}
input::placeholder{color:var(--cds-text-placeholder)}
.field{margin-bottom:10px}
.row{display:flex;gap:8px;margin-top:10px}.row>*{flex:1}
button{background:var(--cds-button-primary);color:#fff;border:1px solid transparent;border-radius:0;padding:8px 16px;font-size:13px;font-weight:400;cursor:pointer;transition:background .15s,opacity .15s;white-space:nowrap;width:100%;margin-top:10px;font-family:var(--cds-font-sans)}
button:hover{background:var(--cds-button-primary-hover)}
button:active{background:var(--cds-button-primary-active)}
button:focus-visible,button:focus{outline:2px solid var(--cds-focus);outline-offset:-2px;box-shadow:inset 0 0 0 1px #fff}
button:disabled{opacity:.45;cursor:default}
button.secondary{background:var(--cds-layer-accent);border:1px solid var(--cds-border-subtle);color:var(--cds-text-primary)}
button.secondary:hover{background:var(--cds-layer-hover)}
button.danger-sm{background:transparent;border:1px solid var(--cds-support-error);color:var(--cds-support-error);width:auto;margin:0;padding:3px 8px;font-size:12px;border-radius:0}
button.danger-sm:hover{background:var(--cds-support-error);color:#fff}
button.btn-sm{background:var(--cds-layer-accent);border:1px solid var(--cds-border-subtle);color:var(--cds-text-primary);width:auto;margin:0;padding:3px 8px;font-size:12px;border-radius:0}
button.btn-sm:hover{background:var(--cds-layer-hover)}
.status-row{display:flex;align-items:center;gap:7px;margin-top:10px;padding:8px 12px;background:var(--cds-layer-02);border:1px solid var(--cds-border-subtle);border-radius:0;font-size:12px}
.dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.dot.on{background:var(--cds-support-success);box-shadow:0 0 5px var(--cds-support-success)}.dot.off{background:var(--cds-border-strong)}
.status-text{color:var(--cds-text-secondary);flex:1}.status-text strong{color:var(--cds-text-primary)}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.chip{background:var(--cds-layer-02);border:1px solid var(--cds-border-subtle);border-radius:.9375rem;padding:5px 10px;font-size:12px;color:var(--cds-text-secondary);cursor:pointer;transition:all .15s}
.chip:hover{background:var(--cds-interactive);border-color:var(--cds-interactive);color:#fff}
.result{margin-top:14px;padding:14px;background:var(--cds-layer-02);border:1px solid var(--cds-border-subtle);border-radius:0;font-size:14px;line-height:1.7;color:var(--cds-text-primary);display:none}
.result.visible{display:block}
.result strong{color:var(--cds-text-primary);font-weight:600}
.thinking{color:var(--cds-text-secondary);font-style:italic;font-size:13px}
.spinner{display:inline-block;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes fadein{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
.fadein{animation:fadein .2s ease}
.feed-item{display:flex;align-items:center;justify-content:space-between;padding:5px 0;border-bottom:1px solid var(--cds-border-subtle);gap:8px}
.feed-item:last-child{border-bottom:none}
.feed-url{font-size:12px;color:var(--cds-text-secondary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}
.alert-row{padding:8px 10px;background:var(--cds-layer-02);border:1px solid var(--cds-border-subtle);border-radius:0;margin-bottom:6px}
.alert-meta{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.alert-btns{display:flex;gap:4px;margin-top:6px}
.badge{font-size:10px;padding:2px 7px;border-radius:.9375rem;font-weight:600;letter-spacing:.04em;text-transform:uppercase}
.badge-daily{background:rgba(0,67,206,0.12);color:var(--cds-link-primary)}
.badge-hourly{background:rgba(36,161,72,0.12);color:var(--cds-support-success)}
.badge-on_demand{background:var(--cds-layer-accent);color:var(--cds-text-secondary)}
.log-entry{padding:8px 10px;background:var(--cds-layer-02);border:1px solid var(--cds-border-subtle);border-radius:0;margin-bottom:6px;font-size:12px}
.log-meta{color:var(--cds-text-secondary);margin-bottom:4px}
.log-body{color:var(--cds-text-secondary);line-height:1.5;white-space:pre-wrap;word-break:break-word;font-family:var(--cds-font-mono)}
.log-body.alert-hit{color:var(--cds-support-warning);color:#8a6d00}
*::-webkit-scrollbar{width:8px;height:8px}
*::-webkit-scrollbar-thumb{background:var(--cds-border-strong)}
*::-webkit-scrollbar-track{background:transparent}
</style>
</head>
<body>
<header>
  <h1>Newsletter Intelligence</h1>
  <p class="sub">Powered by <span>CugaAgent</span> · live RSS feeds</p>
</header>

<div class="app-intro">
  <div class="app-intro__blurb">
    <strong>Newsletter Intelligence.</strong> Pulls live articles from your RSS feeds to summarize the latest news, answer free-form questions, and run scheduled keyword alerts that email you on a match.
  </div>
  <div class="app-intro__tools">
    <span class="tools-label">Tools</span>
    <span class="tool-pill">📰 RSS feeds</span>
    <span class="tool-pill">🔎 Feed search</span>
    <span class="tool-pill">📄 Page fetch</span>
    <span class="tool-pill">🔔 Scheduled alerts</span>
    <span class="tool-pill">📧 Email · SMTP</span>
  </div>
</div>

<div class="layout">

  <!-- ══ Left panel ══ -->
  <div>
    <div class="card">

      <div class="section-label">RSS Feeds</div>
      <div class="row" style="margin-top:0">
        <input id="feedUrl" type="text" placeholder="https://arxiv.org/rss/cs.AI" onkeydown="if(event.key==='Enter')addFeed()" />
        <button onclick="addFeed()" style="width:auto;margin-top:0;padding:8px 14px">+ Add</button>
      </div>
      <div id="feedList" style="margin-top:10px;min-height:20px"></div>

    </div>
  </div>

  <!-- ══ Right panel ══ -->
  <div>

    <!-- Feed Query -->
    <div class="card">
      <div class="card-title">Feed Query</div>
      <div class="row" style="margin-top:0">
        <input id="qQuestion" type="text" placeholder="Ask anything about your feeds…" onkeydown="if(event.key==='Enter')ask()" />
        <button id="askBtn" onclick="ask()" style="width:auto;margin-top:0">Ask</button>
      </div>
      <div class="chips">
        <span class="chip" onclick="quickAsk('Summarize the latest AI research papers from my feeds')">Latest research</span>
        <span class="chip" onclick="quickAsk('What are the top stories across my feeds today?')">Top stories today</span>
        <span class="chip" onclick="quickAsk('Find anything about agentic AI or multi-agent systems')">Agentic AI</span>
        <span class="chip" onclick="quickAsk('Any new LLM releases or model announcements?')">New LLM releases</span>
        <span class="chip" onclick="quickAsk('What is new in open source AI tools or frameworks?')">Open source AI</span>
        <span class="chip" onclick="quickAsk('Find papers about RAG or retrieval-augmented generation')">RAG papers</span>
        <span class="chip" onclick="quickAsk('Any AI safety or alignment research recently?')">Safety & alignment</span>
        <span class="chip" onclick="quickAsk('What new AI products or startups were announced?')">New products</span>
        <span class="chip" onclick="quickAsk('Summarize everything from the last 24 hours across my feeds')">Last 24 hours</span>
        <span class="chip" onclick="quickAsk('Find anything mentioning Claude, GPT-4, or Gemini')">Model mentions</span>
        <span class="chip" onclick="quickAsk('What are the trending topics across my feeds?')">Trending topics</span>
        <span class="chip" onclick="quickAsk('Find recent tutorials or how-to guides on AI')">Tutorials</span>
        <span class="chip" onclick="quickAsk('Any discussions about AI regulation or policy?')">AI policy</span>
        <span class="chip" onclick="quickAsk('What benchmarks or evaluations were published recently?')">Benchmarks</span>
        <span class="chip" onclick="quickAsk('Find anything about AI applications in science or healthcare')">AI in science</span>
      </div>
      <div class="result" id="askResult"></div>
    </div>

    <!-- Scheduled Alerts -->
    <div class="card">
      <div class="card-title">Scheduled Alerts</div>

      <div style="display:grid;grid-template-columns:1fr auto auto;gap:8px;align-items:end">
        <div>
          <label>Keywords</label>
          <input id="aKeywords" type="text" placeholder="agentic AI, LLM release, RAG…" onkeydown="if(event.key==='Enter')addAlert()" />
        </div>
        <div>
          <label>Schedule</label>
          <select id="aSchedule" style="width:auto">
            <option value="daily">Daily</option>
            <option value="hourly">Hourly</option>
            <option value="on_demand">On Demand</option>
          </select>
        </div>
        <div style="padding-bottom:0">
          <button onclick="addAlert()" style="width:auto;margin-top:0;padding:8px 14px">+ Add</button>
        </div>
      </div>

      <div id="alertList" style="margin-top:12px"></div>

      <div class="section-label" style="margin-top:18px">Recent Alerts</div>
      <div id="recentLog"></div>
    </div>

  </div>
</div>

<script>
// ── Feeds ──────────────────────────────────────────────────────────────────

async function loadFeeds() {
  const res  = await fetch('/feeds/list')
  const data = await res.json()
  renderFeedList(data.feeds)
}

function renderFeedList(feeds) {
  const el = document.getElementById('feedList')
  if (!feeds.length) {
    el.innerHTML = '<div style="font-size:12px;color:var(--cds-text-placeholder);padding:4px 0">No feeds configured yet</div>'
    return
  }
  el.innerHTML = feeds.map(url => {
    const short = url.replace(/^https?:\\/\\//, '').replace(/\\/$/, '')
    const display = short.length > 42 ? short.slice(0, 42) + '…' : short
    const escaped = url.replace(/'/g, "\\'")
    return `<div class="feed-item">
      <span class="feed-url" title="${url}">${display}</span>
      <button class="danger-sm" onclick="removeFeed('${escaped}')">×</button>
    </div>`
  }).join('')
}

async function addFeed() {
  const url = document.getElementById('feedUrl').value.trim()
  if (!url) return
  const res = await fetch('/feeds/add', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({url})
  })
  const data = await res.json()
  document.getElementById('feedUrl').value = ''
  renderFeedList(data.feeds)
}

async function removeFeed(url) {
  const res  = await fetch('/feeds/remove', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({url})
  })
  const data = await res.json()
  renderFeedList(data.feeds)
}

// ── Query ──────────────────────────────────────────────────────────────────

function quickAsk(q) {
  document.getElementById('qQuestion').value = q
  ask()
}

async function ask() {
  const q = document.getElementById('qQuestion').value.trim()
  if (!q) return

  const btn    = document.getElementById('askBtn')
  const result = document.getElementById('askResult')
  btn.disabled = true
  result.className = 'result visible fadein'
  result.innerHTML = '<span class="thinking"><span class="spinner">⟳</span> Thinking…</span>'

  try {
    const res = await fetch('/ask', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({question: q})
    })
    if (!res.ok) throw new Error(await res.text())
    const data = await res.json()
    result.innerHTML = renderAnswer(data.answer)
  } catch (err) {
    result.style.color = '#f87171'
    result.textContent = 'Error: ' + err.message
  } finally {
    btn.disabled = false
  }
}

function renderAnswer(text) {
  return text
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/\\*\\*(.*?)\\*\\*/g,'<strong>$1</strong>')
    .replace(/\\n/g,'<br>')
}

// ── Alerts ─────────────────────────────────────────────────────────────────

async function loadAlerts() {
  const [listRes, logRes] = await Promise.all([
    fetch('/alerts/list'),
    fetch('/alerts/recent')
  ])
  const {alerts} = await listRes.json()
  const {log}    = await logRes.json()
  renderAlertList(alerts)
  renderAlertLog(log)
}

function renderAlertList(alerts) {
  const el = document.getElementById('alertList')
  if (!alerts.length) {
    el.innerHTML = '<div class="status-row"><span class="dot off"></span><span class="status-text">No alerts configured</span></div>'
    return
  }
  const schedLabel = {daily: 'daily', hourly: 'hourly', on_demand: 'on demand'}
  el.innerHTML = alerts.map(a => {
    const dotClass = a.enabled ? 'on' : 'off'
    const badge    = `<span class="badge badge-${a.schedule}">${schedLabel[a.schedule] || a.schedule}</span>`
    const lastRun  = a.last_run
      ? new Date(a.last_run).toLocaleString([], {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'})
      : 'never run'
    return `<div class="alert-row">
      <div class="alert-meta">
        <span class="dot ${dotClass}"></span>
        <strong style="font-size:13px;color:var(--cds-text-primary)">${a.keywords}</strong>
        ${badge}
        <span style="font-size:11px;color:var(--cds-text-placeholder)">· ${lastRun}</span>
      </div>
      <div class="alert-btns">
        <button class="btn-sm" data-run-id="${a.id}" onclick="runAlert('${a.id}')">Run Now</button>
        <button class="btn-sm" onclick="toggleAlert('${a.id}', ${!a.enabled})">${a.enabled ? 'Disable' : 'Enable'}</button>
        <button class="danger-sm" onclick="deleteAlert('${a.id}')">×</button>
      </div>
    </div>`
  }).join('')
}

function renderAlertLog(entries) {
  const el = document.getElementById('recentLog')
  if (!entries.length) {
    el.innerHTML = '<div style="font-size:12px;color:var(--cds-text-placeholder);padding:4px 0">No recent outputs</div>'
    return
  }
  el.innerHTML = entries.slice(0, 20).map(e => {
    const ts      = new Date(e.timestamp).toLocaleString([], {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'})
    const isAlert = e.result.startsWith('ALERT')
    const preview = e.result.slice(0, 240)
    const matchTag = isAlert ? ' · <span style="color:#8a6d00">match</span>' : ''
    return `<div class="log-entry">
      <div class="log-meta">${ts} · <strong>${e.keywords}</strong>${matchTag}</div>
      <div class="log-body${isAlert ? ' alert-hit' : ''}">${preview}${e.result.length > 240 ? '…' : ''}</div>
    </div>`
  }).join('')
}

async function addAlert() {
  const keywords = document.getElementById('aKeywords').value.trim()
  const schedule = document.getElementById('aSchedule').value
  if (!keywords) return
  const res  = await fetch('/alerts/add', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({keywords, schedule})
  })
  const data = await res.json()
  document.getElementById('aKeywords').value = ''
  renderAlertList(data.alerts)
}

async function deleteAlert(id) {
  const res  = await fetch('/alerts/delete', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({id})
  })
  const data = await res.json()
  renderAlertList(data.alerts)
}

async function toggleAlert(id, enabled) {
  const res  = await fetch('/alerts/toggle', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({id, enabled})
  })
  const data = await res.json()
  renderAlertList(data.alerts)
}

async function runAlert(id) {
  const btn = document.querySelector(`[data-run-id="${id}"]`)
  if (btn) { btn.disabled = true; btn.textContent = 'Running…' }
  try {
    const res = await fetch('/alerts/run', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id})
    })
    if (!res.ok) throw new Error(await res.text())
  } catch (err) {
    alert('Run failed: ' + err.message)
  }
  await loadAlerts()
}

// ── Init ───────────────────────────────────────────────────────────────────

loadFeeds()
loadAlerts()
// Refresh the alerts log every 30s so server-side scheduled runs surface in
// the bottom panel without a manual reload.
setInterval(loadAlerts, 30000)
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Newsletter Intelligence — web UI")
    parser.add_argument("--port",     type=int, default=18793)
    parser.add_argument("--provider", "-p", default=None,
                        choices=["rits", "watsonx", "openai", "anthropic", "litellm", "ollama"])
    parser.add_argument("--model",    "-m", default=None)
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    _web(args.port)


if __name__ == "__main__":
    main()
