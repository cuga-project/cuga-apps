"""
research.py — the app-specific logic behind Web Researcher. Pure functions
(no CUGA, no network) so they are easy to test.

  * MODES / pick_mode   — which Tavily tools each research mode may use, and a
                          deterministic "auto" choice from the question.
  * SOURCE_PROFILES /
    source_rules        — the user's source controls (domains, time window,
                          news) turned into Tavily parameters the app enforces.
  * egress_violations   — secrets and internal names never leave in a request.
  * quote_supported     — is a quoted sentence really on a page the run read?
  * split_claims        — pull the agent's ```json claims block out of its answer.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import urlparse

# ── Modes ─────────────────────────────────────────────────────────────────
# Each mode is one Tavily strength. `tools` is enforced in code: a call to a
# tool outside the mode is refused, and `budget` caps outside reads per run.

MODES: dict[str, dict[str, Any]] = {
    "quick": {
        "title": "Quick answer",
        "tools": {"tavily_search"},
        "budget": 3,
        "how": ("Run one or two focused tavily_search calls (search_depth 'fast'). Prefer the "
                "official source (the project, company or standard itself). Answer in 2-4 "
                "sentences. Quote the result snippets you rely on."),
    },
    "deep": {
        "title": "Deep dive",
        "tools": {"tavily_search", "tavily_extract"},
        "budget": 8,
        "how": ("Break the question into 2-4 sub-questions. Run tavily_search (search_depth "
                "'advanced') for each. Then call tavily_extract ONCE with the 2-4 best result URLs "
                "together in `urls` and a `query` naming the facts you need, so you get the exact "
                "passages. Quote from those passages."),
    },
    "site": {
        "title": "Site study",
        "tools": {"tavily_map", "tavily_crawl", "tavily_extract", "tavily_search"},
        "budget": 8,
        "how": ("Study one website. 1) tavily_map the site URL with `instructions` to see its "
                "structure. 2) tavily_crawl from the most relevant section's URL with `instructions` "
                "describing what to read — crawl reads several related pages at once. 3) Use "
                "tavily_extract (with a `query`) only for one or two specific pages the crawl missed. "
                "Answer only from that site, quoting its pages."),
    },
    "report": {
        "title": "Research report",
        "tools": {"tavily_research", "tavily_extract", "tavily_search"},
        "budget": 6,
        "how": ("Call tavily_research once with the full question as `input` (model given in the "
                "request). It returns a cited report. Then call tavily_extract on 2-3 of its most "
                "important sources with a `query`, so every claim you keep is quoted in the source "
                "page's own words, not the report's."),
    },
    "watch": {
        "title": "Watch (what's new)",
        "tools": {"tavily_search", "tavily_extract"},
        "budget": 5,
        "how": ("Find only what is NEW since the date given. Use tavily_search with topic 'news' and "
                "start_date set to that date. If nothing new and relevant was published, say "
                "'No new developments since <date>.' Do not repeat older background."),
    },
}

_REPORT_WORDS = re.compile(
    r"\b(report|landscape|overview|state of|comprehensive|in[- ]depth|market map|deep research)\b", re.I)
_URL = re.compile(r"https?://[^\s\"'<>)\]]+")


def first_url(text: str) -> str | None:
    m = _URL.search(text or "")
    return m.group(0).rstrip(".,;") if m else None


def pick_mode(question: str, requested: str = "auto", site_url: str = "") -> tuple[str, str]:
    """(mode, why). 'auto' picks deterministically so the choice is explainable."""
    if requested in MODES:
        return requested, "chosen"
    if site_url or first_url(question):
        return "site", "the question names a website"
    if _REPORT_WORDS.search(question or ""):
        return "report", "the question asks for a report or overview"
    return "deep", "default for open questions"


# ── Source controls ───────────────────────────────────────────────────────

SOCIAL_AND_FORUMS = [
    "reddit.com", "quora.com", "x.com", "twitter.com", "facebook.com", "instagram.com",
    "tiktok.com", "pinterest.com", "linkedin.com",
]
RESEARCH_SITES = [
    "arxiv.org", "openreview.net", "aclanthology.org", "semanticscholar.org", "nature.com",
    "science.org", "acm.org", "ieee.org", "nih.gov", "pnas.org",
]

SOURCE_PROFILES: dict[str, dict[str, Any]] = {
    "web":      {"title": "Whole web"},
    "no_social": {"title": "No social media or forums", "exclude_domains": SOCIAL_AND_FORUMS},
    "research": {"title": "Research papers", "include_domains": RESEARCH_SITES},
    "news":     {"title": "News", "topic": "news"},
    "custom":   {"title": "Custom domains"},
}

TIME_WINDOWS = {"any": None, "day": "day", "week": "week", "month": "month", "year": "year"}


def _clean_domains(items: Any) -> list[str]:
    out = []
    for raw in items or []:
        d = _host(str(raw).strip()) if "/" in str(raw) else str(raw).strip().lower().lstrip(".")
        d = d.removeprefix("www.")
        if d and re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", d) and d not in out:
            out.append(d)
    return out[:20]


_RECENT = re.compile(r"\b(latest|current|currently|newest|today|right now|this (?:week|month|year)|"
                     r"recent|recently|as of now|up[- ]to[- ]date)\b", re.I)


def wants_recent(question: str) -> bool:
    """The question asks for the current state of something."""
    return bool(_RECENT.search(question or ""))


def source_rules(profile: str = "web", include: Any = None, exclude: Any = None,
                 time_window: str = "any", news: bool = False, site_url: str = "",
                 question: str = "") -> dict[str, Any]:
    """The run's source rules as Tavily parameters, plus a human-readable summary.

    `recent` marks a question about the current state of something. It is not
    turned into a time filter — official pages often carry no publish date and a
    filter would hide them — but the agent is told to search for current pages
    and to say how old its sources are (an old page can quote "the latest
    release" accurately and still be out of date)."""
    p = SOURCE_PROFILES.get(profile) or SOURCE_PROFILES["web"]
    inc = _clean_domains(include) if profile == "custom" else list(p.get("include_domains", []))
    exc = _clean_domains(exclude) if profile == "custom" else list(p.get("exclude_domains", []))
    if site_url:
        host = _host(site_url).removeprefix("www.")
        if host:
            inc = [host]
    topic = "news" if (news or p.get("topic") == "news") else None
    tw = TIME_WINDOWS.get(time_window)
    if profile == "news" and not tw:
        tw = "week"
    parts = [p["title"] if not site_url else f"Only {inc[0] if inc else site_url}"]
    if inc and not site_url:
        parts.append("only " + ", ".join(inc[:6]) + ("…" if len(inc) > 6 else ""))
    if exc:
        parts.append("never " + ", ".join(exc[:5]) + ("…" if len(exc) > 5 else ""))
    if tw:
        parts.append(f"published in the last {tw}")
    if topic:
        parts.append("news sources")
    return {"profile": profile if p else "web", "include_domains": inc, "exclude_domains": exc,
            "time_range": tw, "topic": topic, "summary": " · ".join(parts),
            "recent": not site_url and wants_recent(question)}


def _host(url: str) -> str:
    try:
        return (urlparse(url if "://" in url else f"https://{url}").hostname or "").lower()
    except ValueError:
        return ""


def _on(host: str, domains: list[str]) -> bool:
    host = host.lower().removeprefix("www.")
    return any(host == d or host.endswith("." + d) for d in domains)


def apply_source_rules(tool: str, kwargs: dict[str, Any], rules: dict[str, Any]) -> tuple[list[str], str | None]:
    """Fill the run's source rules into a Tavily call; return (what was applied, why it's refused).

    tavily_search gets include/exclude domains, time range and topic filled in when
    the agent leaves them out. Any URL the call would read (extract, crawl, map)
    must respect the same domain rules.
    """
    applied: list[str] = []
    inc, exc = rules.get("include_domains") or [], rules.get("exclude_domains") or []
    if tool == "tavily_search":
        asked = _clean_domains(kwargs.get("include_domains"))
        if inc:
            outside = [d for d in asked if not _on(d, inc)]
            if outside:
                return applied, f"include_domains outside your source rules: {', '.join(outside)}"
            if not asked:
                kwargs["include_domains"] = list(inc)
                applied.append(f"limited to {len(inc)} domain(s)")
        if exc:
            merged = sorted(set(_clean_domains(kwargs.get("exclude_domains"))) | set(exc))
            if merged != _clean_domains(kwargs.get("exclude_domains")):
                kwargs["exclude_domains"] = merged
                applied.append(f"excluded {len(exc)} domain(s)")
        if rules.get("time_range") and not kwargs.get("time_range") and not kwargs.get("start_date"):
            kwargs["time_range"] = rules["time_range"]
            applied.append(f"last {rules['time_range']}")
        if rules.get("topic") and kwargs.get("topic") != rules["topic"]:
            kwargs["topic"] = rules["topic"]
            applied.append("news")
        return applied, None
    urls: list[str] = []
    if tool == "tavily_extract":
        urls = [str(u) for u in kwargs.get("urls") or []]
    elif tool in ("tavily_crawl", "tavily_map"):
        urls = [str(kwargs.get("url") or "")]
    for u in urls:
        h = _host(u)
        if inc and not _on(h, inc):
            return applied, f"{h or u} is outside your source rules (only {', '.join(inc[:5])})"
        if exc and _on(h, exc):
            return applied, f"{h} is on your blocked list"
    return applied, None


# ── Egress guard ──────────────────────────────────────────────────────────

_SECRET_PATTERNS = [
    ("API key", re.compile(r"\bsk-(?:ant-|proj-|live-)?[A-Za-z0-9_\-]{8,}")),
    ("Tavily key", re.compile(r"\btvly-[A-Za-z0-9_\-]{6,}")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{10,}|\bgithub_pat_[A-Za-z0-9_]{10,}")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("credential", re.compile(r"(?i)\b(?:api[_-]?key|token|secret|password)\s*[:=]\s*\S{8,}")),
    ("email address", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
]
_INTERNAL_PATTERNS = [
    ("internal host name", re.compile(r"(?i)\b[a-z0-9][\w\-.]*\.(?:internal|local|corp|lan|intranet)\b")),
    ("private IP address", re.compile(
        r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b|\b127\.0\.0\.1\b|\blocalhost\b")),
]


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, (list, tuple, set)):
        for v in value:
            yield from _strings(v)


def egress_violations(args: Any) -> list[str]:
    """Reasons an outbound call must not leave: secrets, personal emails, internal names."""
    extra = [t.strip().lower() for t in os.getenv("WR_INTERNAL_TERMS", "").split(",") if t.strip()]
    reasons: list[str] = []
    for text in _strings(args):
        for label, pattern in _SECRET_PATTERNS + _INTERNAL_PATTERNS:
            if pattern.search(text) and label not in reasons:
                reasons.append(label)
        low = text.lower()
        if any(t in low for t in extra) and "internal term" not in reasons:
            reasons.append("internal term")
    return reasons


# ── Evidence ──────────────────────────────────────────────────────────────
# Same check as Dependency Drift Watcher: a quote counts only if its words
# appear, in order, on a page this run actually read.

_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−﹣－"), "-")
_SPACES = dict.fromkeys(map(ord, "      　"), " ")


def _words(text: str) -> list[str]:
    plain = (text or "").translate(_DASHES).translate(_SPACES).lower()
    return re.findall(r"[a-z0-9]+(?:[.:-][a-z0-9]+)*", plain)


def quote_supported(quote: str, page_text: str, min_run: int = 6) -> bool:
    """The quote's words appear on the page in order (all of it, or a run of at
    least `min_run` words), and every number in it appears on the page too.
    A quote shortened with an ellipsis counts when every fragment of 3+ words
    appears on the page, in order."""
    if "…" in quote or "..." in quote:
        frags = [f for f in re.split(r"…|\.\.\.", quote) if len(_words(f)) >= 3]
        if not frags:
            return False
        hay, pos = " " + " ".join(_words(page_text)) + " ", 0
        for f in frags:
            idx = hay.find(" " + " ".join(_words(f)) + " ", pos)
            if idx < 0:
                return False
            pos = idx + 1
        return True
    q, page = _words(quote), _words(page_text)
    if not q or not page:
        return False
    hay = " " + " ".join(page) + " "
    for tok in q:
        if any(c.isdigit() for c in tok) and f" {tok} " not in hay:
            return False
    if len(q) <= min_run:
        return f" {' '.join(q)} " in hay
    return any(f" {' '.join(q[i:i + min_run])} " in hay for i in range(len(q) - min_run + 1))


def url_key(url: str) -> str:
    u = (url or "").split("#", 1)[0].rstrip("/").lower()
    return re.sub(r"^https?://(www\.)?", "", u)


def find_page(url: str, pages: dict[str, str]) -> str | None:
    """Text of a page this run read, matched loosely on URL (scheme, www, trailing slash)."""
    k = url_key(url)
    if not k:
        return None
    for u, text in pages.items():
        ku = url_key(u)
        if ku == k or ku.startswith(k) or k.startswith(ku):
            return text
    return None


def best_passage(claim: str, page_text: str, width: int = 320) -> str:
    """The sentence-ish window of a page that shares the most words with the claim."""
    words = set(w for w in _words(claim) if len(w) > 3)
    if not words or not page_text:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+|\n+", page_text)
    best, score = "", 0
    for s in sentences:
        sc = len(words & set(_words(s)))
        if sc > score and 20 <= len(s) <= 1200:
            best, score = s, sc
    return best[:width].strip() if score >= 2 else ""



def best_passages(claim: str, page_text: str, k: int = 2, width: int = 500) -> str:
    """The `k` sentences of a page that share the most words with the claim, in page
    order — a stronger quote when the agent's own quote was too general."""
    words = set(w for w in _words(claim) if len(w) > 3)
    if not words or not page_text:
        return ""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", page_text) if 20 <= len(s.strip()) <= 600]
    scored = sorted(((len(words & set(_words(s))), i) for i, s in enumerate(sentences)), reverse=True)
    top = sorted(i for sc, i in scored[:k] if sc >= 2)
    return " … ".join(sentences[i] for i in top)[:width]

_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def split_claims(answer: str) -> tuple[str, list[dict[str, str]], list[str]]:
    """(answer without the json block, claims, follow-up questions)."""
    matches = list(_JSON_BLOCK.finditer(answer or ""))
    if not matches:
        return (answer or "").strip(), [], []
    block = matches[-1]
    try:
        data = json.loads(block.group(1))
    except json.JSONDecodeError:
        return (answer or "").strip(), [], []
    claims = []
    for item in (data.get("claims") if isinstance(data, dict) else None) or []:
        if isinstance(item, dict) and item.get("claim"):
            claims.append({"claim": str(item["claim"])[:600], "quote": str(item.get("quote", ""))[:800],
                           "source_url": str(item.get("source_url", ""))[:500]})
    follow = [str(f)[:200] for f in (data.get("follow_ups") or [])][:4] if isinstance(data, dict) else []
    clean = (answer[:block.start()] + answer[block.end():]).strip()
    return clean, claims[:8], follow


def urls_in(text: Any, limit: int = 12) -> list[str]:
    out: list[str] = []
    for s in _strings(text):
        for u in _URL.findall(s):
            u = u.rstrip(".,;")
            if u not in out:
                out.append(u)
            if len(out) >= limit:
                return out
    return out
