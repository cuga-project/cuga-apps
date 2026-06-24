"""
IBM Cloud Architecture Advisor — AI-powered service recommendation
==================================================================
Describe what you want to build and the agent recommends the right IBM Cloud
services, explains how they connect, and provides ibmcloud CLI commands.

Uses the IBM Global Catalog public API (no key required) for real service data,
plus optional Tavily search for architecture patterns and pricing docs.

Run:
    python main.py
    python main.py --port 28812
    python main.py --provider anthropic

Then open: http://127.0.0.1:28812

Environment variables:
    LLM_PROVIDER         rits | anthropic | openai | ollama | watsonx | litellm
    LLM_MODEL            model override
    AGENT_SETTING_CONFIG path to agent settings TOML
    TAVILY_API_KEY       Tavily search key (optional — for architecture pattern docs)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

_DIR       = Path(__file__).parent
_DEMOS_DIR = _DIR.parent
for _p in [str(_DIR), str(_DEMOS_DIR)]:
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

_CATALOG_API = "https://globalcatalog.cloud.ibm.com/api/v1"


def _http_get(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "cuga-ibm-advisor/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _make_tools():
    from langchain_core.tools import tool

    @tool
    def search_ibm_catalog(query: str) -> str:
        """
        Search the IBM Cloud Global Catalog for real IBM Cloud services.
        Returns service names, descriptions, and catalog URLs.
        Always call this before recommending services to verify they exist.

        Args:
            query: Keywords describing the needed capability, e.g. "message queue",
                   "managed kubernetes", "object storage", "event streaming",
                   "serverless functions", "vector database".

        Returns:
            JSON list of matching IBM Cloud services with names and descriptions.
        """
        try:
            params = urllib.parse.urlencode({
                "q": query,
                "kind": "service",
                "_limit": "8",
                "_sort": "name",
            })
            data = _http_get(f"{_CATALOG_API}?{params}")
            resources = data.get("resources", [])
            results = []
            for r in resources:
                name = r.get("name", "")
                ov   = r.get("overview_ui", {}).get("en", {})
                disp = ov.get("display_name") or name
                desc = ov.get("description", "")[:250]
                tags = [t for t in r.get("tags", [])
                        if not t.startswith("rc:") and not t.startswith("iam:")][:5]
                results.append({
                    "name":         name,
                    "display_name": disp,
                    "description":  desc,
                    "tags":         tags,
                    "catalog_url":  f"https://cloud.ibm.com/catalog/services/{name}",
                })
            log.info("search_ibm_catalog(%r): %d results", query, len(results))
            return json.dumps({"query": query, "services": results})
        except Exception as exc:
            return json.dumps({"error": str(exc), "query": query})

    # web_search is delegated to mcp-web's web_search; the LLM is
    # instructed by the system prompt to append "site:ibm.com" to queries.
    from _mcp_bridge import load_tools
    web_tools = load_tools(["web"])

    return [search_ibm_catalog, *web_tools]


_SYSTEM = """\
# IBM Cloud Architecture Advisor

You help users design cloud architectures using real IBM Cloud services.

## Workflow

**When a user describes what they want to build:**
1. Call `search_ibm_catalog` with 2–3 focused keyword queries to find relevant services
   (search separately for each capability, e.g. "message queue", "object storage",
   "serverless functions").
2. Optionally call `web_search` (append `site:ibm.com OR site:cloud.ibm.com` to the query) to find architecture patterns, pricing tiers,
   or capability comparisons between candidate services.
3. Recommend 3–7 IBM Cloud services. For each, state its role in the architecture.
4. Describe how they connect: data flows, APIs, event triggers, integration points.
5. Provide `ibmcloud` CLI commands to provision each service.
6. Give a cost indication: note which services have Lite/free plans vs. pay-as-you-go.

**When the user asks for refinements:**
- "Make it highly available" → add multi-zone regions, redundancy, load balancing
- "Add compliance / HIPAA / FedRAMP" → steer toward FSCloud-certified services
- "Show Terraform" → output a basic Terraform IBM provider config instead of CLI
- "Compare X vs Y" → call `search_ibm_catalog` for both; explain trade-offs
- "AWS equivalent" → map AWS services to their IBM Cloud counterparts

## Output format

Structure every architecture recommendation as:

**Architecture: [descriptive name]**

**IBM Cloud Services:**
- **[Display Name]** (`[service-name]`): Role in the architecture.
  Docs: https://cloud.ibm.com/docs/[service-name]
- …

**How they connect:**
[2–4 sentences on data flow and integration]

**Get started — ibmcloud CLI:**
```bash
ibmcloud login --sso
# provision each service:
ibmcloud resource service-instance-create …
```

**Cost indication:** [note Lite plan availability; link https://cloud.ibm.com/estimator]

**References & further reading:**
Always close with this section. Include, as a markdown bullet list:
- One IBM Cloud docs link per recommended service:
  `https://cloud.ibm.com/docs/[service-name]` (use the exact catalog `name`).
- 2–4 relevant general references from this list, picked for the use case:
  - Docs home — https://cloud.ibm.com/docs
  - Architecture patterns & reference architectures — https://www.ibm.com/architectures
  - Pricing & free/Lite tier — https://cloud.ibm.com/pricing
  - Cost estimator — https://cloud.ibm.com/estimator
  - Security & compliance — https://cloud.ibm.com/docs/overview?topic=overview-security
  - High availability & DR — https://cloud.ibm.com/docs/overview?topic=overview-zero-downtime
  - Terraform (IBM Cloud provider) — https://registry.terraform.io/providers/IBM-Cloud/ibm/latest/docs
- If `web_search` surfaced an especially relevant tutorial, solution guide, or
  blog post, cite it here too with its title and URL.

## Rules
- Only recommend services confirmed by `search_ibm_catalog` results
- Never invent IBM service names — use exact `name` values from the catalog
- Keep the architecture focused: 3–7 services unless the use case demands more
- If the user mentions AWS/Azure equivalents, map them explicitly
- If `search_ibm_catalog` returns no results for a capability, say so and suggest
  an alternative approach
- ALWAYS include a per-service docs link and the References section — a
  recommendation without documentation pointers is incomplete.
- Write all links as real markdown so they render as clickable references.
"""


def make_agent():
    _provider_toml = {
        "rits":      "settings.rits.toml",
        "watsonx":   "settings.watsonx.toml",
        "openai":    "settings.openai.toml",
        "anthropic": "settings.openai.toml",
        "litellm":   "settings.litellm.toml",
        "ollama":    "settings.openai.toml",
    }
    provider = (os.getenv("LLM_PROVIDER") or "").lower()
    toml = _provider_toml.get(provider, "settings.rits.toml")
    os.environ.setdefault("AGENT_SETTING_CONFIG", toml)

    from cuga import CugaAgent
    from _llm import create_llm

    return CugaAgent(
        model=create_llm(
            provider=os.getenv("LLM_PROVIDER"),
            model=os.getenv("LLM_MODEL"),
        ),
        tools=_make_tools(),
        special_instructions=_SYSTEM,
        cuga_folder=str(_DIR / ".cuga"),
        # CUGA's policy DB is a global sqlite store shared by every app. Don't
        # auto-load it, or an output-formatter persisted by another app (e.g.
        # find_a_doctor's doctor board) bleeds in and the model emits that board
        # instead of this app's answer.
        auto_load_policies=False,
    )


class AskReq(BaseModel):
    question: str


def _web(port: int) -> None:
    import uvicorn
    from ui import _HTML

    agent = make_agent()
    app   = FastAPI(title="IBM Cloud Architecture Advisor")
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )

    @app.post("/ask")
    async def api_ask(req: AskReq):
        from _usage import track_utterance; track_utterance(req.question)
        try:
            result = await agent.invoke(req.question, thread_id=uuid.uuid4().hex)
            return {"answer": result.answer}
        except Exception as exc:
            log.exception("Agent error")
            return JSONResponse({"error": str(exc)}, status_code=500)

    @app.get("/", response_class=HTMLResponse)
    async def ui():
        return HTMLResponse(_HTML)

    # Public deployment: layered, in-memory rate limiting on POST.
    from _ratelimit import install_rate_limit
    install_rate_limit(app)
    from _usage import install_usage
    install_usage(app)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IBM Cloud Architecture Advisor")
    parser.add_argument("--port",     type=int, default=28812)
    parser.add_argument("--provider", "-p", default=None,
        choices=["rits", "watsonx", "openai", "anthropic", "litellm", "ollama"])
    parser.add_argument("--model",    "-m", default=None)
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    print(f"\n  IBM Cloud Architecture Advisor  →  http://127.0.0.1:{args.port}\n")  # default 28812
    _web(args.port)
