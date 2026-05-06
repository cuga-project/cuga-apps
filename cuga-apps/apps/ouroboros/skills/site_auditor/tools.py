"""Tools for the site_auditor skill — fetch + classify capability + freshness.

Single fetch, two analyses. Uses httpx + regex; no JS-render dependency.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from typing import Optional

import httpx


# ── Capability patterns ──────────────────────────────────────────────────
# Each pattern set names a self-serve feature whose ABSENCE is a CUGA wedge.
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


# ── HTML strip ───────────────────────────────────────────────────────────
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


# ── Audits ───────────────────────────────────────────────────────────────

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
    out = {k: any(p in t for p in pats) for k, pats in _SIGNAL_PATTERNS.items()}
    out["agent_unblock_score"] = int(
        out["phone_first"]
        + (not out["has_online_ordering"])
        + (not out["has_online_booking"])
        + (not out["has_chat_widget"])
    )
    out.update(freshness)
    return out


def _analyze(name: str, website_url: str, max_chars: int = 1500) -> dict:
    if not website_url:
        raise ValueError("website_url is empty")
    with httpx.Client(timeout=15.0, follow_redirects=True,
                      headers={"User-Agent": "ouroboros-site-auditor/1.0 (research)"}) as c:
        r = c.get(website_url)
        r.raise_for_status()
        html = r.text or ""
    title_m   = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title     = (title_m.group(1).strip() if title_m else "")[:200]
    text      = _strip_html(html)
    freshness = _audit_freshness(html, str(r.url))
    signals   = _classify_signals(text, freshness)
    return {
        "url":          str(r.url),
        "title":        title,
        "signals":      signals,
        "text_excerpt": text[:max_chars],
    }


# ── LangChain @tool ──────────────────────────────────────────────────────

try:
    from langchain_core.tools import tool

    @tool
    def analyze_business_website(name: str, website_url: str,
                                  max_chars: int = 1500) -> str:
        """Fetch a business website and classify capability gaps + freshness flaws.

        Args:
            name:        Business name (for logs).
            website_url: Absolute URL of the homepage.
            max_chars:   Cap on returned text excerpt (default 1500).
        """
        try:
            return json.dumps({"ok": True, "data": _analyze(name, website_url, max_chars)})
        except ValueError as e:
            return json.dumps({"ok": False, "error": str(e), "code": "bad_input"})
        except Exception as e:
            return json.dumps({
                "ok": False, "error": f"website fetch failed for {name!r}: {e}",
                "code": "upstream",
            })

    TOOLS = [analyze_business_website]
except ImportError:
    TOOLS = []


# ── Sandbox CLI ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"error": "usage: tools.py analyze_business_website <name> <url>"}),
              file=sys.stderr)
        sys.exit(2)
    if sys.argv[1] != "analyze_business_website":
        print(json.dumps({"error": f"unknown command {sys.argv[1]!r}"}), file=sys.stderr)
        sys.exit(2)
    print(json.dumps(_analyze(sys.argv[2], sys.argv[3])))
