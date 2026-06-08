"""
Find a Doctor — CUGA Demo App
=============================

Give a location and (optionally) a specialty or preference — "find a
cardiologist in Boston", "a really experienced pediatric dentist in Austin
who's good with kids" — and the agent assembles a ranked board of doctors:
where they are, their specialty, and a review-grounded summary of pros and
cons drawn from trusted review sites.

Same spirit as Ouroboros (geocode → discover → enrich → synthesize), but with
**inline @tool defs only** — no MCP servers. Live data comes from:
  - Nominatim (OpenStreetMap) for geocoding
  - Overpass (OpenStreetMap) for nearby doctors/clinics
  - DuckDuckGo HTML for review snippets from trusted health sites
All keyless, via direct httpx calls.

Run:
    python main.py
    python main.py --port 28825
    python main.py --provider anthropic

Then open: http://127.0.0.1:28825

Environment variables:
    LLM_PROVIDER          rits | anthropic | openai | watsonx | litellm | ollama
    LLM_MODEL             model name override
    AGENT_SETTING_CONFIG  path to CUGA settings TOML (defaulted in make_agent)
"""
from __future__ import annotations

import argparse
import html as _html
import json
import logging
import math
import os
import re
import sys
import urllib.parse
import uuid
from pathlib import Path

# ── Path bootstrap — must come before local imports ─────────────────────
_DIR       = Path(__file__).parent
_DEMOS_DIR = _DIR.parent
for _p in (str(_DIR), str(_DEMOS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

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


# ── Trusted review / directory sources ──────────────────────────────────
# Domains we treat as credible signal for a doctor's reputation. Used to tag
# search results so the agent leans on these for pros/cons.
_TRUSTED_DOMAINS = {
    "healthgrades.com", "vitals.com", "zocdoc.com", "webmd.com",
    "ratemds.com", "yelp.com", "sharecare.com", "wellness.com",
    "doximity.com", "castleconnolly.com", "ucomparehealthcare.com",
    "npino.com", "google.com", "realself.com", "opencare.com",
}

_OVERPASS_URL   = "https://overpass-api.de/api/interpreter"
_NOMINATIM_URL  = "https://nominatim.openstreetmap.org/search"
_DDG_HTML_URL   = "https://html.duckduckgo.com/html/"
_UA = "Mozilla/5.0 (cuga-apps find-a-doctor)"


# ── Per-thread session store ────────────────────────────────────────────
_sessions: dict[str, dict] = {}


def _get_session(thread_id: str) -> dict:
    if thread_id not in _sessions:
        _sessions[thread_id] = {
            "location":    "",
            "specialty":   "",
            "preferences": [],     # e.g. ["experienced", "good with kids"]
            "geo":         None,   # {lat, lon, display_name}
            "doctors":     [],     # ranked cards
        }
    return _sessions[thread_id]


def _append_unique(lst: list[str], value: str) -> None:
    if value and value.lower() not in [v.lower() for v in lst]:
        lst.append(value)


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(a)), 2)


def _domain_of(url: str) -> str:
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:  # noqa: BLE001
        return ""


# ── Tools ────────────────────────────────────────────────────────────────
def _make_tools():
    import httpx
    from langchain_core.tools import tool

    @tool
    def set_search(thread_id: str, location: str = "", specialty: str = "",
                   preferences: str = "") -> str:
        """Record what the user is looking for this session. Call this whenever
        they mention a location, a specialty, or a preference.

        Args:
            thread_id:   The current session/thread ID (always pass through).
            location:    City / area, e.g. "Boston, MA" or "Pleasantville NY".
            specialty:   Medical specialty, e.g. "cardiologist", "pediatric
                         dentist", "dermatologist". Empty leaves it unchanged.
            preferences: Free-text preference(s) like "very experienced",
                         "good with kids", "accepts new patients". Comma-separated.
        """
        session = _get_session(thread_id)
        if location.strip():
            session["location"] = location.strip()
            session["geo"] = None  # invalidate cached geocode
        if specialty.strip():
            session["specialty"] = specialty.strip().lower()
        if preferences.strip():
            for p in preferences.split(","):
                _append_unique(session["preferences"], p.strip())
        return json.dumps({"ok": True, "data": {
            "location":    session["location"],
            "specialty":   session["specialty"] or "any",
            "preferences": session["preferences"],
        }})

    @tool
    def geocode_location(thread_id: str, location: str = "") -> str:
        """Resolve a location string to lat/lon + a canonical display name via
        OpenStreetMap Nominatim. Call this before find_doctors.

        Args:
            thread_id: The current session/thread ID.
            location:  Place to geocode; empty uses the session location.
        """
        session = _get_session(thread_id)
        place = (location or session["location"]).strip()
        if not place:
            return json.dumps({"ok": False, "code": "bad_input",
                               "error": "no location given"})
        try:
            with httpx.Client(timeout=20, headers={"User-Agent": _UA}) as client:
                resp = client.get(_NOMINATIM_URL, params={
                    "q": place, "format": "json", "limit": 1})
            resp.raise_for_status()
            hits = resp.json()
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"ok": False, "code": "network_error", "error": str(exc)})
        if not hits:
            return json.dumps({"ok": False, "code": "not_found",
                               "error": f"could not geocode '{place}'"})
        h = hits[0]
        geo = {"lat": float(h["lat"]), "lon": float(h["lon"]),
               "display_name": h.get("display_name", place)}
        session["geo"] = geo
        if not session["location"]:
            session["location"] = place
        return json.dumps({"ok": True, "data": geo})

    @tool
    def find_doctors(thread_id: str, specialty: str = "", radius_km: float = 8.0,
                     limit: int = 20) -> str:
        """Find doctors/clinics near the session's geocoded location using
        OpenStreetMap (Overpass). Returns structured listings with address,
        phone, and website where tagged. Call geocode_location first.

        Note: OSM coverage of individual practitioners is uneven (sparser in
        the US). Treat results as a starting set and supplement with
        web_search("best <specialty> in <location>") to discover named doctors.

        Args:
            thread_id: The current session/thread ID.
            specialty: Filter hint (e.g. "cardiology"); empty uses the session
                       specialty. Matched loosely against name + speciality tags.
            radius_km: Search radius in km (default 8).
            limit:     Max listings to return (default 20).
        """
        session = _get_session(thread_id)
        geo = session.get("geo")
        if not geo:
            return json.dumps({"ok": False, "code": "no_geo",
                               "error": "call geocode_location first"})
        specialty = (specialty or session["specialty"] or "").strip().lower()
        radius_m = int(max(0.5, min(float(radius_km or 8), 50)) * 1000)
        lat, lon = geo["lat"], geo["lon"]
        query = f"""
[out:json][timeout:25];
(
  node["amenity"="doctors"](around:{radius_m},{lat},{lon});
  way["amenity"="doctors"](around:{radius_m},{lat},{lon});
  node["healthcare"="doctor"](around:{radius_m},{lat},{lon});
  way["healthcare"="doctor"](around:{radius_m},{lat},{lon});
  node["healthcare"="clinic"](around:{radius_m},{lat},{lon});
  way["healthcare"="clinic"](around:{radius_m},{lat},{lon});
);
out center {limit * 3};
"""
        try:
            with httpx.Client(timeout=40, headers={"User-Agent": _UA}) as client:
                resp = client.post(_OVERPASS_URL, data={"data": query})
            resp.raise_for_status()
            elements = resp.json().get("elements", [])
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"ok": False, "code": "network_error", "error": str(exc)})

        results = []
        for el in elements:
            tags = el.get("tags", {})
            name = tags.get("name")
            if not name:
                continue
            spec = (tags.get("healthcare:speciality")
                    or tags.get("speciality") or tags.get("healthcare:speciality:en") or "")
            spec = spec.replace(";", ", ")
            if specialty:
                hay = f"{name} {spec}".lower()
                terms = [t for t in re.split(r"\W+", specialty) if len(t) > 3]
                if terms and not any(t in hay for t in terms):
                    continue
            elat = el.get("lat") or (el.get("center") or {}).get("lat")
            elon = el.get("lon") or (el.get("center") or {}).get("lon")
            dist = _haversine_km(lat, lon, elat, elon) if elat and elon else None
            addr_parts = [tags.get("addr:housenumber"), tags.get("addr:street"),
                          tags.get("addr:city"), tags.get("addr:postcode")]
            address = " ".join(p for p in addr_parts if p)
            results.append({
                "name":      name,
                "specialty": spec,
                "address":   address,
                "phone":     tags.get("phone") or tags.get("contact:phone") or "",
                "website":   tags.get("website") or tags.get("contact:website") or "",
                "distance_km": dist,
            })

        results.sort(key=lambda d: (d["distance_km"] is None, d["distance_km"] or 0))
        results = results[:limit]
        log.info("[%s] OSM doctors near %s: %d (specialty=%s)",
                 thread_id[:8], session["location"], len(results), specialty or "any")
        return json.dumps({"ok": True, "data": {
            "location":  geo["display_name"],
            "specialty": specialty or "any",
            "count":     len(results),
            "doctors":   results,
        }})

    @tool
    def web_search(query: str, max_results: int = 8) -> str:
        """Keyless web search via DuckDuckGo HTML. Returns titles, URLs, and
        snippets, each tagged with its domain and whether that domain is a
        trusted health-review source. Use to discover named doctors
        ("best cardiologist in <city>") and to gather review snippets.

        Args:
            query:       The search query.
            max_results: Max results to return (1–15, default 8).
        """
        query = (query or "").strip()
        if not query:
            return json.dumps({"ok": False, "code": "bad_input", "error": "empty query"})
        max_results = max(1, min(int(max_results or 8), 15))
        try:
            with httpx.Client(timeout=25, headers={"User-Agent": _UA},
                              follow_redirects=True) as client:
                resp = client.post(_DDG_HTML_URL, data={"q": query})
            resp.raise_for_status()
            html_text = resp.text
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"ok": False, "code": "network_error", "error": str(exc)})

        results = _parse_ddg(html_text, max_results)
        if not results:
            return json.dumps({"ok": True, "data": {"query": query, "count": 0,
                                                    "results": [],
                                                    "note": "no results parsed (DDG may be "
                                                            "rate-limiting); try rephrasing"}})
        return json.dumps({"ok": True, "data": {"query": query,
                                                "count": len(results),
                                                "results": results}})

    @tool
    def fetch_reviews(doctor_name: str, location: str = "", max_results: int = 8) -> str:
        """Convenience wrapper: search for reviews of a specific doctor and
        return only snippets from trusted health-review sites (Healthgrades,
        Vitals, Zocdoc, WebMD, RateMDs, Yelp, etc.).

        Args:
            doctor_name: The doctor's name (and optionally clinic).
            location:    City/area to disambiguate (optional but recommended).
            max_results: Max snippets to return (default 8).
        """
        doctor_name = (doctor_name or "").strip()
        if not doctor_name:
            return json.dumps({"ok": False, "code": "bad_input",
                               "error": "doctor_name is empty"})
        q = f"{doctor_name} {location} reviews".strip()
        max_results = max(1, min(int(max_results or 8), 15))
        try:
            with httpx.Client(timeout=25, headers={"User-Agent": _UA},
                              follow_redirects=True) as client:
                resp = client.post(_DDG_HTML_URL, data={"q": q})
            resp.raise_for_status()
            html_text = resp.text
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"ok": False, "code": "network_error", "error": str(exc)})

        parsed = _parse_ddg(html_text, 15)
        trusted = [r for r in parsed if r["trusted"]][:max_results]
        return json.dumps({"ok": True, "data": {
            "doctor": doctor_name,
            "query":  q,
            "trusted_count": len(trusted),
            "reviews": trusted or parsed[:max_results],
            "note": "" if trusted else "no trusted-source hits; returning general results",
        }})

    @tool
    def save_doctors(thread_id: str, doctors_json: str) -> str:
        """Persist the ranked doctor board so the right-panel UI can render it.
        Call this at the END of every search, after gathering reviews.

        Args:
            thread_id:    The current session/thread ID.
            doctors_json: A JSON array. Each element should include:
                            name            (str)
                            specialty       (str)
                            address         (str, optional)
                            phone           (str, optional)
                            website         (str, optional)
                            distance_km     (number, optional)
                            rating_summary  (str, one line on overall reputation)
                            experience_note (str, on seniority/experience if known)
                            pros            (list[str], 2–4 grounded in reviews)
                            cons            (list[str], 0–3 grounded in reviews)
                            sources         (list[{title, url, domain}])
        """
        session = _get_session(thread_id)
        try:
            doctors = json.loads(doctors_json)
            if not isinstance(doctors, list):
                return json.dumps({"ok": False, "code": "bad_input",
                                   "error": "doctors_json must be a JSON array"})
            session["doctors"] = doctors
            log.info("[%s] saved %d doctor cards", thread_id[:8], len(doctors))
            return json.dumps({"ok": True, "data": {"saved": len(doctors)}})
        except json.JSONDecodeError as exc:
            return json.dumps({"ok": False, "code": "bad_input",
                               "error": f"invalid JSON: {exc}"})

    return [set_search, geocode_location, find_doctors, web_search,
            fetch_reviews, save_doctors]


# ── DuckDuckGo HTML parsing (regex; no bs4 dependency) ───────────────────
_RESULT_A_RE = re.compile(
    r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
    re.DOTALL | re.IGNORECASE)
_SNIPPET_RE = re.compile(
    r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
    re.DOTALL | re.IGNORECASE)


def _strip_tags(s: str, limit: int = 300) -> str:
    s = re.sub(r"<[^>]+>", "", s or "")
    s = _html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]


def _unwrap_ddg(href: str) -> str:
    """DDG wraps result links as //duckduckgo.com/l/?uddg=<encoded>. Unwrap."""
    if "uddg=" in href:
        try:
            qs = urllib.parse.urlparse(href if href.startswith("http") else "https:" + href).query
            uddg = urllib.parse.parse_qs(qs).get("uddg", [])
            if uddg:
                return urllib.parse.unquote(uddg[0])
        except Exception:  # noqa: BLE001
            pass
    if href.startswith("//"):
        return "https:" + href
    return href


def _parse_ddg(html_text: str, max_results: int) -> list[dict]:
    links = _RESULT_A_RE.findall(html_text)
    snippets = _SNIPPET_RE.findall(html_text)
    out = []
    for i, (href, title) in enumerate(links[:max_results]):
        url = _unwrap_ddg(href)
        domain = _domain_of(url)
        out.append({
            "title":   _strip_tags(title, 160),
            "url":     url,
            "domain":  domain,
            "snippet": _strip_tags(snippets[i], 300) if i < len(snippets) else "",
            "trusted": any(domain == d or domain.endswith("." + d) for d in _TRUSTED_DOMAINS),
        })
    return out


# ── System prompt ────────────────────────────────────────────────────────
_SYSTEM = """\
# Find a Doctor

You help the user find a good doctor in a location, grounded in real listings
and review snippets from trusted sites. Queries range from simple ("a
dentist in Austin") to nuanced ("a really experienced pediatric cardiologist
in Boston who's good with anxious kids").

## Sequence for every search

1. Call `set_search` to record the location, specialty, and any preferences
   (experience, bedside manner, accepts new patients, etc.).
2. Call `geocode_location(thread_id=...)`. If it fails, ask the user to
   clarify the location and stop.
3. Discover candidates from TWO sources and merge them:
     a. `find_doctors(thread_id=..., specialty=...)` — structured OSM listings
        (address/phone/website). Coverage is uneven, so also:
     b. `web_search("best <specialty> in <location>")` and similar queries to
        surface named, well-regarded doctors. If the user asked for
        "experienced" or a sub-specialty, bias queries accordingly
        (e.g. "top-rated", "most experienced", "<sub-specialty>").
4. For the most promising 3–6 candidates, call
   `fetch_reviews(doctor_name=..., location=...)` to pull review snippets from
   trusted sites. Read the snippets for recurring praise and complaints.
5. For each doctor synthesize:
     - `rating_summary`: one line on overall reputation (cite the kind of
       sources, e.g. "well-reviewed on Healthgrades & Zocdoc").
     - `experience_note`: seniority/years/sub-specialty IF supported by a source.
     - `pros` / `cons`: short bullets, each grounded in what reviews actually say.
     - `sources`: the trusted links you used ({title, url, domain}).
6. Rank by how well they match the user's request (specialty fit, experience,
   review sentiment, proximity), then call
   `save_doctors(thread_id=..., doctors_json=...)`. This step is REQUIRED and is
   the PRIMARY output — the ranked panel on the right is what the user reads. You
   MUST call save_doctors before you reply, even if you only found one or two
   matches.
7. Reply with a SHORT framing ONLY — 1–2 sentences, e.g. "Found 4 well-reviewed
   cardiologists in Boston — the ranked list with pros & cons is on the right."
   Do NOT repeat the per-doctor detail in prose; the panel already shows it.

## Rules — important
- This is informational help, NOT medical advice or a referral. If reviews are
  thin or conflicting, say so plainly; don't manufacture pros/cons.
- Never invent ratings, credentials, addresses, or quotes. Every pro/con must
  trace to a real snippet you retrieved. If you couldn't verify experience,
  leave `experience_note` empty rather than guessing.
- Prefer trusted-source snippets (Healthgrades, Vitals, Zocdoc, WebMD,
  RateMDs, Yelp) over random blogs.
- If searches are rate-limited or empty, tell the user and return whatever
  structured listings you did find.

## Thread ID
You will receive the thread_id in every user message (format:
"[thread:<UUID>]"). Always extract it and pass it unchanged to every tool
call that requires thread_id.
"""


# ── CUGA policies ─────────────────────────────────────────────────────────
# This app benefits most from CUGA's policy system:
#   • intent_guard    — a hard safety boundary: this is a doctor *finder*, not
#                       a source of medical advice/diagnosis. The guard fires
#                       before the planner runs, so it can't be prompt-talked
#                       around.
#   • tool_guide      — grounds every pro/con in real review snippets.
#   • output_formatter — locks the ranked-board save + disclaimer contract.
# Attached once, lazily, and defensively (sqlite-vec optional).
async def _attach_policies(agent) -> None:
    try:
        await agent.policies.add_intent_guard(
            name="medical_advice_guard",
            keywords=[
                "diagnose", "diagnosis", "should i take", "is it safe to take",
                "what medication", "what dosage", "prescribe", "treat my",
                "what do my symptoms mean", "is this normal", "home remedy",
                "do i have", "am i having",
            ],
            response=(
                "I can help you find and compare doctors — but I can't give "
                "medical advice, diagnoses, or medication/treatment guidance. "
                "For any health concern please consult a licensed clinician (or "
                "call emergency services if it's urgent). Tell me a location and "
                "the kind of doctor you're looking for and I'll pull options."
            ),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("intent_guard skipped: %s", exc)
    try:
        await agent.policies.add_tool_guide(
            name="review_grounding_guide",
            content=(
                "Prefer snippets from trusted review domains (Healthgrades, "
                "Vitals, Zocdoc, WebMD, RateMDs, Yelp). Ground every pro and con "
                "in a real retrieved snippet — never invent ratings, credentials, "
                "years of experience, or quotes. If reviews are thin or "
                "conflicting, say so plainly instead of manufacturing a verdict."
            ),
            target_tools=["fetch_reviews", "web_search"],
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("tool_guide skipped: %s", exc)
    try:
        await agent.policies.add_output_formatter(
            name="doctor_board_formatter",
            format_config=(
                "Before replying, ALWAYS call save_doctors with the ranked "
                "board — each doctor needs rating_summary, pros, cons (grounded "
                "in reviews), and sources. In prose give a short ranked rundown "
                "with each doctor's standout pro and any caveat, citing sources "
                "as markdown links, and END with a one-line reminder that this "
                "is informational only — not medical advice or a referral."
            ),
            format_type="markdown",
            keywords=["doctor", "physician", "specialist", "cardiologist",
                       "dentist", "find a", "best", "near"],
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
    )


# ── Request models ──────────────────────────────────────────────────────
class AskReq(BaseModel):
    question: str
    thread_id: str = ""


# ── HTTP server ──────────────────────────────────────────────────────────
def _web(port: int) -> None:
    import uvicorn

    app = FastAPI(title="Find a Doctor", docs_url=None, redoc_url=None)
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
        # Stateless: the panel id keys the per-turn data the UI polls, but we
        # reset it each turn and run the agent on a fresh memory thread, so
        # nothing carries over from the previous question.
        thread_id = req.thread_id or uuid.uuid4().hex
        _sessions.pop(thread_id, None)
        augmented = f"[thread:{thread_id}] {req.question}"
        try:
            agent = await _get_agent()
            result = await agent.invoke(augmented, thread_id=uuid.uuid4().hex)
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

    print(f"\n  Find a Doctor  →  http://127.0.0.1:{port}\n")
    # Public deployment: layered, in-memory rate limiting on POST.
    from _ratelimit import install_rate_limit
    install_rate_limit(app)
    from _usage import install_usage
    install_usage(app)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ── CLI entry point ──────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Find a Doctor — CUGA demo app")
    parser.add_argument("--port", type=int, default=28825)
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
