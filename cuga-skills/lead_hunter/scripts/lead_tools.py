"""CLI helpers for the lead_hunter skill.

The agent invokes this script via `run_command` (or its host's subprocess
primitive) and parses JSON from stdout:

    python scripts/lead_tools.py geocode 'Pleasantville, NY'
    python scripts/lead_tools.py find_businesses 41.13 -73.78 restaurants 4000
    python scripts/lead_tools.py audit_site 'https://example-cafe.com'
    python scripts/lead_tools.py search_reviews "Joe's Pizza" 'Pleasantville NY' 4
    python scripts/lead_tools.py search_owner "Joe's Pizza" 'Pleasantville NY'
    python scripts/lead_tools.py guess_emails Maya Iyer miassalon.com
    python scripts/lead_tools.py estimate_revenue restaurants \
        '{"review_count": 220, "locations_count": 1}'

Tavily-backed subcommands (`search_reviews`, `search_owner`) require
`TAVILY_API_KEY` in the environment. Without it they return
`{"error": "TAVILY_API_KEY not set"}` and exit 1.

Exit codes: 0 = ok, 1 = runtime error, 2 = usage error.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse

import httpx


_NOMINATIM = "https://nominatim.openstreetmap.org/search"
_OVERPASS = "https://overpass-api.de/api/interpreter"
_TAVILY = "https://api.tavily.com/search"
_UA = {"User-Agent": "lead-hunter-skill/1.0 (https://skills.sh)"}


# ─────────────────────────────────────────────────────────────────────────
# Phase 1: geocode + find_businesses
# ─────────────────────────────────────────────────────────────────────────

_CATEGORY_TAGS: dict[str, list[tuple[str, str]]] = {
    "restaurants":  [("amenity", "restaurant")],
    "cafes":        [("amenity", "cafe")],
    "bars":         [("amenity", "bar"), ("amenity", "pub")],
    "salons":       [("shop", "hairdresser"), ("shop", "beauty")],
    "fitness":      [("leisure", "fitness_centre"), ("leisure", "sports_centre")],
    "clinics":      [("amenity", "clinic"), ("amenity", "doctors"),
                     ("amenity", "dentist"), ("amenity", "hospital"),
                     ("amenity", "pharmacy"), ("healthcare", "centre"),
                     ("healthcare", "physiotherapist"),
                     ("healthcare", "psychotherapist"),
                     ("healthcare", "alternative")],
    "veterinary":   [("amenity", "veterinary")],
    "auto":         [("shop", "car_repair"), ("amenity", "car_wash")],
    "boutiques":    [("shop", "clothes"), ("shop", "shoes"), ("shop", "jewelry")],
    "real_estate":  [("office", "estate_agent")],
    "lawyers":      [("office", "lawyer")],
    "accountants":  [("office", "accountant"), ("office", "financial")],
    "hotels":       [("tourism", "hotel"), ("tourism", "guest_house"),
                     ("tourism", "motel")],
    "bakeries":     [("shop", "bakery"), ("shop", "pastry")],
    "florists":     [("shop", "florist")],
    "tutoring":     [("amenity", "language_school"), ("amenity", "tutoring")],
}


def geocode(place: str) -> dict:
    """Resolve a place name → {lat, lon, display_name} via Nominatim."""
    r = httpx.get(
        _NOMINATIM,
        params={"q": place, "format": "json", "limit": 1},
        headers=_UA, timeout=20.0,
    )
    r.raise_for_status()
    hits = r.json() or []
    if not hits:
        return {"error": f"No geocode result for {place!r}"}
    h = hits[0]
    return {
        "lat":          float(h["lat"]),
        "lon":          float(h["lon"]),
        "display_name": h.get("display_name", place),
    }


def _overpass_query(lat: float, lon: float, radius_m: int, category: str) -> str:
    tags = _CATEGORY_TAGS[category]
    blocks = []
    for k, v in tags:
        for kind in ("node", "way", "relation"):
            blocks.append(f'{kind}["{k}"="{v}"](around:{radius_m},{lat},{lon});')
    return f"[out:json][timeout:25];({' '.join(blocks)});out tags center 60;"


def _businesses_from_overpass(elements: list[dict]) -> list[dict]:
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
    seen, unique = set(), []
    for b in out:
        key = b["name"].lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(b)
    return unique


def find_businesses(lat: float, lon: float, category: str,
                    radius_m: int = 4000) -> dict:
    """List businesses in one OSM category around (lat, lon)."""
    if category not in _CATEGORY_TAGS:
        return {
            "error": f"unknown category {category!r}. "
                     f"Valid: {sorted(_CATEGORY_TAGS)}",
            "code":  "bad_input",
        }
    query = _overpass_query(float(lat), float(lon), int(radius_m), category)
    with httpx.Client(timeout=30.0, headers=_UA) as c:
        r = c.post(_OVERPASS, data={"data": query})
        r.raise_for_status()
        payload = r.json()
    businesses = _businesses_from_overpass(payload.get("elements") or [])
    return {
        "category":   category,
        "count":      len(businesses),
        "businesses": businesses[:8],
    }


# ─────────────────────────────────────────────────────────────────────────
# Phase 2.a: audit_site (capability + freshness + stack fingerprint)
# ─────────────────────────────────────────────────────────────────────────

_SIGNAL_PATTERNS: dict[str, list[str]] = {
    "has_online_ordering":  ["order online", "order now", "place an order",
                             "place order", "online ordering", "doordash",
                             "ubereats", "deliveroo", "swiggy", "zomato order",
                             "add to cart", "checkout"],
    "has_online_booking":   ["book online", "book now", "book a table",
                             "reserve a table", "make a reservation",
                             "book an appointment", "schedule appointment",
                             "schedule a visit", "book your", "reserve now",
                             "opentable", "calendly",
                             "squareup.com/appointments"],
    "has_contact_form":     ["contact form", "send us a message",
                             "send a message", "get in touch",
                             "request a quote", "request a callback",
                             "leave us a message", "drop us a line"],
    "has_chat_widget":      ["live chat", "chat with us", "chat now",
                             "ask a question", "we're online",
                             "intercom.com", "drift.com", "tawk.to"],
    "phone_first":          ["call us", "call to book", "call to order",
                             "call to make", "call ahead", "call for",
                             "phone orders only", "by phone"],
    "appointment_required": ["by appointment only", "appointment required",
                             "by appointment", "walk-ins not"],
    "has_faq":              ["faq", "frequently asked",
                             "questions and answers"],
    "lists_languages":      ["se habla", "español", "english spoken",
                             "français", "mandarin", "हिंदी", "we speak"],
    "has_response_promise": ["we will respond", "respond within",
                             "get back to you", "reply within",
                             "24-hour response"],
}

_TECH_SMELL_PATTERNS: list[tuple[str, str]] = [
    ("jquery 1.x",      r"jquery[-/]1\.\d"),
    ("jquery 2.x",      r"jquery[-/]2\.\d"),
    ("flash embed",     r'<embed[^>]+(application/x-shockwave-flash|\.swf)'),
    ("mootools",        r"mootools"),
    ("table layout",    r"(?:<table[^>]*>\s*<tr[^>]*>\s*<td[^>]*>.*?</td>.*?</tr>.*?){3,}"),
    ("lorem ipsum",     r"lorem\s+ipsum"),
    ("coming soon",     r"coming\s+soon|under\s+construction"),
    ("font face shim",  r"<font\s+face=|<center>"),
]

_FINGERPRINTS: list[tuple[str, str, str]] = [
    ("OpenTable",   r"opentable\.com/(restref|r|reserve|widget)",      "OpenTable booking widget"),
    ("Resy",        r"resy\.com/cities|resy_button|resy-widget",        "Resy booking embed"),
    ("Tock",        r"exploretock\.com|tockify\.com",                   "Tock booking"),
    ("Yelp Reservations", r"yelp\.com/biz_reservation|yelp-reservations", "Yelp Reservations"),
    ("Toast",       r"toasttab\.com|toast-tab\.com",                    "Toast online ordering / POS"),
    ("Square",      r"squareup\.com/appointments|square\.site",         "Square (appointments / online store)"),
    ("Clover",      r"clover\.com/online-ordering",                     "Clover online ordering"),
    ("Calendly",    r"calendly\.com",                                   "Calendly booking embed"),
    ("Mindbody",    r"clients\.mindbodyonline\.com|mindbody-iframe",    "Mindbody booking"),
    ("Booksy",      r"booksy\.com",                                     "Booksy booking"),
    ("Vagaro",      r"vagaro\.com",                                     "Vagaro booking"),
    ("Acuity",      r"acuityscheduling\.com",                           "Acuity Scheduling"),
    ("Zocdoc",      r"zocdoc\.com",                                     "Zocdoc booking"),
    ("Healthgrades", r"healthgrades\.com",                              "Healthgrades listing"),
    ("Practo",      r"practo\.com",                                     "Practo (clinic booking)"),
    ("DoorDash",    r"doordash\.com|order\.doordash\.com",              "DoorDash menu link"),
    ("Uber Eats",   r"ubereats\.com",                                   "Uber Eats menu link"),
    ("Grubhub",     r"grubhub\.com",                                    "Grubhub menu link"),
    ("Postmates",   r"postmates\.com",                                  "Postmates menu link"),
    ("Swiggy",      r"swiggy\.com",                                     "Swiggy menu link"),
    ("Zomato",      r"zomato\.com",                                     "Zomato listing or order"),
    ("Shopify",     r"cdn\.shopify\.com|shopify\.com/checkout",         "Shopify storefront"),
    ("WooCommerce", r"woocommerce|wp-content/plugins/woocommerce",      "WooCommerce store"),
    ("Wix Bookings", r"editor\.wix\.com.*bookings|wixapps\.net/bookings", "Wix Bookings"),
    ("Squarespace Scheduling", r"squarespace\.com/scheduling",          "Squarespace Scheduling"),
    ("HubSpot Forms", r"js\.hsforms\.net",                              "HubSpot form"),
    ("Intercom",    r"widget\.intercom\.io",                            "Intercom chat widget"),
    ("Drift",       r"js\.driftt\.com|drift\.com/widget",               "Drift chat widget"),
    ("Tawk.to",     r"embed\.tawk\.to",                                 "Tawk.to chat widget"),
    ("LiveChat",    r"cdn\.livechatinc\.com",                           "LiveChat widget"),
    ("Zendesk Chat", r"static\.zdassets\.com",                          "Zendesk widget"),
    ("Mailchimp",   r"mc\.us\d+\.list-manage\.com|mailchimp\.com",      "Mailchimp signup"),
    ("Google Reviews", r"google\.com/maps/embed|maps\.google\.com",     "Google Maps embed"),
]

_SCRIPT_RE = re.compile(r"<script[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
_STYLE_RE  = re.compile(r"<style[^>]*>.*?</style>",   re.IGNORECASE | re.DOTALL)
_TAG_RE    = re.compile(r"<[^>]+>")
_WS_RE     = re.compile(r"\s+")


def _strip_html(html: str) -> str:
    txt = _SCRIPT_RE.sub(" ", html or "")
    txt = _STYLE_RE.sub(" ", txt)
    txt = _TAG_RE.sub(" ", txt)
    txt = (txt.replace("&nbsp;", " ").replace("&amp;", "&")
              .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"'))
    return _WS_RE.sub(" ", txt).strip()


def _detect_tech_smells(html: str) -> list[str]:
    out: list[str] = []
    h = (html or "")[:200_000]
    for label, pattern in _TECH_SMELL_PATTERNS:
        try:
            if re.search(pattern, h, re.IGNORECASE | re.DOTALL):
                out.append(label)
        except re.error:
            continue
    return out


def _audit_freshness(html: str, response_url: str) -> dict:
    h = html or ""
    is_https = (response_url or "").lower().startswith("https://")
    mobile_responsive = bool(re.search(
        r'<meta[^>]+name=["\']viewport["\']', h, re.IGNORECASE,
    ))
    has_meta_description = bool(re.search(
        r'<meta[^>]+name=["\']description["\']', h, re.IGNORECASE,
    ))
    has_og_tags = bool(re.search(
        r'<meta[^>]+property=["\']og:', h, re.IGNORECASE,
    ))
    has_favicon = bool(re.search(
        r'<link[^>]+rel=["\'](?:shortcut\s+)?icon["\']', h, re.IGNORECASE,
    ))
    years: list[int] = []
    for pat in (
        r"(?:©|&copy;|copyright)\s*\D{0,5}(\d{4})\s*[-–]\s*(\d{4})",
        r"(?:©|&copy;|copyright)\s*\D{0,5}(\d{4})",
    ):
        for m in re.finditer(pat, h, re.IGNORECASE):
            for g in m.groups():
                if g and 1995 <= int(g) <= 2100:
                    years.append(int(g))
    copyright_year = max(years) if years else None
    years_stale    = (datetime.now().year - copyright_year) if copyright_year else None
    tech_smells    = _detect_tech_smells(h)
    looks_outdated = bool(
        (not is_https)
        or (not mobile_responsive)
        or (years_stale is not None and years_stale >= 3)
        or tech_smells
    )
    return {
        "is_https":             is_https,
        "mobile_responsive":    mobile_responsive,
        "has_meta_description": has_meta_description,
        "has_og_tags":          has_og_tags,
        "has_favicon":          has_favicon,
        "copyright_year":       copyright_year,
        "years_stale":          years_stale,
        "tech_smells":          tech_smells,
        "looks_outdated":       looks_outdated,
    }


def _classify_signals(text: str, freshness: dict) -> dict:
    t = (text or "").lower()
    out: dict[str, Any] = {
        k: any(p in t for p in pats) for k, pats in _SIGNAL_PATTERNS.items()
    }
    out["agent_unblock_score"] = int(
        out["phone_first"]
        + (not out["has_online_ordering"])
        + (not out["has_online_booking"])
        + (not out["has_chat_widget"])
    )
    out.update(freshness)
    return out


def _fingerprint_stack(html: str) -> list[dict]:
    found: list[dict] = []
    seen: set[str] = set()
    for name, pat, ev in _FINGERPRINTS:
        if name in seen:
            continue
        try:
            if re.search(pat, html, re.IGNORECASE):
                found.append({"name": name, "evidence": ev})
                seen.add(name)
        except re.error:
            continue
    return found


def audit_site(url: str, max_chars: int = 1500) -> dict:
    """Fetch a site once; classify capability, freshness, and stack."""
    if not url:
        return {"error": "url is empty", "code": "bad_input"}
    with httpx.Client(timeout=15.0, follow_redirects=True,
                      headers={"User-Agent": "lead-hunter-skill/1.0"}) as c:
        r = c.get(url)
        r.raise_for_status()
        html = r.text or ""
        final_url = str(r.url)
    title_m   = re.search(r"<title[^>]*>(.*?)</title>", html,
                          re.IGNORECASE | re.DOTALL)
    title     = (title_m.group(1).strip() if title_m else "")[:200]
    text      = _strip_html(html)
    freshness = _audit_freshness(html, final_url)
    signals   = _classify_signals(text, freshness)
    third     = _fingerprint_stack(html)
    return {
        "url":           final_url,
        "title":         title,
        "signals":       signals,
        "third_parties": third,
        "green_field":   len(third) == 0,
        "text_excerpt":  text[:max_chars],
    }


# ─────────────────────────────────────────────────────────────────────────
# Phase 2.b/c: Tavily-backed search
# ─────────────────────────────────────────────────────────────────────────

def _tavily_search(query: str, max_results: int = 5) -> dict:
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        return {
            "error": "TAVILY_API_KEY not set",
            "code":  "no_credentials",
        }
    r = httpx.post(
        _TAVILY,
        json={
            "api_key":      key,
            "query":        query,
            "max_results":  int(max_results),
            "search_depth": "basic",
        },
        timeout=25.0,
    )
    r.raise_for_status()
    body = r.json() or {}
    hits = []
    for it in (body.get("results") or [])[:int(max_results)]:
        if not isinstance(it, dict):
            continue
        hits.append({
            "title":   (it.get("title") or "").strip()[:200],
            "url":     it.get("url") or "",
            "snippet": (it.get("content") or "").strip()[:600],
        })
    return {"query": query, "hits": hits}


def search_reviews(name: str, city: str, max_results: int = 5,
                   complaints_focus: bool = False) -> dict:
    """Tavily search for review-site snippets about a business."""
    if complaints_focus:
        q = f'"{name}" {city} reviews complaints problems'
    else:
        q = f'"{name}" {city} reviews'
    return _tavily_search(q, max_results)


def search_owner(name: str, city: str, max_results: int = 5) -> dict:
    """Tavily search for owner / founder / GM mentions for a business."""
    q = f'"{name}" {city} (owner OR founder OR GM OR manager)'
    return _tavily_search(q, max_results)


# ─────────────────────────────────────────────────────────────────────────
# Phase 2.c: email pattern guess (no I/O)
# ─────────────────────────────────────────────────────────────────────────

def _domain_from_url(url: str) -> str:
    if not url:
        return ""
    if "://" not in url:
        url = "http://" + url
    host = urlparse(url).hostname or ""
    return host[4:] if host.lower().startswith("www.") else host


def guess_emails(first_name: str, last_name: str, domain: str) -> dict:
    """Generate ordered cold-email pattern candidates."""
    domain = _domain_from_url(domain) or domain
    f = re.sub(r"[^a-z]", "", (first_name or "").lower())
    l = re.sub(r"[^a-z]", "", (last_name  or "").lower())
    if not f or not l or not domain:
        return {"best_guess": None, "candidates": [], "domain": domain}
    candidates = [
        f"{f}.{l}@{domain}",
        f"{f[0]}{l}@{domain}",
        f"{f}@{domain}",
        f"{f}{l}@{domain}",
        f"{f}_{l}@{domain}",
        f"{l}.{f}@{domain}",
    ]
    return {
        "best_guess": candidates[0],
        "candidates": candidates,
        "domain":     domain,
    }


# ─────────────────────────────────────────────────────────────────────────
# Phase 2.d: revenue band heuristic (no I/O)
# ─────────────────────────────────────────────────────────────────────────

_VERTICAL_BASELINE_PER_EMPLOYEE: dict[str, int] = {
    "restaurant":  120_000,
    "cafe":         95_000,
    "bar":         110_000,
    "salon":        85_000,
    "fitness":      90_000,
    "clinic":      230_000,
    "veterinary":  220_000,
    "auto":        150_000,
    "boutique":    160_000,
    "real_estate": 200_000,
    "lawyer":      300_000,
    "accountant":  250_000,
    "hotel":       180_000,
    "bakery":       95_000,
    "florist":      90_000,
    "tutoring":     60_000,
}

_BAND_THRESHOLDS = [
    (200_000,      "< $200k",   0,         199_999),
    (1_000_000,    "$200k–$1M", 200_000,   999_999),
    (5_000_000,    "$1M–$5M",   1_000_000, 4_999_999),
    (float("inf"), "> $5M",     5_000_000, 999_999_999),
]


def _band_for(arr: int) -> tuple[str, int, int]:
    for limit, label, lo, hi in _BAND_THRESHOLDS:
        if arr < limit:
            return label, lo, hi
    return ">$5M", 5_000_000, 999_999_999


def estimate_revenue(business_type: str, signals: dict) -> dict:
    """Map size signals → ARR band. signals may contain employee_count,
    review_count, locations_count, years_in_business."""
    btype = (business_type or "").lower().strip().rstrip("s")
    per_emp = _VERTICAL_BASELINE_PER_EMPLOYEE.get(btype, 100_000)

    employees = signals.get("employee_count")
    reviews   = signals.get("review_count")
    locations = signals.get("locations_count") or 1
    years     = signals.get("years_in_business")

    rules: list[str] = []
    arr: Optional[int] = None

    if isinstance(employees, (int, float)) and employees > 0:
        arr = int(employees * per_emp * locations)
        rules.append(f"{int(employees)} employees × ${per_emp:,}/emp × {locations} loc")
    elif isinstance(reviews, (int, float)):
        if reviews >= 500:
            arr = 1_500_000 * locations
            rules.append(f"{int(reviews)} reviews → mid–large band")
        elif reviews >= 150:
            arr = 600_000 * locations
            rules.append(f"{int(reviews)} reviews → mid band")
        elif reviews >= 30:
            arr = 250_000 * locations
            rules.append(f"{int(reviews)} reviews → small–mid band")
        else:
            arr = 120_000 * locations
            rules.append(f"{int(reviews)} reviews → small band")
    elif locations > 1:
        arr = per_emp * 5 * locations
        rules.append(f"{locations} locations × ~5 emp baseline")
    else:
        return {
            "band":          "unknown",
            "band_low_usd":  None,
            "band_high_usd": None,
            "rationale":     "No public size signals found.",
            "rules_fired":   [],
            "confidence":    "low",
            "disclaimer":    "Estimated, not measured. Treat as a ranking aid only.",
        }

    if isinstance(years, (int, float)) and years >= 10:
        rules.append(f"{int(years)} years in business → established")

    band, lo, hi = _band_for(arr or 0)
    confidence = "medium" if len(rules) >= 2 else "low"
    return {
        "band":          band,
        "band_low_usd":  lo,
        "band_high_usd": hi,
        "rationale":     "; ".join(rules) or "Single signal estimate.",
        "rules_fired":   rules,
        "confidence":    confidence,
        "disclaimer":    "Estimated, not measured. Treat as a ranking aid only.",
    }


# ─────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────

_USAGE = """\
usage:
  python scripts/lead_tools.py geocode <place>
  python scripts/lead_tools.py find_businesses <lat> <lon> <category> [radius_m=4000]
  python scripts/lead_tools.py audit_site <url>
  python scripts/lead_tools.py search_reviews <name> <city> [max_results=5] [complaints_focus=0]
  python scripts/lead_tools.py search_owner <name> <city> [max_results=5]
  python scripts/lead_tools.py guess_emails <first_name> <last_name> <domain>
  python scripts/lead_tools.py estimate_revenue <category> <signals_json>

categories: restaurants, cafes, bars, salons, fitness, clinics, veterinary,
            auto, boutiques, real_estate, lawyers, accountants, hotels,
            bakeries, florists, tutoring
"""


def _bool(s: str) -> bool:
    return s.lower() in ("1", "true", "yes")


def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(_USAGE, file=sys.stderr)
        return 2
    cmd = argv[1]
    try:
        if cmd == "geocode":
            if len(argv) < 3:
                print(_USAGE, file=sys.stderr); return 2
            result: object = geocode(argv[2])

        elif cmd == "find_businesses":
            if len(argv) < 5:
                print(_USAGE, file=sys.stderr); return 2
            radius = int(argv[5]) if len(argv) > 5 else 4000
            result = find_businesses(float(argv[2]), float(argv[3]),
                                      argv[4], radius)

        elif cmd == "audit_site":
            if len(argv) < 3:
                print(_USAGE, file=sys.stderr); return 2
            result = audit_site(argv[2])

        elif cmd == "search_reviews":
            if len(argv) < 4:
                print(_USAGE, file=sys.stderr); return 2
            mr  = int(argv[4]) if len(argv) > 4 else 5
            cf  = _bool(argv[5]) if len(argv) > 5 else False
            result = search_reviews(argv[2], argv[3], mr, cf)

        elif cmd == "search_owner":
            if len(argv) < 4:
                print(_USAGE, file=sys.stderr); return 2
            mr = int(argv[4]) if len(argv) > 4 else 5
            result = search_owner(argv[2], argv[3], mr)

        elif cmd == "guess_emails":
            if len(argv) < 5:
                print(_USAGE, file=sys.stderr); return 2
            result = guess_emails(argv[2], argv[3], argv[4])

        elif cmd == "estimate_revenue":
            if len(argv) < 4:
                print(_USAGE, file=sys.stderr); return 2
            try:
                signals = json.loads(argv[3])
                if not isinstance(signals, dict):
                    raise ValueError("signals_json must be a JSON object")
            except (ValueError, json.JSONDecodeError) as e:
                print(json.dumps({"error": f"bad signals_json: {e}",
                                   "code": "bad_input"}), file=sys.stderr)
                return 2
            result = estimate_revenue(argv[2], signals)

        else:
            print(f"unknown command: {cmd!r}\n\n{_USAGE}", file=sys.stderr)
            return 2

    except httpx.HTTPError as e:
        print(json.dumps({"error": f"http: {type(e).__name__}: {e}",
                           "code": "upstream"}))
        return 1
    except Exception as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}))
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
