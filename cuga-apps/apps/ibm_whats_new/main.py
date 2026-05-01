"""
IBM What's New Monitor — web UI powered by CugaAgent
=====================================================
Tracks IBM Cloud service release notes and "What's New" announcements.
Configure which services to watch, then get a scheduled digest or ask
ad-hoc questions about recent IBM Cloud changes.

Run:
    python main.py
    python main.py --port 28814
    python main.py --provider anthropic

Then open: http://127.0.0.1:28814

Prerequisites:
    pip install -r requirements.txt
    export TAVILY_API_KEY=...   # required

Environment variables:
    LLM_PROVIDER         rits | anthropic | openai | ollama | watsonx | litellm
    LLM_MODEL            model override
    AGENT_SETTING_CONFIG path to agent settings TOML
    TAVILY_API_KEY       Tavily API key (required)
    SMTP_HOST            smtp.gmail.com (optional)
    SMTP_USERNAME        sender email
    SMTP_PASSWORD        app password
    DIGEST_TO            recipient email for digests
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import smtplib
import sys
import uuid
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

_DIR       = Path(__file__).parent
_DEMOS_DIR = _DIR.parent
for _p in [str(_DIR), str(_DEMOS_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Persistent store
# ---------------------------------------------------------------------------

_STORE_PATH = _DIR / ".store.json"

_DEFAULT_SERVICES = [
    "Code Engine",
    "watsonx.ai",
    "IBM Kubernetes Service",
    "Databases for PostgreSQL",
    "Cloud Object Storage",
]


def _load_store() -> dict:
    try:
        return json.loads(_STORE_PATH.read_text()) if _STORE_PATH.exists() else {}
    except Exception as exc:
        log.warning("Could not read store: %s", exc)
        return {}


def _save_store(data: dict) -> None:
    try:
        _STORE_PATH.write_text(json.dumps(data, indent=2))
    except Exception as exc:
        log.warning("Could not write store: %s", exc)


def _update_store(**fields) -> None:
    data = _load_store()
    data.update(fields)
    _save_store(data)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def _make_tools():
    # Delegated to MCP server(s): web.
    from _mcp_bridge import load_tools
    return load_tools(["web"])


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = """\
# IBM What's New Monitor

You track IBM Cloud service release notes and "What's New" announcements.

## Tools

| Tool | When to use |
|---|---|
| `web_search(query)` | Find recent IBM Cloud updates. Use targeted queries: "IBM <service> release notes 2026" or "IBM <service> what is new". One search per service. |
| `fetch_webpage(url)` | Read the full release notes page when a search result looks highly relevant. |

Always call tools. Never fabricate dates, version numbers, or feature names.

---

## Digest mode (checking a service for updates)

When asked to check what is new for a specific IBM Cloud service:
1. Call `web_search("IBM <service> release notes what is new 2026")`.
2. If a release notes page appears in the results, call `fetch_webpage(url)` on it.
3. Extract: new features, fixes, breaking changes, deprecations — with dates where available.
4. If meaningful updates were found, begin your response with exactly `UPDATE:` on the first line.
5. If nothing new or relevant: respond with exactly `No updates found for: <service>` — nothing more.

Format for updates:
  **IBM Code Engine** — release notes
  - [Apr 2026] Support for custom domain mapping in private visibility apps
  - [Mar 2026] Cold start latency reduced by up to 40%

---

## Query mode (ad-hoc chat)

For free-form questions about IBM Cloud changes:
- Use `web_search` (include 'site:ibm.com' + 'release notes' / 'what's new') with targeted terms, then optionally fetch 1–2 pages for depth.
- Answer concisely and cite every source with title + URL.
- Include dates where available.

---

## Format rules

- **Bold** service names and key feature names.
- No fabricated facts — if you cannot find it, say so.
- No filler, no disclaimers.
"""


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

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
    os.environ.setdefault("AGENT_SETTING_CONFIG",
                          _provider_toml.get(provider, "settings.rits.toml"))

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
    )


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

_email_config: dict = {}


def _get_email_cfg() -> dict:
    return {
        "host":     _email_config.get("host")     or os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "user":     _email_config.get("user")     or os.getenv("SMTP_USERNAME", ""),
        "password": _email_config.get("password") or os.getenv("SMTP_PASSWORD", ""),
        "to":       _email_config.get("to")       or os.getenv("DIGEST_TO", ""),
    }


def _send_email(subject: str, body: str) -> bool:
    cfg = _get_email_cfg()
    if not (cfg["to"] and cfg["user"] and cfg["password"]):
        log.info("[EMAIL — not configured] %s", subject)
        return False
    msg            = MIMEText(body)
    msg["Subject"] = subject
    msg["From"]    = cfg["user"]
    msg["To"]      = cfg["to"]
    try:
        with smtplib.SMTP_SSL(cfg["host"], 465) as smtp:
            smtp.login(cfg["user"], cfg["password"])
            smtp.send_message(msg)
        log.info("Email sent → %s  subject=%s", cfg["to"], subject)
        return True
    except Exception as exc:
        log.error("Failed to send email: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Digest runner + background scheduler
# ---------------------------------------------------------------------------

_digest_log: list[dict] = []   # capped at 15 entries


async def _run_digest(agent, services: list[str]) -> dict:
    """Check all tracked services for new updates. Returns a log entry."""
    if not services:
        return {
            "id":        str(uuid.uuid4())[:8],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary":   "No services configured.",
            "updates":   [],
            "sent":      False,
        }

    updates: list[str] = []
    for service in services:
        prompt = (
            f"Check what is new for IBM Cloud service: {service}\n"
            f"Use web_search to find recent release notes for {service}.\n"
            f"If you find updates, start with 'UPDATE:' and list them.\n"
            f"If nothing found, respond with 'No updates found for: {service}'"
        )
        try:
            result = await agent.invoke(prompt, thread_id=f"digest-{service.replace(' ', '-')}")
            answer = result.answer
        except Exception as exc:
            answer = f"Error checking {service}: {exc}"

        log.info("[DIGEST] %s → %s", service, answer[:80])
        if answer.strip().startswith("UPDATE:"):
            updates.append(answer)

    sent = False
    if updates:
        body    = "\n\n---\n\n".join(updates)
        subject = f"IBM What's New — {datetime.now(timezone.utc).strftime('%b %d, %Y')}"
        sent    = _send_email(subject, body)

    entry = {
        "id":        str(uuid.uuid4())[:8],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary":   f"{len(updates)} service(s) updated out of {len(services)} checked.",
        "updates":   updates,
        "sent":      sent,
    }
    _digest_log.insert(0, entry)
    if len(_digest_log) > 15:
        _digest_log.pop()

    _update_store(last_run=entry["timestamp"])
    return entry


async def _digest_scheduler(agent) -> None:
    """Background task: checks whether a scheduled digest is due every 5 minutes."""
    while True:
        await asyncio.sleep(300)  # check every 5 minutes
        data     = _load_store()
        schedule = data.get("schedule", "daily")
        if schedule == "off":
            continue

        last_run = data.get("last_run")
        now      = datetime.now(timezone.utc)
        due      = False

        if last_run is None:
            due = True
        else:
            try:
                elapsed = (now - datetime.fromisoformat(last_run)).total_seconds()
                if schedule == "daily"  and elapsed >= 86400:
                    due = True
                elif schedule == "weekly" and elapsed >= 604800:
                    due = True
            except Exception:
                due = True

        if not due:
            continue

        services = data.get("services", [])
        log.info("[SCHEDULER] Digest due (%s) — checking %d services", schedule, len(services))
        await _run_digest(agent, services)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

from pydantic import BaseModel  # noqa: E402


class AskReq(BaseModel):
    question: str


class ServiceAddReq(BaseModel):
    name: str


class ServiceRemoveReq(BaseModel):
    name: str


class ScheduleReq(BaseModel):
    schedule: str   # "daily" | "weekly" | "off"


class EmailConfigReq(BaseModel):
    host: str = "smtp.gmail.com"
    user: str
    password: str
    to: str


class EmailSendReq(BaseModel):
    subject: str
    body: str


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

def _web(port: int) -> None:
    import uvicorn
    from contextlib import asynccontextmanager
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, JSONResponse
    from ui import _HTML

    _agent = make_agent()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        asyncio.create_task(_digest_scheduler(_agent))
        yield

    app = FastAPI(title="IBM What's New Monitor", docs_url=None, redoc_url=None,
                  lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    # Restore persisted state
    stored = _load_store()
    if stored.get("email"):
        global _email_config
        _email_config = stored["email"]
        log.info("Restored email config → %s", _email_config.get("to"))
    if not stored.get("services"):
        _update_store(services=_DEFAULT_SERVICES, schedule="daily")
        log.info("Initialized default services")
    else:
        log.info("Restored %d service(s), schedule=%s",
                 len(stored.get("services", [])), stored.get("schedule", "daily"))

    # ── Chat ──────────────────────────────────────────────────────────────────

    @app.post("/ask")
    async def api_ask(req: AskReq):
        try:
            result = await _agent.invoke(req.question, thread_id="chat")
            return {"answer": result.answer}
        except Exception as exc:
            log.exception("Agent error")
            return JSONResponse({"error": str(exc)}, status_code=500)

    # ── Services ──────────────────────────────────────────────────────────────

    @app.get("/services")
    def services_list():
        data = _load_store()
        return {"services": data.get("services", []), "schedule": data.get("schedule", "daily")}

    @app.post("/services/add")
    def services_add(req: ServiceAddReq):
        data     = _load_store()
        services = data.get("services", [])
        name     = req.name.strip()
        if name and name not in services:
            services.append(name)
            data["services"] = services
            _save_store(data)
        return {"services": _load_store().get("services", [])}

    @app.post("/services/remove")
    def services_remove(req: ServiceRemoveReq):
        data     = _load_store()
        services = [s for s in data.get("services", []) if s != req.name]
        data["services"] = services
        _save_store(data)
        return {"services": services}

    @app.post("/schedule")
    def schedule_set(req: ScheduleReq):
        _update_store(schedule=req.schedule)
        return {"schedule": req.schedule}

    # ── Digest ────────────────────────────────────────────────────────────────

    @app.post("/digest/run")
    async def digest_run():
        services = _load_store().get("services", [])
        entry    = await _run_digest(_agent, services)
        return entry

    @app.get("/digest/recent")
    def digest_recent():
        return {"log": _digest_log}

    # ── Email ─────────────────────────────────────────────────────────────────

    @app.post("/email/config")
    def email_config(req: EmailConfigReq):
        global _email_config
        _email_config = {"host": req.host, "user": req.user,
                         "password": req.password, "to": req.to}
        _update_store(email=_email_config)
        log.info("Email config updated → %s", req.to)
        return {"status": "saved", "to": req.to}

    @app.get("/email/status")
    def email_status():
        cfg        = _get_email_cfg()
        configured = bool(cfg["to"] and cfg["user"] and cfg["password"])
        return {"configured": configured, "to": cfg["to"],
                "host": cfg["host"], "user": cfg["user"]}

    @app.post("/email/send")
    def email_send(req: EmailSendReq):
        sent = _send_email(req.subject, req.body)
        return {"status": "sent" if sent else "not_configured"}

    # ── UI ────────────────────────────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def ui():
        return HTMLResponse(_HTML)

    print(f"\n  IBM What's New Monitor  →  http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IBM What's New Monitor")
    parser.add_argument("--port",     type=int, default=28814)
    parser.add_argument("--provider", "-p", default=None,
        choices=["rits", "watsonx", "openai", "anthropic", "litellm", "ollama"])
    parser.add_argument("--model", "-m", default=None)
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    _web(args.port)
