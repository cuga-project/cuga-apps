"""Tools for the revenue_estimator skill."""
from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, Optional

_WEB_SEARCH: Optional[Callable[..., Awaitable[Any]]] = None


def bind_web_search(fn: Callable[..., Awaitable[Any]]) -> None:
    global _WEB_SEARCH
    _WEB_SEARCH = fn


def _envelope_ok(data) -> str:
    return json.dumps({"ok": True, "data": data})


def _envelope_err(msg: str, code: str = "upstream") -> str:
    return json.dumps({"ok": False, "error": msg, "code": code})


# Coarse per-vertical heuristics. These are deliberately conservative and
# should not be reported as anything other than a *ranking aid*. Numbers
# come from public ARR-per-employee benchmarks for small US businesses.
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
    (200_000,    "< $200k",     0,        199_999),
    (1_000_000,  "$200k–$1M",   200_000,  999_999),
    (5_000_000,  "$1M–$5M",     1_000_000, 4_999_999),
    (float("inf"), "> $5M",     5_000_000, 999_999_999),
]


def _band_for(arr: int) -> tuple[str, int, int]:
    for limit, label, lo, hi in _BAND_THRESHOLDS:
        if arr < limit:
            return label, lo, hi
    return ">$5M", 5_000_000, 999_999_999


def _estimate_arr_band(business_type: str, signals: dict) -> dict:
    btype = (business_type or "").lower().strip().rstrip("s")  # "restaurants" → "restaurant"
    per_emp = _VERTICAL_BASELINE_PER_EMPLOYEE.get(btype, 100_000)

    employees   = signals.get("employee_count")
    reviews     = signals.get("review_count")
    locations   = signals.get("locations_count") or 1
    years       = signals.get("years_in_business")

    rules: list[str] = []
    arr: Optional[int] = None

    # Rule 1: explicit employee count is the strongest signal.
    if isinstance(employees, (int, float)) and employees > 0:
        arr = int(employees * per_emp * locations)
        rules.append(f"{int(employees)} employees × ${per_emp:,}/emp × {locations} loc")
    # Rule 2: review count as a proxy for footfall — a salon with 200+ Yelp
    # reviews is bigger than one with 12.
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
        arr = per_emp * 5 * locations  # assume ~5 emp per loc baseline
        rules.append(f"{locations} locations × ~5 emp baseline")
    else:
        return {
            "band":          "unknown",
            "band_low_usd":  None,
            "band_high_usd": None,
            "rationale":     "No public size signals found.",
            "rules_fired":   [],
            "confidence":    "low",
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
    }


async def _search_size_signals(business_name: str, city: str) -> dict:
    if _WEB_SEARCH is None:
        raise RuntimeError("web_search not bound")
    query = (
        f'"{business_name}" {city} '
        f'(reviews OR employees OR "team of" OR locations OR "since")'
    )
    raw = await _WEB_SEARCH(query=query, max_results=5)
    if isinstance(raw, dict) and "results" in raw:
        items = raw["results"]
    elif isinstance(raw, list):
        items = raw
    elif isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            items = parsed.get("results", []) if isinstance(parsed, dict) else (
                parsed if isinstance(parsed, list) else []
            )
        except json.JSONDecodeError:
            items = []
    else:
        items = []
    hits = []
    for it in items[:5]:
        if not isinstance(it, dict):
            continue
        hits.append({
            "title":   (it.get("title") or "").strip()[:200],
            "url":     it.get("url") or "",
            "snippet": (it.get("content") or it.get("snippet") or "").strip()[:600],
        })
    return {"query": query, "hits": hits}


try:
    from langchain_core.tools import tool

    @tool
    async def search_size_signals(business_name: str, city: str) -> str:
        """Search for size signals: review counts, employees, locations, years.

        Args:
            business_name: Exact business name.
            city:          City to disambiguate.
        """
        try:
            return _envelope_ok(await _search_size_signals(business_name, city))
        except Exception as e:
            return _envelope_err(f"search_size_signals failed: {e}")

    @tool
    def estimate_arr_band(business_type: str, signals: dict) -> str:
        """Map collected size signals to an annual-revenue band.

        Args:
            business_type: "restaurant", "salon", "clinic", etc.
            signals:       dict possibly containing review_count,
                           employee_count, locations_count, years_in_business.
        """
        return _envelope_ok(_estimate_arr_band(business_type, signals or {}))

    TOOLS = [search_size_signals, estimate_arr_band]
except ImportError:
    TOOLS = []
