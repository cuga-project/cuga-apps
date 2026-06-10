"""
Meetup Finder — CUGA Demo App (Playwright / browser automation)
==============================================================

Give a location and your interests (tech/AI by default) — "AI meetups in San
Francisco this week", "LLM and data-eng events near Austin this weekend" — and
the agent returns a ranked board of upcoming events with date, venue, host,
and an RSVP link.

This is CUGA's *browser* capability, not just an API call. The big event
platforms (Meetup.com, Luma, Eventbrite) deprecated their public search APIs
but render rich, structured event pages — so the agent drives a real headless
Chromium via Playwright, opens each discovery page, and extracts events from
the page's embedded JSON-LD / Next.js data.

Pattern: Playwright is wrapped as inline @tool defs and the CugaAgent planner
orchestrates them (same approach as chief_of_staff's browser-runner) — no MCP
servers. CUGA policies (tool_guide + output_formatter) harden the result.

Run:
    cd apps/meetup_finder
    pip install -r requirements.txt        # plus: pip install cuga
    python -m playwright install chromium   # one-time: fetch the browser
    python main.py --port 28826

Then open: http://127.0.0.1:28826

Environment variables:
    LLM_PROVIDER          rits | anthropic | openai | watsonx | litellm | ollama
    LLM_MODEL             model name override
    AGENT_SETTING_CONFIG  path to CUGA settings TOML (defaulted in make_agent)
    MEETUP_HEADLESS       "0" to watch the browser (default headless)
"""
from __future__ import annotations

import argparse
import asyncio
import contextvars
import html as _html
import json
import logging
import os
import re
import sys
import urllib.parse
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ── Path bootstrap — must come before local imports ─────────────────────
_DIR       = Path(__file__).parent
_DEMOS_DIR = _DIR.parent
for _p in (str(_DIR), str(_DEMOS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Robustness: AGENT_SETTING_CONFIG may arrive as an in-IMAGE absolute path
# (e.g. /app/apps/settings.watsonx.toml from build/.env) while running from a
# local checkout where it doesn't exist. CUGA aborts on a missing config file,
# so remap a non-existent absolute config to a local file of the same name.
_asc = os.environ.get("AGENT_SETTING_CONFIG", "")
if os.path.isabs(_asc) and not os.path.isfile(_asc):
    for _cand in (_DIR / os.path.basename(_asc), _DEMOS_DIR / os.path.basename(_asc)):
        if _cand.is_file():
            os.environ["AGENT_SETTING_CONFIG"] = str(_cand)
            break

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from ui import _HTML


# ── Tech/AI default interests ────────────────────────────────────────────
_DEFAULT_INTERESTS = "artificial intelligence"
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/123.0 Safari/537.36")


# ── Per-thread session store ────────────────────────────────────────────
_sessions: dict[str, dict] = {}

# The thread_id of the in-flight /ask, so fetch_events can accumulate what it
# extracts into that session WITHOUT depending on the (weak) model to thread a
# thread_id through every tool call. A ContextVar is task-local, so concurrent
# /ask requests don't clobber each other (and child tasks inherit the value).
_active_thread: contextvars.ContextVar[str] = contextvars.ContextVar(
    "active_thread", default="")


def _get_session(thread_id: str) -> dict:
    if thread_id not in _sessions:
        _sessions[thread_id] = {
            "interests": "",
            "location":  "",
            "when":      "",
            "events":    [],   # ranked board the right panel renders
            "_fetched":  [],   # raw events fetch_events extracted (safety-net source)
        }
    return _sessions[thread_id]


def _event_is_past(start: str) -> bool:
    """True if an event's start date is clearly in the past. Lenient: if the
    date can't be parsed, keep the event (return False) rather than drop it."""
    s = (start or "").strip()
    if not s:
        return False
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
        if not m:
            return False
        dt = datetime(int(m[1]), int(m[2]), int(m[3]))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # Compare on date only, so an event earlier *today* still counts.
    return dt.date() < datetime.now(timezone.utc).date()


# Bare-metal hosts (no `playwright install --with-deps`, no root to dnf-install
# Chromium's system libs) can stage them in a local prefix and point the loader
# at it. Default matches the rootless RPM-extract recipe in the README; override
# with MEETUP_BROWSER_LIBS. No-op in the container (the image bakes the libs in)
# and on any host where the prefix doesn't exist.
def _ensure_local_browser_libs() -> None:
    prefix = os.getenv("MEETUP_BROWSER_LIBS") or os.path.expanduser(
        "~/.local/chromium-deps")
    dirs = [os.path.join(prefix, "usr", "lib64"), os.path.join(prefix, "usr", "lib")]
    dirs = [d for d in dirs if os.path.isdir(d)]
    if not dirs:
        return
    existing = os.environ.get("LD_LIBRARY_PATH", "")
    parts = [d for d in dirs if d not in existing.split(os.pathsep)]
    if parts:
        os.environ["LD_LIBRARY_PATH"] = os.pathsep.join(
            parts + ([existing] if existing else []))


# ── Playwright browser pool (lazy, single browser, serialized) ───────────
# Mirrors chief_of_staff/browser_runner/executor.py: start async_playwright
# once, launch one headless Chromium, and serve a fresh context per fetch
# under a lock. The browser is reused across requests for speed.
class _BrowserPool:
    def __init__(self) -> None:
        self._pw = None
        self._browser = None
        self._lock = asyncio.Lock()

    async def fetch(self, url: str, timeout_ms: int = 30_000) -> tuple[str, str]:
        """Navigate to url and return (html, page_title). Raises on failure."""
        from playwright.async_api import async_playwright
        headless = os.getenv("MEETUP_HEADLESS", "1") != "0"
        async with self._lock:
            # Gate on the browser, not the playwright handle: a launch that fails
            # after async_playwright().start() leaves _pw set but _browser None,
            # so gating on _pw would skip relaunch and every later call would die
            # with a misleading "'NoneType' has no attribute 'new_context'".
            if self._browser is None:
                _ensure_local_browser_libs()
                if self._pw is None:
                    self._pw = await async_playwright().start()
                # In a container (Docker/Code Engine) Chromium runs as root and
                # /dev/shm is tiny, so the sandbox + default shm break the
                # launch. Detect the container and pass the standard flags.
                in_container = bool(os.getenv("CUGA_IN_DOCKER") or os.getenv("CE_APP")
                                    or os.getenv("MEETUP_NO_SANDBOX"))
                launch_args = ["--no-sandbox", "--disable-dev-shm-usage"] if in_container else []
                try:
                    self._browser = await self._pw.chromium.launch(
                        headless=headless, args=launch_args)
                except Exception:
                    # Tear the handle down too so the next call retries cleanly
                    # and surfaces the real launch error, not a None deref.
                    await self.aclose()
                    self._pw = None
                    self._browser = None
                    raise
            ctx = await self._browser.new_context(
                user_agent=_UA, viewport={"width": 1280, "height": 2400})
            page = await ctx.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                # Give client-side rendering a moment to populate event cards.
                try:
                    await page.wait_for_load_state("networkidle", timeout=6_000)
                except Exception:  # noqa: BLE001
                    pass
                return await page.content(), await page.title()
            finally:
                await ctx.close()

    async def aclose(self) -> None:
        try:
            if self._browser:
                await self._browser.close()
            if self._pw:
                await self._pw.stop()
        except Exception:  # noqa: BLE001
            pass


_pool = _BrowserPool()


# ── Event extraction (embedded structured data) ──────────────────────────
def _clean(s, limit: int = 400) -> str:
    s = re.sub(r"<[^>]+>", " ", str(s or ""))
    s = _html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()[:limit]


def _g(obj: dict, *keys):
    for k in keys:
        if isinstance(obj, dict) and obj.get(k) not in (None, "", [], {}):
            return obj[k]
    return None


def _loc_str(loc) -> str:
    if isinstance(loc, str):
        return _clean(loc, 160)
    if isinstance(loc, list) and loc:
        return _loc_str(loc[0])
    if isinstance(loc, dict):
        name = loc.get("name") or ""
        addr = loc.get("address")
        if isinstance(addr, dict):
            parts = [addr.get("streetAddress"), addr.get("addressLocality"),
                     addr.get("addressRegion")]
            addr = ", ".join(p for p in parts if p)
        return _clean(" — ".join(p for p in [name, addr if isinstance(addr, str) else ""] if p), 160)
    return ""


def _norm_event(obj: dict, source: str) -> dict | None:
    title = _g(obj, "name", "title", "headline")
    start = _g(obj, "startDate", "start_at", "startTime", "start_time", "starts_at", "datetime")
    if not title or not start:
        return None
    url = _g(obj, "url", "full_url", "permalink", "event_url")
    organizer = _g(obj, "organizer", "host", "group")
    if isinstance(organizer, dict):
        organizer = organizer.get("name")
    elif isinstance(organizer, list) and organizer:
        organizer = organizer[0].get("name") if isinstance(organizer[0], dict) else str(organizer[0])
    attendees = _g(obj, "going_count", "guest_count", "maximumAttendeeCapacity", "remaining_spots")
    return {
        "title":     _clean(title, 200),
        "url":       url if isinstance(url, str) else "",
        "start":     _clean(start, 40),
        "venue":     _loc_str(_g(obj, "location", "venue", "geo_address_info")),
        "host":      _clean(organizer, 120) if organizer else "",
        "attendees": attendees if isinstance(attendees, (int, str)) else None,
        "description": _clean(_g(obj, "description", "summary") or "", 300),
        "source":    source,
    }


def _iter_jsonld(node):
    if isinstance(node, dict):
        if "@graph" in node:
            yield from _iter_jsonld(node["@graph"])
        if node.get("@type") == "ItemList" and "itemListElement" in node:
            for el in node["itemListElement"]:
                yield from _iter_jsonld(el.get("item", el) if isinstance(el, dict) else el)
        yield node
    elif isinstance(node, list):
        for el in node:
            yield from _iter_jsonld(el)


def _events_from_jsonld(html: str, source: str) -> list[dict]:
    out = []
    for m in re.finditer(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html, re.DOTALL | re.IGNORECASE):
        try:
            data = json.loads(m.group(1).strip())
        except Exception:  # noqa: BLE001
            continue
        for obj in _iter_jsonld(data):
            t = obj.get("@type") if isinstance(obj, dict) else None
            t = " ".join(t) if isinstance(t, list) else str(t or "")
            if "Event" in t:
                ev = _norm_event(obj, source)
                if ev:
                    out.append(ev)
    return out


def _events_from_nextdata(html: str, source: str) -> list[dict]:
    """Harvest event-shaped dicts from Next.js __NEXT_DATA__ / Apollo blobs
    (Luma, Meetup). Generic: a dict with a name/title AND a start-time field."""
    out = []
    for m in re.finditer(
            r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
            html, re.DOTALL | re.IGNORECASE):
        try:
            data = json.loads(m.group(1))
        except Exception:  # noqa: BLE001
            continue
        seen_ids = set()

        def walk(o):
            if isinstance(o, dict):
                keys = {k.lower() for k in o.keys()}
                has_name = bool(keys & {"name", "title"})
                has_start = bool(keys & {"start_at", "startdate", "start_time",
                                         "starts_at", "starttime", "datetime"})
                if has_name and has_start:
                    ev = _norm_event(o, source)
                    if ev:
                        key = (ev["title"], ev["start"])
                        if key not in seen_ids:
                            seen_ids.add(key)
                            out.append(ev)
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)

        walk(data)
    return out


def _board_from_fetched(raw: list[dict]) -> list[dict]:
    """Build a render-ready board from the events fetch_events extracted:
    normalise, drop past events, dedupe by title+date, cap. Used as the
    safety net when the model never calls save_events."""
    out, seen = [], set()
    for e in raw:
        ev = _coerce_board_event(e)
        if not ev or _event_is_past(ev["start"]):
            continue
        key = (ev["title"].lower(), ev["start"])
        if key in seen:
            continue
        seen.add(key)
        out.append(ev)
    return out[:30]


def _coerce_board_event(e: dict) -> dict | None:
    """Normalise one event the agent passes to save_events into the exact
    shape the right panel renders. The model often uses schema.org-ish keys
    (name/date/link/organizer) instead of our title/start/url/host — before
    this, those rendered as blank 'Event' cards and, once we started filtering
    empties, vanished entirely. A real entry needs at least a title/name."""
    if not isinstance(e, dict):
        return None

    def pick(*keys):
        for k in keys:
            v = e.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""

    title = pick("title", "name", "headline", "event", "event_name", "summary")
    if not title:
        return None
    att = e.get("attendees")
    if not isinstance(att, (int, str)) or att == "":
        att = pick("going", "going_count", "rsvps", "guest_count") or None
    return {
        "title":     title,
        "url":       pick("url", "link", "permalink", "event_url", "rsvp_url"),
        "start":     pick("start", "start_at", "startDate", "start_time",
                          "starts_at", "datetime", "date", "when"),
        "venue":     pick("venue", "location", "place", "address"),
        "city":      pick("city"),
        "host":      pick("host", "organizer", "organiser", "group"),
        "source":    pick("source"),
        "attendees": att,
        "why":       pick("why", "reason", "fit", "note"),
    }


def _extract_events(html: str, url: str) -> list[dict]:
    domain = urllib.parse.urlparse(url).netloc.lower().replace("www.", "")
    source = domain.split(".")[0] if domain else "web"
    events = _events_from_jsonld(html, source) + _events_from_nextdata(html, source)
    # Dedupe by (title, start); fix relative Luma URLs.
    seen, deduped = set(), []
    for ev in events:
        if ev["url"].startswith("/"):
            ev["url"] = f"https://{domain}{ev['url']}"
        key = (ev["title"].lower(), ev["start"][:10])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ev)
    return deduped


# ── Discovery URL builders (tech/AI focus) ───────────────────────────────
def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def _discovery_urls(interests: str, location: str) -> list[dict]:
    q = interests or _DEFAULT_INTERESTS
    qslug = _slug(q)
    city = _slug(location.split(",")[0]) if location else ""
    urls = [
        {"source": "meetup",
         "url": "https://www.meetup.com/find/?" + urllib.parse.urlencode(
             {"keywords": q, "source": "EVENTS", **({"location": location} if location else {})})},
        {"source": "luma",
         "url": f"https://lu.ma/{city}" if city else "https://lu.ma/discover"},
    ]
    eb_loc = _slug(location.replace(", ", "-")) if location else "online"
    urls.append({"source": "eventbrite",
                 "url": f"https://www.eventbrite.com/d/{eb_loc}/{qslug}/"})
    return urls


# ── Tools ────────────────────────────────────────────────────────────────
def _make_tools():
    from langchain_core.tools import tool

    @tool
    def set_search(thread_id: str, interests: str = "", location: str = "",
                   when: str = "") -> str:
        """Record what the user is looking for this session. Call whenever they
        mention interests, a location, or a timeframe.

        Args:
            thread_id: The current session/thread ID (always pass through).
            interests: Topics, e.g. "AI agents, LLMs", "data engineering",
                       "startups". Empty defaults to a broad AI/tech search.
            location:  City/area, e.g. "San Francisco", "Austin, TX". Empty
                       searches Luma's global discover feed.
            when:      Free-text timeframe, e.g. "this week", "this weekend",
                       "next month". Used to filter events at ranking time.
        """
        session = _get_session(thread_id)
        if interests.strip():
            session["interests"] = interests.strip()
        if location.strip():
            session["location"] = location.strip()
        if when.strip():
            session["when"] = when.strip()
        return json.dumps({"ok": True, "data": {
            "interests": session["interests"] or _DEFAULT_INTERESTS,
            "location":  session["location"] or "anywhere",
            "when":      session["when"] or "upcoming",
        }})

    @tool
    def build_event_urls(thread_id: str, interests: str = "",
                         location: str = "") -> str:
        """Build the discovery-page URLs to crawl across Meetup, Luma, and
        Eventbrite for the given interests + location. Call this before
        fetch_events. Returns a list of {source, url}.

        Args:
            thread_id: The current session/thread ID.
            interests: Topics; empty uses the session interests (or AI default).
            location:  City/area; empty uses the session location.
        """
        session = _get_session(thread_id)
        interests = interests.strip() or session["interests"]
        location = location.strip() or session["location"]
        urls = _discovery_urls(interests, location)
        return json.dumps({"ok": True, "data": {
            "interests": interests or _DEFAULT_INTERESTS,
            "location":  location or "anywhere",
            "urls":      urls,
        }})

    @tool
    async def fetch_events(url: str, limit: int = 15) -> str:
        """Open a discovery page in a real headless browser (Playwright) and
        extract upcoming events from its embedded structured data (JSON-LD /
        Next.js data). Use this on each URL from build_event_urls.

        Args:
            url:   A discovery-page URL (Meetup find, Luma city/discover,
                   Eventbrite /d/...).
            limit: Max events to return from this page (default 15).
        """
        url = (url or "").strip()
        if not url.startswith("http"):
            return json.dumps({"ok": False, "code": "bad_input",
                               "error": "url must be absolute http(s)"})
        try:
            html, title = await _pool.fetch(url)
        except Exception as exc:  # noqa: BLE001
            log.warning("fetch_events failed for %s: %s", url, exc)
            return json.dumps({"ok": False, "code": "browser_error",
                               "error": f"{type(exc).__name__}: {exc}"})
        events = _extract_events(html, url)[: max(1, min(int(limit or 15), 40))]
        log.info("fetch_events %s → %d events", url, len(events))
        # Safety net: stash what we actually extracted on the in-flight session.
        # If the model then forgets/comments-out save_events (the weak ones do),
        # /ask falls back to this so the panel still renders real events.
        tid = _active_thread.get()
        if tid and events:
            _get_session(tid)["_fetched"].extend(events)
        return json.dumps({"ok": True, "data": {
            "url": url, "page_title": _clean(title, 120),
            "count": len(events), "events": events,
            "note": "" if events else "no structured events found on this page "
                    "(site layout may have changed, or no matching events)",
        }})

    @tool
    def get_session_state(thread_id: str) -> str:
        """Read the session's interests, location, timeframe, and whether a
        board has been saved yet.

        Args:
            thread_id: The current session/thread ID.
        """
        session = _get_session(thread_id)
        return json.dumps({"ok": True, "data": {
            "interests":  session["interests"] or _DEFAULT_INTERESTS,
            "location":   session["location"] or "anywhere",
            "when":       session["when"] or "upcoming",
            "has_events": bool(session["events"]),
        }})

    @tool
    def save_events(thread_id: str, events_json: str) -> str:
        """Persist the ranked event board so the right-panel UI can render it.
        Call this at the END of every search.

        Args:
            thread_id:   The current session/thread ID.
            events_json: A JSON array. Each element should include:
                           title       (str)
                           url         (str)   RSVP / event link
                           start       (str)   ISO date/time as found
                           venue       (str)
                           city        (str, optional)
                           host        (str, optional)  group/organizer
                           source      (str)   meetup | luma | eventbrite
                           attendees   (int|str, optional)
                           why         (str)   one line: why you'd go / fit
        """
        session = _get_session(thread_id)
        try:
            events = json.loads(events_json)
            if not isinstance(events, list):
                return json.dumps({"ok": False, "code": "bad_input",
                                   "error": "events_json must be a JSON array"})
            # Normalise each entry into the panel's shape (handles alternate
            # key names) and drop anything without a title. This kills the
            # empty-card flood AND ensures real events still render even when
            # the model used name/date/link instead of title/start/url.
            clean = [n for n in (_coerce_board_event(e) for e in events) if n]
            clean = clean[:30]
            # Don't wipe a good board with an empty/garbage submission.
            if clean or not session.get("events"):
                session["events"] = clean
            log.info("[%s] saved %d events (%d submitted)",
                     thread_id[:8], len(clean), len(events))
            return json.dumps({"ok": True, "data": {"saved": len(clean)}})
        except json.JSONDecodeError as exc:
            return json.dumps({"ok": False, "code": "bad_input",
                               "error": f"invalid JSON: {exc}"})

    return [set_search, build_event_urls, fetch_events, get_session_state, save_events]


# ── System prompt ────────────────────────────────────────────────────────
_SYSTEM = """\
# Meetup Finder (browser-driven)

You find upcoming meetups and events — tech/AI by default — by driving a real
browser over Meetup, Luma, and Eventbrite (their public search APIs are gone,
so you read the rendered discovery pages).

## Sequence for every search

1. Call `set_search` with the user's interests, location, and timeframe.
2. Call `build_event_urls(thread_id=...)` to get the discovery URLs.
3. For each URL, call `fetch_events(url=...)`. It opens the page in a headless
   browser and extracts structured events. Some pages return nothing (layout
   drift or no matches) — that's fine, move on. Aim to fetch all of them.
4. Merge the events. Drop duplicates (same title + date across sources).
   Filter to the user's timeframe (`when`) using each event's `start`. Bias
   toward the user's interests; for the default search, favor AI / ML / data /
   dev / startup events.
5. Rank by relevance to the interests, then soonest date. For each event write
   a one-line `why` (why it fits). Keep `url`, `start`, `venue`, `host`,
   `source` from the extracted data.
6. Call `save_events(thread_id=..., events_json=...)`. This step is REQUIRED
   and is the PRIMARY output — the panel on the right is what the user reads.
   You MUST call it before you reply, even if you only have partial results.
7. Reply with a SHORT framing ONLY — 1–2 sentences pointing the user to the
   panel (note if a source returned nothing). Do NOT repeat the full ranked
   rundown in prose; the panel already shows every event with its date, venue,
   host, and RSVP link.

## Rules
- Never invent events, dates, venues, or RSVP links — only report what
  fetch_events returned. If everything came back empty, say so and suggest a
  broader location or different interests.
- Prefer events with a real date and link. Don't list past events.
- Keep the prose tight — the right panel shows the full board.

## Thread ID
You will receive the thread_id in every user message (format:
"[thread:<UUID>]"). Always extract it and pass it unchanged to every tool
call that requires thread_id.
"""


# ── CUGA policies ─────────────────────────────────────────────────────────
async def _attach_policies(agent) -> None:
    try:
        await agent.policies.add_tool_guide(
            name="event_extraction_guide",
            content=(
                "Only report events that fetch_events actually returned — never "
                "invent titles, dates, venues, or RSVP links. Try every URL from "
                "build_event_urls; an empty page is normal, just move on. Drop "
                "past events and duplicates that appear on more than one source."
            ),
            target_tools=["fetch_events", "build_event_urls"],
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("tool_guide skipped: %s", exc)
    try:
        await agent.policies.add_output_formatter(
            name="event_board_formatter",
            format_config=(
                "Before replying, ALWAYS call save_events with the ranked board "
                "(each event needs title, url, start, venue, source, and a one-"
                "line why). Then reply with a tight ranked list — event title as "
                "a markdown link, its date, and venue/host. Note any source that "
                "returned nothing."
            ),
            format_type="markdown",
            keywords=["meetup", "meetups", "events", "event", "happening", "near"],
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("output_formatter skipped: %s", exc)


# ── Agent factory ────────────────────────────────────────────────────────
def make_agent():
    from cuga.sdk import CugaAgent
    from _llm import create_llm

    _provider_toml = {
        "rits":      "settings.rits.toml",
        "watsonx":   "settings.watsonx.toml",
        "openai":    "settings.openai.toml",
        "anthropic": "settings.openai.toml",
        "litellm":   "settings.litellm.toml",
        "ollama":    "settings.openai.toml",
    }
    provider = (os.getenv("LLM_PROVIDER") or "").lower()
    os.environ.setdefault(
        "AGENT_SETTING_CONFIG",
        _provider_toml.get(provider, "settings.rits.toml"),
    )

    return CugaAgent(
        model=create_llm(
            provider=os.getenv("LLM_PROVIDER"),
            model=os.getenv("LLM_MODEL"),
        ),
        tools=_make_tools(),
        special_instructions=_SYSTEM,
        cuga_folder=str(_DIR / ".cuga"),
        # Each question is independent. Disable the persistent knowledge store
        # and on-disk policy auto-load so nothing learned/saved in one question
        # leaks into the next via the shared .cuga folder. The output formatter
        # we need is attached explicitly in _attach_policies().
        enable_knowledge=False,
        auto_load_policies=False,
    )


# ── Request models ──────────────────────────────────────────────────────
class AskReq(BaseModel):
    question: str
    thread_id: str = ""


# ── HTTP server ──────────────────────────────────────────────────────────
def _web(port: int) -> None:
    import uvicorn

    app = FastAPI(title="Meetup Finder", docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    _agent = None
    _policies_attached = False

    async def _get_agent():
        nonlocal _agent, _policies_attached
        if _agent is None:
            log.info("Initialising CugaAgent…")
            _agent = make_agent()
            log.info("CugaAgent ready.")
        if not _policies_attached:
            try:
                await _attach_policies(_agent)
                log.info("CUGA policies attached.")
            except Exception as exc:  # noqa: BLE001
                log.warning("policy attach failed (continuing without): %s", exc)
            _policies_attached = True
        return _agent

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(_HTML)

    @app.post("/ask")
    async def api_ask(req: AskReq):
        from _usage import track_utterance; track_utterance(req.question)
        # Stateless per question: reset the panel session and run on a fresh
        # memory thread. The singleton agent has its persistent knowledge store
        # and on-disk policy auto-load disabled (see make_agent), so nothing
        # carries over from the previous question.
        thread_id = req.thread_id or uuid.uuid4().hex
        _sessions.pop(thread_id, None)
        _active_thread.set(thread_id)
        augmented = f"[thread:{thread_id}] {req.question}"
        try:
            agent = await _get_agent()
            result = await agent.invoke(augmented, thread_id=uuid.uuid4().hex)
            # Use the agent's synthesised answer, NOT str(result): the result
            # object's repr dumps the CUGA plan + generated code into the chat.
            answer = result.answer if hasattr(result, "answer") else str(result)
            # Safety net: if the model fetched events but never (correctly) called
            # save_events, the panel would be empty. Populate it from what
            # fetch_events actually extracted so the user still sees real results.
            session = _sessions.get(thread_id)
            if session is not None and not session.get("events") and session.get("_fetched"):
                board = _board_from_fetched(session["_fetched"])
                if board:
                    session["events"] = board
                    log.info("[%s] safety-net populated %d events "
                             "(model skipped save_events)", thread_id[:8], len(board))
            return {"answer": answer, "thread_id": thread_id}
        except Exception as exc:
            log.exception("Agent invocation failed")
            return JSONResponse(
                status_code=500,
                content={"answer": f"Error: {exc}", "thread_id": thread_id},
            )

    @app.get("/session/{thread_id}")
    async def api_session(thread_id: str):
        return _get_session(thread_id)

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.on_event("shutdown")
    async def _shutdown():
        await _pool.aclose()

    print(f"\n  Meetup Finder  →  http://127.0.0.1:{port}\n")
    # Public deployment: layered, in-memory rate limiting on POST.
    from _ratelimit import install_rate_limit
    install_rate_limit(app)
    from _usage import install_usage
    install_usage(app)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ── CLI entry point ──────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Meetup Finder — CUGA demo app")
    parser.add_argument("--port", type=int, default=28826)
    parser.add_argument(
        "--provider", "-p", default=None,
        choices=["rits", "watsonx", "openai", "anthropic", "litellm", "ollama"],
    )
    parser.add_argument("--model", "-m", default=None)
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    _web(args.port)


if __name__ == "__main__":
    main()
