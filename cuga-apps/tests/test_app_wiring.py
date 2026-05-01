"""
App-wiring tests: hit non-LLM REST endpoints on every app to verify the
FastAPI shell, the SQLite/in-memory state layer, and any volume mounts work.

These do NOT call the agent — no LLM is invoked, no tokens spent. If you
break a route, mistype a path, or wire a SQLite table wrong, these catch it.
"""
from __future__ import annotations

import pytest

from .conftest import app_url


pytestmark = pytest.mark.wiring


# (app_id, endpoint, expected_kind)
# expected_kind is one of:
#   "json_list" — body is a JSON array
#   "json_obj"  — body is a JSON object
#   "any_2xx"   — any 2xx (we don't care about body shape)
#   "any_2xx_or_redirect" — 2xx or 3xx
ENDPOINTS = [
    # web_researcher — research log + scheduled topics + settings
    ("web_researcher", "/reports",  "json_list"),
    ("web_researcher", "/topics",   "json_list"),
    ("web_researcher", "/settings", "json_obj"),

    # code_reviewer — reviewed-snippet history
    ("code_reviewer", "/history", "json_list"),

    # travel_planner — health + config readouts
    ("travel_planner", "/health",         "json_obj"),
    ("travel_planner", "/config/status",  "json_obj"),
    ("travel_planner", "/config/prefill", "json_obj"),

    # stock_alert — watcher and email status
    ("stock_alert", "/watch/status", "json_list"),  # list of active watches
    ("stock_alert", "/api/status",   "json_obj"),
    ("stock_alert", "/email/status", "json_obj"),

    # server_monitor — live metrics + alert log + thresholds
    ("server_monitor", "/metrics",       "json_obj"),
    ("server_monitor", "/alerts/log",    "json_list"),
    ("server_monitor", "/alerts/config", "json_obj"),

    # smart_todo — todo lists + reminder log + settings
    ("smart_todo", "/todos",            "json_list"),
    ("smart_todo", "/todos/done",       "json_list"),
    ("smart_todo", "/reminders/fired",  "json_list"),
    ("smart_todo", "/settings",         "json_obj"),

    # voice_journal — entries + search + watcher
    ("voice_journal", "/entries",         "json_list"),
    ("voice_journal", "/watcher/status",  "json_obj"),

    # newsletter — feeds + alerts + email (return wrapped objects)
    ("newsletter", "/feeds/list",     "json_obj"),
    ("newsletter", "/alerts/list",    "json_obj"),
    ("newsletter", "/alerts/recent",  "json_obj"),
    ("newsletter", "/email/status",   "json_obj"),

    # arch_diagram — saved diagrams + settings
    ("arch_diagram", "/diagrams", "json_list"),
    ("arch_diagram", "/settings", "json_obj"),

    # movie_recommender — health
    ("movie_recommender", "/health", "json_obj"),

    # ibm_whats_new — service list + digest + email (services + log are wrapped)
    ("ibm_whats_new", "/services",      "json_obj"),
    ("ibm_whats_new", "/digest/recent", "json_obj"),
    ("ibm_whats_new", "/email/status",  "json_obj"),

    # box_qa — settings (no Box auth required for the GET)
    ("box_qa", "/settings", "json_obj"),

    # drop_summarizer — file watcher state (files/pending wraps the list)
    ("drop_summarizer", "/files/pending",   "json_obj"),
    ("drop_summarizer", "/summaries",       "json_list"),
    ("drop_summarizer", "/watcher/status",  "json_obj"),
    ("drop_summarizer", "/settings",        "json_obj"),

    # api_doc_gen — spec metadata
    ("api_doc_gen", "/spec-info", "json_obj"),

    # webpage_summarizer — health
    ("webpage_summarizer", "/health", "json_obj"),

    # youtube_research — research log + settings
    ("youtube_research", "/reports",  "json_list"),
    ("youtube_research", "/settings", "json_obj"),

    # code_engine_deployer is local-only (needs host docker + ibmcloud + user's IBM auth)
    # — not started by docker compose, so no in-container wiring test.
]


@pytest.mark.parametrize("app,endpoint,kind", ENDPOINTS, ids=[
    f"{a}{e}" for a, e, _ in ENDPOINTS
])
def test_app_endpoint(http, app, endpoint, kind):
    r = http.get(app_url(app) + endpoint, timeout=20)
    assert 200 <= r.status_code < 300, (
        f"{app}{endpoint} → {r.status_code}: {r.text[:200]}"
    )
    if kind in ("json_list", "json_obj"):
        try:
            body = r.json()
        except Exception as exc:
            pytest.fail(f"{app}{endpoint} returned non-JSON: {exc}; body[:200]={r.text[:200]}")
        if kind == "json_list":
            assert isinstance(body, list), (
                f"{app}{endpoint}: expected JSON list, got {type(body).__name__}"
            )
        elif kind == "json_obj":
            assert isinstance(body, dict), (
                f"{app}{endpoint}: expected JSON object, got {type(body).__name__}"
            )


# ── Stateful round-trip without LLM ─────────────────────────────────────
# web_researcher exposes /topics/add and /topics/delete as non-LLM endpoints
# that mutate per-app state (a JSON store). This test catches breakage in
# the FastAPI route + persistence layer without spending tokens.

class TestWebResearcherTopicsRoundtrip:

    SENTINEL = "integration-test-sentinel-topic"

    def test_add_list_delete(self, http):
        base = app_url("web_researcher")

        # 1. snapshot
        before = http.get(base + "/topics", timeout=10).json()
        assert isinstance(before, list)

        # 2. add a sentinel topic (disabled so the scheduler never runs it)
        add = http.post(base + "/topics/add", json={
            "query":         self.SENTINEL,
            "schedule":      "weekly",
            "email_results": False,
        }, timeout=15)
        assert add.status_code == 200, f"/topics/add → {add.status_code}: {add.text}"

        topic_id = None
        try:
            # 3. list — sentinel must be present and have an id
            mid = http.get(base + "/topics", timeout=10).json()
            sentinels = [t for t in mid if t.get("query") == self.SENTINEL]
            assert sentinels, f"sentinel not in {[t.get('query') for t in mid]}"
            topic_id = sentinels[0]["id"]
            assert topic_id

            # 4. toggle to verify the toggle endpoint works (non-LLM)
            tog = http.post(base + "/topics/toggle", json={"id": topic_id, "enabled": False}, timeout=10)
            assert tog.status_code == 200
        finally:
            # 5. cleanup
            if topic_id:
                http.post(base + "/topics/delete", json={"id": topic_id}, timeout=10)

        # 6. final list — sentinel gone
        after = http.get(base + "/topics", timeout=10).json()
        assert not [t for t in after if t.get("query") == self.SENTINEL]
