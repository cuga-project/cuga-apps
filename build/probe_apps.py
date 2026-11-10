#!/usr/bin/env python3
"""
probe_apps.py — ask every cuga-app one real question and report PASS/FAIL.

This is the end-to-end check used for the cuga 0.4.5 upgrade (2026-11-09/10):
the smoke test (build/smoke.sh) proves routing; this proves each agent actually
answers, with its tools, on a given deployment.

Usage:
    python build/probe_apps.py host                       # local launch.py stack (apps on their own ports)
    python build/probe_apps.py https://<all-in-one-host>   # a deployed all-in-one (routes /a/<app>/)
    python build/probe_apps.py host --set additional       # the non-showcase apps (local only)
    python build/probe_apps.py <base> wiki_dive web_researcher   # just these

A FAIL prints the HTTP error or the start of the bad answer. "PASS" also catches
answers that are code or a raw error (see BAD) — read the answer heads anyway.
Needs: httpx. Runs 6 apps at a time; LLM apps take 10 s – 5 min each.
"""
import argparse, sys, time, json, concurrent.futures as cf
from pathlib import Path
import httpx

F = False
PROBES = [
 {"app": "stock_alert", "port": 28801, "steps": [{"method": "POST", "path": "/ask", "json": {"symbol": "BTC", "question": "What is the current price of BTC in USD?", "is_stock": F}}], "poll": None, "answer_field": "answer"},
 {"app": "server_monitor", "port": 28767, "steps": [{"method": "POST", "path": "/ask", "json": {"question": "What is the current CPU and memory usage on this server?"}}], "poll": None, "answer_field": "answer"},
 {"app": "newsletter", "port": 28793, "steps": [{"method": "POST", "path": "/ask", "json": {"question": "Give me the single most recent headline from https://hnrss.org/frontpage in one sentence."}}], "poll": None, "answer_field": "answer"},
 {"app": "web_researcher", "port": 28798, "steps": [{"method": "POST", "path": "/research", "json": {"question": "Who is the current CEO of IBM?", "mode": "quick"}, "extract": "id"}], "poll": {"path": "/jobs/{job_id}", "done_field": "status", "done_values": ["done", "error"]}, "answer_field": "result.answer"},
 {"app": "travel_planner", "port": 28090, "steps": [{"method": "POST", "path": "/plan", "json": {"destination": "Lisbon", "days": 1, "interests": ["food"], "travel_style": "budget", "travel_month": "June", "agent_type": "cuga"}}], "poll": None, "answer_field": "itinerary"},
 {"app": "youtube_research", "port": 28803, "steps": [{"method": "POST", "path": "/ask", "json": {"question": "Find one popular YouTube video explaining what MCP (Model Context Protocol) is, with title and channel."}}], "poll": None, "answer_field": "answer"},
 {"app": "arch_diagram", "port": 28804, "steps": [{"method": "POST", "path": "/ask", "json": {"question": "Draw a simple mermaid diagram of a web app with a load balancer, two API servers and a Postgres database."}}], "poll": None, "answer_field": "answer"},
 {"app": "hiking_research", "port": 28805, "steps": [{"method": "POST", "path": "/ask", "json": {"question": "Suggest one easy hiking trail near Boulder, Colorado and the weather there today."}}], "poll": None, "answer_field": "answer"},
 {"app": "movie_recommender", "port": 28806, "steps": [{"method": "POST", "path": "/ask", "json": {"question": "Recommend one sci-fi movie similar to Interstellar.", "thread_id": ""}}], "poll": None, "answer_field": "answer"},
 {"app": "webpage_summarizer", "port": 28071, "steps": [{"method": "POST", "path": "/ask", "json": {"question": "Summarize https://example.com in one sentence."}}], "poll": None, "answer_field": "answer"},
 {"app": "paper_scout", "port": 28808, "steps": [{"method": "POST", "path": "/ask", "json": {"question": "Find one recent arXiv paper on retrieval-augmented generation and give its title.", "thread_id": "default"}}], "poll": None, "answer_field": "answer"},
 {"app": "wiki_dive", "port": 28809, "steps": [{"method": "POST", "path": "/ask", "json": {"question": "According to Wikipedia, in what year was the Eiffel Tower completed?", "thread_id": "default"}}], "poll": None, "answer_field": "answer"},
 {"app": "ibm_cloud_advisor", "port": 28812, "steps": [{"method": "POST", "path": "/ask", "json": {"question": "Which IBM Cloud service should I use to run a containerized web app without managing servers?"}}], "poll": None, "answer_field": "answer"},
 {"app": "ibm_docs_qa", "port": 28813, "steps": [{"method": "POST", "path": "/ask", "json": {"question": "How do I create an API key in IBM Cloud?"}}], "poll": None, "answer_field": "answer"},
 {"app": "recipe_composer", "port": 28820, "steps": [{"method": "POST", "path": "/ask", "json": {"question": "I have eggs, spinach and feta. Suggest one quick recipe.", "thread_id": ""}}], "poll": None, "answer_field": "answer"},
 {"app": "city_beat", "port": 28821, "steps": [{"method": "POST", "path": "/ask", "json": {"question": "What's the weather and one notable thing happening in Austin, Texas today?", "thread_id": ""}}], "poll": None, "answer_field": "answer"},
 {"app": "ouroboros", "port": 28822, "steps": [{"method": "POST", "path": "/ask", "json": {"question": "Find one startup working on AI agents for customer support and name it.", "thread_id": ""}}], "poll": None, "answer_field": "answer"},
 {"app": "github_trending", "port": 28823, "steps": [{"method": "POST", "path": "/ask", "json": {"question": "What is the top trending Python repository on GitHub this week?", "thread_id": ""}}], "poll": None, "answer_field": "answer"},
 {"app": "ai_labs_news", "port": 28824, "steps": [{"method": "POST", "path": "/ask", "json": {"question": "What is the latest announcement from Anthropic? One sentence.", "thread_id": ""}}], "poll": None, "answer_field": "answer"},
 {"app": "find_a_doctor", "port": 28825, "steps": [{"method": "POST", "path": "/ask", "json": {"question": "Find one dermatologist in San Jose, CA.", "thread_id": ""}}], "poll": None, "answer_field": "answer"},
 {"app": "meetup_finder", "port": 28826, "steps": [{"method": "POST", "path": "/ask", "json": {"question": "Find one AI or Python meetup in San Francisco this month.", "thread_id": ""}}], "poll": None, "answer_field": "answer"},
 {"app": "dependency_drift_watcher", "port": 28843, "steps": [{"method": "POST", "path": "/ask", "json": {"question": "Are any LLM model IDs used in this repo deprecated?", "pack": "models", "repo": ""}, "extract": "id"}], "poll": {"path": "/jobs/{job_id}", "done_field": "status", "done_values": ["done", "error"]}, "answer_field": "result.answer"},
]
BAD = ("Error:", "Traceback", "object has no attribute", "I cannot", "unable to access", "ERROR:")

def get(d, dotted):
    for k in dotted.split("."):
        d = d.get(k) if isinstance(d, dict) else None
    return d

def run(p, mode):
    base = f"http://localhost:{p['port']}" if mode == "host" else f"{mode.rstrip('/')}/a/{p['app'].replace('_','-')}"
    t0 = time.time(); vals = {}
    try:
        with httpx.Client(timeout=600) as c:
            r = None
            for s in p["steps"]:
                path = s["path"].format(**vals)
                r = c.request(s["method"], base + path, json=s.get("json"))
                if r.status_code >= 400:
                    return p["app"], "FAIL", time.time()-t0, f"HTTP {r.status_code}: {r.text[:300]}"
                if s.get("extract"):
                    vals["job_id"] = r.json()[s["extract"]]
            body = r.json()
            if p["poll"]:
                while time.time()-t0 < 900:
                    body = c.get(base + p["poll"]["path"].format(**vals)).json()
                    if body.get(p["poll"]["done_field"]) in p["poll"]["done_values"]: break
                    time.sleep(5)
                if body.get("status") == "error":
                    return p["app"], "FAIL", time.time()-t0, f"job error: {str(body.get('error'))[:300]}"
            ans = get(body, p["answer_field"])
            text = ans if isinstance(ans, str) else json.dumps(ans)[:2000]
            if not ans or any(b in (text or "")[:400] for b in BAD):
                return p["app"], "FAIL", time.time()-t0, (text or json.dumps(body))[:300]
            return p["app"], "PASS", time.time()-t0, " ".join(text.split())[:160]
    except Exception as e:
        return p["app"], "FAIL", time.time()-t0, f"{type(e).__name__}: {e}"[:300]



# ── Non-showcase apps (run locally; not in the all-in-one image) ─────────────
# Skipped on purpose: box_qa (needs Box creds), code_engine_deployer (acts on your
# ibmcloud login), bird_invocable_api_creator (needs the BIRD dataset).
SPEC = '{"openapi":"3.0.0","info":{"title":"Pet API","version":"1.0"},"paths":{"/pets":{"get":{"summary":"List pets","parameters":[{"name":"limit","in":"query","schema":{"type":"integer"}}],"responses":{"200":{"description":"A list of pets"}}}}}}'
D = str(Path(__file__).resolve().parent.parent / "cuga-apps" / "apps" / "deck_forge" / "data")
def _a(app, port, q, path="/ask", field="answer", extra=None):
    j = {"question": q}; j.update(extra or {})
    return {"app": app, "port": port, "steps": [{"method": "POST", "path": path, "json": j}], "poll": None, "answer_field": field}
ADDITIONAL = [
 {"app": "api_doc_gen", "port": 28811, "steps": [{"method": "POST", "path": "/load-spec", "json": {"raw": SPEC}}, {"method": "POST", "path": "/ask", "json": {"question": "In one sentence, what does GET /pets do and what parameters does it take?"}}], "poll": None, "answer_field": "answer"},
 {"app": "brief_budget", "port": 28816, "steps": [{"method": "POST", "path": "/api/run", "json": {"question": "What is the James Webb Space Telescope? Answer in two sentences.", "budget": 5}, "extract": "session_id"}], "poll": {"path": "/api/result/{job_id}", "done_field": "status", "done_values": ["done", "error"]}, "answer_field": "brief"},
 _a("code_explainer", 28838, "Explain this Python in one sentence: print(sum(x*x for x in range(5)))"),
 {"app": "code_reviewer", "port": 28807, "steps": [{"method": "POST", "path": "/review", "json": {"code": "def div(a, b):\n    return a / b", "language": "python", "focus": "bugs"}}], "poll": None, "answer_field": "review"},
 _a("compare_two", 28833, "Compare Python and Go in two sentences."),
 _a("crypto_101", 28840, "What is Bitcoin's current price, in one sentence?"),
 {"app": "deck_forge", "port": 28802, "steps": [{"method": "POST", "path": "/api/generate", "json": {"directory": D, "topic": "Transformers in 3 slides", "agent_type": "cuga"}, "extract": "session_id"}], "poll": {"path": "/api/session/{job_id}", "done_field": "status", "done_values": ["done", "error"]}, "answer_field": "result"},
 _a("drop_summarizer", 28794, "In one sentence, what kinds of files can you summarize?"),
 _a("explain_like_five", 28830, "Explain why the sky is blue like I'm five, in two sentences."),
 _a("fact_checker", 28832, "Fact-check: The Great Wall of China is visible from space with the naked eye."),
 _a("hacker_news_digest", 28841, "What is the top Hacker News story right now? One sentence."),
 _a("ibm_whats_new", 28814, "What's one recent update to IBM Cloud Code Engine? One sentence."),
 _a("on_this_day", 28834, "What happened on July 20 in history? Give one event."),
 _a("paper_plain_english", 28836, "Explain arXiv paper 1706.03762 (Attention Is All You Need) in plain English in two sentences."),
 _a("repo_explainer", 28837, "Explain https://github.com/psf/requests briefly."),
 _a("repo_explainer_2", 28839, "Explain https://github.com/pallets/flask briefly."),
 _a("smart_todo", 28800, "What's on my todo list?"),
 {"app": "trip_designer", "port": 28817, "steps": [{"method": "POST", "path": "/api/run", "json": {"destination": "Lisbon", "days": 1, "travel_month": "May", "origin_city": "", "interests": ["food"], "travel_style": "budget", "constraints": "keep it short"}, "extract": "session_id"}], "poll": {"path": "/api/result/{job_id}", "done_field": "status", "done_values": ["done", "error"]}, "answer_field": "itinerary"},
 _a("trivia_quiz", 28831, "Give me 1 easy trivia question about the solar system, with the answer."),
 _a("voice_journal", 28799, "How many journal entries do I have? One sentence."),
 _a("weather_wardrobe", 28835, "What should I wear in Boston today? One sentence."),
 _a("weather_wardrobe_2", 38842, "What should I wear in Seattle today? One sentence."),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base", help="'host' for a local stack, or the all-in-one base URL")
    ap.add_argument("apps", nargs="*", help="only these app ids")
    ap.add_argument("--set", choices=["showcase", "additional", "all"], default="showcase")
    a = ap.parse_args()
    table = {"showcase": PROBES, "additional": ADDITIONAL, "all": PROBES + ADDITIONAL}[a.set]
    todo = [p for p in table if not a.apps or p["app"] in a.apps]
    fails = 0
    with cf.ThreadPoolExecutor(6) as ex:
        for app, st, dt, info in ex.map(lambda p: run(p, a.base), todo):
            fails += st != "PASS"
            print(f"{st}  {app:<26} {dt:6.0f}s  {info}", flush=True)
    print(f"\n{len(todo) - fails}/{len(todo)} passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
