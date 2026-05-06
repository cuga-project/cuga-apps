"""
Ouroboros — CUGA looks for its next client
==========================================

Lead generation for CUGA itself. The agent scouts a location for local
businesses that would benefit from an enterprise-grade conversational AI
agent (chat-bot order taker for restaurants, appointment booker for
salons, FAQ + lead-capture for clinics, etc.) and assembles a ranked
shortlist with a tailored CUGA pitch for each.

Tool surface:
  - mcp-geo.geocode                   place → lat/lon
  - mcp-web.web_search                public mentions, recent news
  - mcp-web.fetch_webpage             website read for signals
  - mcp-knowledge.search_wikipedia    background on the area
  - inline.find_local_businesses      Overpass API — shops / amenities
                                      (no key, OSM-backed)
  - inline.set_target_location, add_business_category, set_pitch_focus
  - inline.save_leads                 the structured card the right panel renders

Run:
    python main.py
    python main.py --port 28822
    python main.py --provider anthropic

Then open: http://127.0.0.1:28822

Environment variables:
    LLM_PROVIDER          rits | anthropic | openai | watsonx | litellm | ollama
    LLM_MODEL             model name override
    AGENT_SETTING_CONFIG  CUGA settings TOML (defaulted in make_agent)
    TAVILY_API_KEY        used by mcp-web.web_search (set on the MCP host)
    CUGA_TARGET=ce        forces public Code Engine MCP URLs
    MCP_<NAME>_URL        per-server URL override
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ── Path bootstrap — must come before local imports ─────────────────────
_DIR       = Path(__file__).parent
_DEMOS_DIR = _DIR.parent
for _p in (str(_DIR), str(_DEMOS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Default to the hosted Code Engine MCP servers — Ouroboros uses geo / web /
# knowledge tools that ship there. A user-supplied CUGA_TARGET still wins.
os.environ.setdefault("CUGA_TARGET", "ce")

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


# ── Per-thread session store ────────────────────────────────────────────
_sessions: dict[str, dict] = {}


def _get_session(thread_id: str) -> dict:
    if thread_id not in _sessions:
        _sessions[thread_id] = {
            "target_location":   "",
            "target_lat":        None,
            "target_lon":        None,
            "categories":        [],     # business categories the user is hunting
            "pitch_focus":       "",     # e.g. "order-taking chat bot", "appointment booking"
            "leads":             None,   # the structured card
            "history":           [],     # prior shortlists
        }
    return _sessions[thread_id]


def _append_unique(lst: list[str], value: str) -> None:
    if value and value.lower() not in [v.lower() for v in lst]:
        lst.append(value)


# ── Overpass query for local businesses ─────────────────────────────────
# Categories the agent can pass to find_local_businesses. Each maps to a
# bag of OSM tags. Keep this list small and intentional — the prompt
# references the keys verbatim.
_CATEGORY_TAGS: dict[str, list[tuple[str, str]]] = {
    "restaurants":     [("amenity", "restaurant")],
    "cafes":           [("amenity", "cafe")],
    "bars":            [("amenity", "bar"), ("amenity", "pub")],
    "salons":          [("shop", "hairdresser"), ("shop", "beauty")],
    "fitness":         [("leisure", "fitness_centre"), ("leisure", "sports_centre")],
    "clinics":         [("amenity", "clinic"), ("amenity", "doctors"), ("amenity", "dentist")],
    "veterinary":      [("amenity", "veterinary")],
    "auto":            [("shop", "car_repair"), ("amenity", "car_wash")],
    "boutiques":       [("shop", "clothes"), ("shop", "shoes"), ("shop", "jewelry")],
    "real_estate":     [("office", "estate_agent")],
    "lawyers":         [("office", "lawyer")],
    "accountants":     [("office", "accountant"), ("office", "financial")],
    "hotels":          [("tourism", "hotel"), ("tourism", "guest_house"), ("tourism", "motel")],
    "bakeries":        [("shop", "bakery"), ("shop", "pastry")],
    "florists":        [("shop", "florist")],
    "tutoring":        [("amenity", "language_school"), ("amenity", "tutoring")],
}


def _overpass_query(lat: float, lon: float, radius_m: int, category: str) -> str:
    tags = _CATEGORY_TAGS[category]
    blocks = []
    for k, v in tags:
        for kind in ("node", "way", "relation"):
            blocks.append(f'{kind}["{k}"="{v}"](around:{radius_m},{lat},{lon});')
    return f"[out:json][timeout:25];({' '.join(blocks)});out tags center 60;"


# ── Website signal classifier ───────────────────────────────────────────
# Keywords mapped to the agent capability they imply. These are intentionally
# crude — the agent does the synthesis. We just give it pre-extracted hooks
# so the pitch can reference concrete features instead of vague generalities.
_SIGNAL_PATTERNS: dict[str, list[str]] = {
    "has_online_ordering":  ["order online", "order now", "place an order", "place order",
                             "online ordering", "doordash", "ubereats", "deliveroo",
                             "swiggy", "zomato order", "add to cart", "checkout"],
    "has_online_booking":   ["book online", "book now", "book a table", "reserve a table",
                             "make a reservation", "book an appointment", "schedule appointment",
                             "schedule a visit", "book your", "reserve now", "opentable",
                             "calendly", "squareup.com/appointments"],
    "has_contact_form":     ["contact form", "send us a message", "send a message",
                             "get in touch", "request a quote", "request a callback",
                             "leave us a message", "drop us a line"],
    "has_chat_widget":      ["live chat", "chat with us", "chat now", "ask a question",
                             "we're online", "intercom.com", "drift.com", "tawk.to"],
    "phone_first":          ["call us", "call to book", "call to order", "call to make",
                             "call ahead", "call for", "phone orders only", "by phone"],
    "appointment_required": ["by appointment only", "appointment required",
                             "by appointment", "walk-ins not"],
    "has_faq":              ["faq", "frequently asked", "questions and answers"],
    "lists_languages":      ["se habla", "español", "english spoken", "français",
                             "mandarin", "हिंदी", "we speak"],
    "has_response_promise": ["we will respond", "respond within", "get back to you",
                             "reply within", "24-hour response"],
}


_HTML_TAG_RE   = None
_SCRIPT_RE     = None
_STYLE_RE      = None
_WHITESPACE_RE = None


def _strip_html(html: str) -> str:
    """Tiny HTML-to-text shim. Good enough to mine keyword hits; we are not
    rendering the page, just classifying it."""
    import re
    global _HTML_TAG_RE, _SCRIPT_RE, _STYLE_RE, _WHITESPACE_RE
    if _HTML_TAG_RE is None:
        _SCRIPT_RE     = re.compile(r"<script[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
        _STYLE_RE      = re.compile(r"<style[^>]*>.*?</style>",   re.IGNORECASE | re.DOTALL)
        _HTML_TAG_RE   = re.compile(r"<[^>]+>")
        _WHITESPACE_RE = re.compile(r"\s+")
    txt = _SCRIPT_RE.sub(" ", html or "")
    txt = _STYLE_RE.sub(" ", txt)
    txt = _HTML_TAG_RE.sub(" ", txt)
    txt = txt.replace("&nbsp;", " ").replace("&amp;", "&") \
             .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return _WHITESPACE_RE.sub(" ", txt).strip()


# Tech-smell patterns flag either:
#   - obviously dated front-end stack (jQuery 1.x, MooTools, Flash embeds)
#   - hand-coded table layouts (a strong correlate of a 2005-era site)
#   - generic "coming soon" / "lorem ipsum" placeholders
_TECH_SMELL_PATTERNS: list[tuple[str, str]] = [
    ("jquery 1.x",         r'jquery[-/]1\.\d'),
    ("jquery 2.x",         r'jquery[-/]2\.\d'),
    ("flash embed",        r'<embed[^>]+(application/x-shockwave-flash|\.swf)'),
    ("mootools",           r'mootools'),
    ("table layout",       r'(?:<table[^>]*>\s*<tr[^>]*>\s*<td[^>]*>.*?</td>.*?</tr>.*?){3,}'),
    ("lorem ipsum",        r'lorem\s+ipsum'),
    ("coming soon",        r'coming\s+soon|under\s+construction|site\s+is\s+being'),
    ("font face shim",     r'<font\s+face=|<center>'),
    ("flash require",      r'requireflash|swfobject'),
]


def _detect_tech_smells(html: str) -> list[str]:
    import re
    out: list[str] = []
    h = (html or "")[:200_000]   # cap — we are scanning, not parsing
    for label, pattern in _TECH_SMELL_PATTERNS:
        try:
            if re.search(pattern, h, re.IGNORECASE | re.DOTALL):
                out.append(label)
        except re.error:
            continue
    return out


def _audit_freshness(html: str, response_url: str) -> dict:
    """Inspect the raw HTML for freshness signals: SSL, viewport,
    SEO meta, copyright year, social-meta tags. Return a dict the agent
    can quote in its pitch and email draft."""
    import re
    from datetime import datetime

    h = html or ""

    # SSL — based on the *final* URL after redirects.
    is_https = (response_url or "").lower().startswith("https://")

    # Viewport meta — strong signal a site was at least once mobile-aware.
    mobile_responsive = bool(re.search(
        r'<meta[^>]+name=["\']viewport["\']', h, re.IGNORECASE,
    ))

    # SEO basics
    has_meta_description = bool(re.search(
        r'<meta[^>]+name=["\']description["\']', h, re.IGNORECASE,
    ))
    has_og_tags = bool(re.search(
        r'<meta[^>]+property=["\']og:', h, re.IGNORECASE,
    ))
    has_favicon = bool(re.search(
        r'<link[^>]+rel=["\'](?:shortcut\s+)?icon["\']', h, re.IGNORECASE,
    ))

    # Copyright year (most recent 4-digit year in a copyright phrase).
    years: list[int] = []
    for pat in (
        r'(?:©|&copy;|copyright)\s*\D{0,5}(\d{4})\s*[-–]\s*(\d{4})',
        r'(?:©|&copy;|copyright)\s*\D{0,5}(\d{4})',
    ):
        for m in re.finditer(pat, h, re.IGNORECASE):
            for g in m.groups():
                if g and 1995 <= int(g) <= 2100:
                    years.append(int(g))
    copyright_year = max(years) if years else None
    current_year   = datetime.now().year
    years_stale    = (current_year - copyright_year) if copyright_year else None

    # Tech smells
    tech_smells = _detect_tech_smells(h)

    looks_outdated = bool(
        (not is_https)
        or (not mobile_responsive)
        or (years_stale is not None and years_stale >= 3)
        or tech_smells
    )

    return {
        "is_https":              is_https,
        "mobile_responsive":     mobile_responsive,
        "has_meta_description":  has_meta_description,
        "has_og_tags":           has_og_tags,
        "has_favicon":           has_favicon,
        "copyright_year":        copyright_year,
        "years_stale":           years_stale,
        "tech_smells":           tech_smells,
        "looks_outdated":        looks_outdated,
    }


def _classify_signals(text: str, freshness: dict | None = None) -> dict:
    t = (text or "").lower()
    out = {k: any(p in t for p in pats) for k, pats in _SIGNAL_PATTERNS.items()}
    # Capability gap score: phone-first AND missing self-serve options.
    out["agent_unblock_score"] = int(
        out["phone_first"]
        + (not out["has_online_ordering"])
        + (not out["has_online_booking"])
        + (not out["has_chat_widget"])
    )
    if freshness is not None:
        out.update(freshness)
    return out


def _businesses_from_overpass(elements: list[dict]) -> list[dict]:
    """Extract a lean per-business dict from Overpass output.

    Lat/lon are intentionally dropped from the returned dict — the agent
    doesn't reference per-business coordinates downstream (the session
    holds the area centroid from geocode), and shaving them keeps each
    tool result smaller in the running context.
    """
    out: list[dict] = []
    for el in elements:
        tags = el.get("tags") or {}
        name = (tags.get("name") or "").strip()
        if not name:
            continue
        out.append({
            "name":     name,
            "category": tags.get("amenity") or tags.get("shop")
                          or tags.get("office") or tags.get("leisure")
                          or tags.get("tourism") or "",
            "address":  ", ".join(filter(None, [
                tags.get("addr:housenumber"), tags.get("addr:street"),
                tags.get("addr:city"), tags.get("addr:postcode"),
            ])),
            "phone":    tags.get("phone") or tags.get("contact:phone") or "",
            "website":  tags.get("website") or tags.get("contact:website") or "",
            "email":    tags.get("email") or tags.get("contact:email") or "",
            "osm":      f"https://www.openstreetmap.org/{el.get('type')}/{el.get('id')}",
        })
    seen = set()
    unique = []
    for b in out:
        key = b["name"].lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(b)
    return unique


# ── Tools ────────────────────────────────────────────────────────────────
def _make_tools():
    """MCP-loaded tools (geo, web, knowledge) + inline @tool defs:
    - find_local_businesses        Overpass API (no key needed)
    - set_target_location          remember the active location + coords
    - add_business_category, set_pitch_focus   bias the search
    - get_session_state            recall prior context
    - save_leads                   persist the right-panel card
    """
    from langchain_core.tools import tool
    from _mcp_bridge import load_tools

    mcp_tools = load_tools(["geo", "web", "knowledge"])

    @tool
    def find_local_businesses(
        thread_id: str,
        lat: float,
        lon: float,
        category: str,
        radius_m: int = 4000,
    ) -> str:
        """Find local businesses around a coordinate using OpenStreetMap's
        Overpass API. No API key required.

        Args:
            thread_id: Current session/thread ID (always pass through).
            lat:       Latitude (geocode first to get this).
            lon:       Longitude.
            category:  One of: restaurants, cafes, bars, salons, fitness,
                       clinics, veterinary, auto, boutiques, real_estate,
                       lawyers, accountants, hotels, bakeries, florists,
                       tutoring.
            radius_m:  Search radius in meters (default 4000 = ~4 km).

        Returns:
            tool_result envelope; data has shape:
              {"category": str, "count": int, "businesses": [
                  {"name", "category", "address", "phone", "website",
                   "email", "lat", "lon", "osm"}, ...
              ]}
        """
        _ = thread_id  # not stored; just accepted to match the convention
        if category not in _CATEGORY_TAGS:
            return json.dumps({
                "ok": False, "code": "bad_input",
                "error": f"unknown category {category!r}. "
                         f"Valid: {sorted(_CATEGORY_TAGS)}",
            })
        try:
            import httpx
            query = _overpass_query(float(lat), float(lon),
                                    int(radius_m), category)
            with httpx.Client(timeout=30.0) as client:
                r = client.post(
                    "https://overpass-api.de/api/interpreter",
                    data={"data": query},
                    headers={"User-Agent": "ouroboros-cuga/1.0"},
                )
                r.raise_for_status()
                payload = r.json()
            businesses = _businesses_from_overpass(payload.get("elements") or [])
            # Cap at 15 to keep the running context bounded. The agent only
            # shortlists 5–8 leads anyway; more than 15 raw Overpass hits
            # mostly chew tokens without adding signal.
            return json.dumps({"ok": True, "data": {
                "category":   category,
                "count":      len(businesses),
                "businesses": businesses[:15],
            }})
        except Exception as exc:
            return json.dumps({
                "ok": False, "code": "upstream",
                "error": f"overpass failed: {exc}",
            })

    @tool
    def analyze_business_website(
        thread_id: str,
        name: str,
        website_url: str,
        max_chars: int = 1500,
    ) -> str:
        """Fetch a business's website and extract signals that tell us
        whether a CUGA agent would visibly help (no online ordering →
        order-bot pitch; phone-first contact → chat pitch; no FAQ → support
        pitch; etc.).

        Use this in the deep-dive phase, AFTER find_local_businesses turned
        up the URL. Skip it when website_url is empty — that's what the
        web_search corroboration step is for.

        Args:
            thread_id:   Current session/thread ID.
            name:        Business name (for logs / errors only).
            website_url: Absolute URL of the business's homepage.
            max_chars:   Cap on the returned text excerpt (default 4000).

        Returns:
            tool_result envelope; data has shape:
              {
                "url":          str,
                "title":        str,           # <title> if found, else ""
                "signals": {
                  // Capability gaps — TRUE when feature is present.
                  "has_online_ordering":   bool,
                  "has_online_booking":    bool,
                  "has_contact_form":      bool,
                  "has_chat_widget":       bool,
                  "has_faq":               bool,
                  "has_response_promise":  bool,
                  "lists_languages":       bool,
                  // Friction — TRUE means the site has this property AND it is bad.
                  "phone_first":           bool,
                  "appointment_required":  bool,
                  // Capability-gap aggregate (0..4, higher = bigger CUGA opportunity).
                  "agent_unblock_score":   int,
                  // Freshness — surface "the site is stale" as its own pitch wedge.
                  "is_https":              bool,
                  "mobile_responsive":     bool,
                  "has_meta_description":  bool,
                  "has_og_tags":           bool,
                  "has_favicon":           bool,
                  "copyright_year":        int | null,
                  "years_stale":           int | null,    // current_year - copyright_year
                  "tech_smells":           [str],          // e.g. ["jquery 1.x", "flash embed", "table layout"]
                  "looks_outdated":        bool             // any-of staleness heuristic
                },
                "text_excerpt": str            # cleaned text, capped at max_chars
              }
        """
        _ = thread_id
        if not website_url:
            return json.dumps({"ok": False, "code": "bad_input",
                               "error": "website_url is empty"})
        try:
            import httpx, re
            with httpx.Client(timeout=15.0,
                              follow_redirects=True,
                              headers={"User-Agent": "ouroboros-cuga/1.0 (research)"}) as client:
                r = client.get(website_url)
                r.raise_for_status()
                html = r.text or ""
            title_m = re.search(r"<title[^>]*>(.*?)</title>", html,
                                re.IGNORECASE | re.DOTALL)
            title     = (title_m.group(1).strip() if title_m else "")[:200]
            text      = _strip_html(html)
            freshness = _audit_freshness(html, str(r.url))
            signals   = _classify_signals(text, freshness=freshness)
            return json.dumps({"ok": True, "data": {
                "url":          str(r.url),
                "title":        title,
                "signals":      signals,
                "text_excerpt": text[:max_chars],
            }})
        except Exception as exc:
            return json.dumps({
                "ok": False, "code": "upstream",
                "error": f"website fetch failed for {name!r}: {exc}",
            })

    @tool
    def set_target_location(
        thread_id: str,
        location: str,
        lat: float | None = None,
        lon: float | None = None,
    ) -> str:
        """Save the location the user is hunting in. Call this after geocode
        so the lat/lon are stored alongside the human-readable name.

        Args:
            thread_id: Current session/thread ID.
            location:  Human label, e.g. "Westchester, NY" or "Bangalore HSR".
            lat:       Latitude from geocode.
            lon:       Longitude from geocode.
        """
        if not location:
            return json.dumps({"ok": False, "code": "bad_input",
                               "error": "location is empty"})
        s = _get_session(thread_id)
        s["target_location"] = location.strip()
        if lat is not None: s["target_lat"] = float(lat)
        if lon is not None: s["target_lon"] = float(lon)
        return json.dumps({"ok": True, "data": {
            "target_location": s["target_location"],
            "target_lat":      s["target_lat"],
            "target_lon":      s["target_lon"],
        }})

    @tool
    def add_business_category(thread_id: str, category: str) -> str:
        """Add a business category to the hunt list. Categories from the
        find_local_businesses docstring are preferred but free-text is OK
        (e.g. "yoga studios").

        Args:
            thread_id: Current session/thread ID.
            category:  Business category keyword.
        """
        s = _get_session(thread_id)
        normalized = (category or "").strip().lower()
        if not normalized:
            return json.dumps({"ok": False, "code": "bad_input",
                               "error": "category is empty"})
        _append_unique(s["categories"], normalized)
        return json.dumps({"ok": True, "data": {"categories": s["categories"]}})

    @tool
    def set_pitch_focus(thread_id: str, focus: str) -> str:
        """Save the kind of CUGA capability to pitch on this hunt
        (e.g. "order-taking chatbot", "appointment booking",
        "lead capture + follow-up", "customer support FAQ"). Pass an empty
        string to clear.

        Args:
            thread_id: Current session/thread ID.
            focus:     Short phrase, or "" to clear.
        """
        s = _get_session(thread_id)
        s["pitch_focus"] = (focus or "").strip()
        return json.dumps({"ok": True, "data": {"pitch_focus": s["pitch_focus"]}})

    @tool
    def get_session_state(thread_id: str) -> str:
        """Read everything tracked for this session: location, lat/lon,
        categories, pitch focus, and whether a lead board exists. Call this
        at the start of a hunt to recall prior context.

        Args:
            thread_id: Current session/thread ID.
        """
        s = _get_session(thread_id)
        return json.dumps({"ok": True, "data": {
            "target_location": s["target_location"],
            "target_lat":      s["target_lat"],
            "target_lon":      s["target_lon"],
            "categories":      s["categories"],
            "pitch_focus":     s["pitch_focus"],
            "has_leads":       s["leads"] is not None,
        }})

    @tool
    def save_leads(thread_id: str, leads_json: str) -> str:
        """Persist the structured lead board the right panel renders. Call
        this at the END of every hunt, after you have shortlisted businesses
        and written a tailored CUGA pitch for each.

        Args:
            thread_id:  Current session/thread ID.
            leads_json: A JSON object with this shape:
                {
                  "location":        str,           # human label
                  "display_name":    str,           # canonical from geocode
                  "lat":             float,
                  "lon":             float,
                  "summary":         str,           # 1–2 sentence overview of the area
                  "leads": [                         # 5–8 items: top 3 deep-dived, rest preliminary
                    {
                      "name":           str,
                      "category":       str,         # e.g. "restaurant"
                      "address":        str,         # may be ""
                      "website":        str,         # may be ""
                      "phone":          str,         # may be ""
                      "email":          str,         # may be ""; from OSM if available
                      "fit_score":      int,         # 1..10
                      "use_case":       str,         # e.g. "Order-taking chat bot for delivery + reservations"
                      "pitch":          str,         # deep-dive: 2–3 specific sentences. preliminary: 1–2 sentences from OSM only.
                      "evidence":       [{"title": str, "url": str}],   # web_search citations (deep-dive only)
                      "osm":            str,         # OSM URL from find_local_businesses

                      // The fields below are REQUIRED for the top 3
                      // deep-dived leads. For lower-ranked candidates
                      // (ranks 4–8), set deep_dive=false and either omit
                      // the deep-dive fields or pass empty values — the
                      // UI hides empty blocks.

                      "deep_dive":      bool,        // true for top 3, false for rest
                      "website_signals": {            // straight from analyze_business_website
                        "has_online_ordering":  bool,
                        "has_online_booking":   bool,
                        "has_contact_form":     bool,
                        "has_chat_widget":      bool,
                        "has_faq":              bool,
                        "has_response_promise": bool,
                        "phone_first":          bool,
                        "appointment_required": bool,
                        "lists_languages":      bool,
                        "agent_unblock_score":  int,
                        "is_https":             bool,
                        "mobile_responsive":    bool,
                        "has_meta_description": bool,
                        "has_og_tags":          bool,
                        "has_favicon":          bool,
                        "copyright_year":       int | null,
                        "years_stale":          int | null,
                        "tech_smells":          [str],
                        "looks_outdated":       bool
                      },
                      "review_friction": [           // 0–4 verbatim grievances mined from web_search snippets
                        {
                          "pattern":    str,          // short label, e.g. "phone unanswered"
                          "quote":      str,          // verbatim phrase from a review snippet
                          "source_url": str           // the web_search hit it came from
                        }
                      ],
                      "email_draft": {                // the cold email — 120–180 words. REQUIRED for deep-dive leads only.
                        "subject": str,                 // for non-deep-dive leads, omit or use {"subject": "", "body": ""}
                        "body":    str
                      }
                    }
                  ],
                  "next_steps": [str]                # 2–4 outreach moves the user can take
                }
        """
        s = _get_session(thread_id)
        try:
            obj = json.loads(leads_json)
            if not isinstance(obj, dict):
                return json.dumps({"ok": False, "code": "bad_input",
                                   "error": "leads_json must be a JSON object"})
            obj["_at"] = datetime.now(timezone.utc).isoformat()
            s["leads"] = obj
            s["history"].insert(0, obj)
            s["history"] = s["history"][:6]
            log.info("[%s] leads saved: %d items in %s",
                     thread_id[:8],
                     len(obj.get("leads", []) or []),
                     obj.get("location", "?"))
            return json.dumps({"ok": True, "data": {"saved": True,
                                                    "count": len(obj.get("leads", []) or [])}})
        except json.JSONDecodeError as exc:
            return json.dumps({"ok": False, "code": "bad_input",
                               "error": f"invalid JSON: {exc}"})

    inline_tools = [
        find_local_businesses, analyze_business_website,
        set_target_location, add_business_category, set_pitch_focus,
        get_session_state, save_leads,
    ]

    return [*mcp_tools, *inline_tools]


# ── System prompt ────────────────────────────────────────────────────────
# Kept tight to preserve context budget. Per-tool details live in the tool
# docstrings (the agent re-reads those on every call); the prompt only
# names the workflow.
_SYSTEM = """\
# Ouroboros — sales-dev scout for CUGA

Find local businesses that would visibly benefit from a CUGA agent
(restaurants → order bots; salons/clinics/vets → booking; hotels →
concierge; lawyers/realtors → lead capture; boutiques → product Q&A).
Bias to independents; skip global chains.

## Per request, do this once

1. `set_target_location(thread_id, location)` then `geocode(place)` then
   `set_target_location` again WITH the lat/lon from geocode.
2. `get_session_state(thread_id)` — recall categories + pitch_focus.
3. If the user named a category or pitch focus, call
   `add_business_category` / `set_pitch_focus`.

## Wide net

4. For 1–3 sensible categories, call
   `find_local_businesses(thread_id, lat, lon, category, radius_m=4000)`.
   Score every result 1–10: +3 if business type matches `pitch_focus`,
   +2 if has a website, +2 if has a phone/address, +1 if independent.
   Keep the top 5–8.

## Deep-dive (top 3 only)

For each of the top 3 in turn:
  a. If `website` is present: `analyze_business_website(thread_id, name,
     website_url)`. Read its `signals` dict — `agent_unblock_score`
     (0..4) and `looks_outdated` are the headline signals.
  b. `web_search("<name> <city> reviews", max_results=4)`. Read snippets.
  c. Extract 0–4 `{pattern, quote, source_url}` items. `quote` MUST be a
     verbatim fragment of a snippet — never paraphrase. If no friction
     found, return `review_friction: []` (don't fabricate).
  d. Refine fit_score: +unblock_score, +1 per friction item, +1 if
     `looks_outdated`. Cap at 10.

## Pitch + email (deep-dive leads only)

For each top-3 lead:
  - `pitch` (2–3 sentences) MUST cite at least one concrete signal:
    a verbatim review quote, OR a missing website feature, OR a
    staleness flag. Then name the CUGA capability that closes the gap.
    End with measurable lift. "Could benefit from AI" is banned.
  - `email_draft = {subject, body}`, 120–180 words. Subject hooks on the
    signal (no "Quick chat about AI"). Body: open with the verbatim
    quote or signal → one empathy line → one CUGA capability line → one
    lift line → CTA "Worth a 15-min call next week?". Sign "— The CUGA
    team". No `[PLACEHOLDERS]`. No discounts, free trials, or fabricated
    case studies.

For ranks 4–8: 1–2 sentence preliminary pitch from OSM data alone.
`deep_dive: false`, omit `email_draft`. User can request deep-dives by
name later.

## Finish

5. `save_leads(thread_id, leads_json)` — see its docstring for the exact
   schema.
6. Reply with 2 short paragraphs naming the top 3 leads and their angle,
   plus one line of next steps. The right panel renders the rest.

## Thread ID
Every user message starts with `[thread:<UUID>]`. Extract the UUID and
pass it unchanged as `thread_id` to every inline tool.
"""


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
    )


# ── Request models ──────────────────────────────────────────────────────
class AskReq(BaseModel):
    question: str
    thread_id: str = ""


# ── HTTP server ──────────────────────────────────────────────────────────
def _web(port: int) -> None:
    import uvicorn

    app = FastAPI(title="Ouroboros", docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    _agent = None

    def _get_agent():
        nonlocal _agent
        if _agent is None:
            log.info("Initialising CugaAgent (mcp: geo, web, knowledge)…")
            _agent = make_agent()
            log.info("CugaAgent ready.")
        return _agent

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(_HTML)

    @app.post("/ask")
    async def api_ask(req: AskReq):
        thread_id = req.thread_id or str(uuid.uuid4())
        augmented = f"[thread:{thread_id}] {req.question}"
        try:
            agent = _get_agent()
            result = await agent.invoke(augmented, thread_id=thread_id)
            return {"answer": str(result), "thread_id": thread_id}
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

    print(f"\n  Ouroboros  →  http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ── CLI entry point ──────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Ouroboros — CUGA-powered lead generation")
    parser.add_argument("--port", type=int, default=28822)
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
