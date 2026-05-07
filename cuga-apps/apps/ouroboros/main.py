"""
Ouroboros — CUGA finds its next client (multi-agent edition)
============================================================

A CugaSupervisor orchestrating 7 specialist CugaAgents. Each specialist is
backed by one skill (SKILL.md + tools.py) under ./skills/. The supervisor's
planner decides which specialist to delegate to, each runs in its own
context, and the pitch+email writer specialist returns the final structured
leads JSON which the server parses and stores per-thread.

CUGA capabilities tapped (skills-branch SDK):
  • CugaSupervisor        — A2A multi-agent orchestration
  • CugaAgent             — per-specialist plan/execute graph
  • CugaLite step limits  — bounded planner per agent
  • Policies              — intent_guard, tool_guide, output_formatter
  • Skills (declarative)  — SKILL.md + tools.py, host-loaded at startup

Run:
    python main.py --port 28822
    python main.py --provider anthropic
    python main.py --provider rits --model gpt-oss-120b

Then open: http://127.0.0.1:28822

Env vars:
    LLM_PROVIDER          rits | anthropic | openai | watsonx | litellm | ollama
    LLM_MODEL             model name override
    AGENT_SETTING_CONFIG  CUGA settings TOML (defaulted in main)
    CUGA_TARGET=ce        forces public Code Engine MCP URLs
    MCP_<NAME>_URL        per-server URL override
"""
from __future__ import annotations

import argparse
import asyncio
import html
import json
import logging
import os
import re
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

# Default to the hosted Code Engine MCP servers; user-set value still wins.
os.environ.setdefault("CUGA_TARGET", "ce")

# CUGA's `cuga.config` module reads AGENT_SETTING_CONFIG once at import
# time and pins the agent-internal LLM TOML. Setting it inside
# make_supervisor() is too late — by then specialists.py has already
# imported cuga.sdk indirectly. So we resolve it here, before the first
# cuga import in this process.
_AGENT_SETTING_CONFIG = {
    "rits":      "settings.rits.toml",
    "watsonx":   "settings.watsonx.toml",
    "openai":    "settings.openai.toml",
    "groq":      "settings.groq.toml",
    "litellm":   "settings.litellm.toml",
    "anthropic": "settings.openai.toml",   # cuga has no "anthropic"
                                            # platform; openai TOML is the
                                            # closest fallback. Internal
                                            # nodes will fail unless the
                                            # user runs a proxy or we
                                            # monkey-patch LLMManager.
    "ollama":    "settings.openai.toml",
}
_provider = (os.getenv("LLM_PROVIDER") or "rits").lower()
os.environ.setdefault(
    "AGENT_SETTING_CONFIG",
    _AGENT_SETTING_CONFIG.get(_provider, "settings.rits.toml"),
)


def _patch_executor_timeout(seconds: int = 180) -> None:
    """Bump CUGA's hardcoded 30s code-executor timeout.

    `code_executor.py:148` calls
        await executor.execute(..., timeout=30)
    with no env / config override. A specialist's CugaLite graph runs
    multiple LLM steps for one delegation, and 30s is too tight for
    them — scout-on-cold-LLM regularly takes 30–60s. We monkey-patch
    LocalExecutor.execute so any caller-provided timeout < `seconds`
    is bumped up. Idempotent.
    """
    try:
        from cuga.backend.cuga_graph.nodes.cuga_lite.executors.local import (
            local_executor as _le,
        )
    except ImportError:
        return
    if getattr(_le.LocalExecutor.execute, "_ouroboros_patched", False):
        return
    _orig = _le.LocalExecutor.execute

    async def _patched(self, *args, timeout: int = 30, **kwargs):
        bumped = max(int(timeout or 30), seconds)
        return await _orig(self, *args, timeout=bumped, **kwargs)

    _patched._ouroboros_patched = True   # type: ignore[attr-defined]
    _le.LocalExecutor.execute = _patched   # type: ignore[assignment]
    log = __import__("logging").getLogger(__name__)
    log.info("patched LocalExecutor.execute timeout floor to %ds", seconds)


_patch_executor_timeout(180)

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


# ── Per-thread server-side session ──────────────────────────────────────
# The supervisor itself doesn't have inline session-state hooks on this
# branch, so the server holds the cross-turn memory: location, categories,
# pitch_focus, plus the most recent leads board parsed from the writer
# specialist's output.

_sessions: dict[str, dict] = {}


def _get_session(thread_id: str) -> dict:
    if thread_id not in _sessions:
        _sessions[thread_id] = {
            "target_location": "",
            "categories":      [],
            "pitch_focus":     "",
            "leads":           None,
            "history":         [],
        }
    return _sessions[thread_id]


def _format_session_brief(session: dict) -> str:
    parts = []
    if session["target_location"]:
        parts.append(f'location={session["target_location"]!r}')
    if session["categories"]:
        parts.append(f'categories={session["categories"]}')
    if session["pitch_focus"]:
        parts.append(f'pitch_focus={session["pitch_focus"]!r}')
    return "; ".join(parts) if parts else "(empty)"


# ── Extract the structured leads JSON from the supervisor's text answer ──
# The pitch_email_writer specialist is instructed to emit a fenced ```json
# block. We strip that off, parse it, and store it in the session.

_JSON_FENCE_RE = re.compile(r"```json\s*\n?(.*?)\n?```", re.DOTALL | re.IGNORECASE)


# ── Per-turn run metadata (so we can debug what each stage actually produced) ─
_RUNS_DIR = _DIR / "runs"
try:
    _RUNS_DIR.mkdir(exist_ok=True)
except Exception:
    pass


# ── Email alerts ────────────────────────────────────────────────────────
# Per-run email notification. Triggered after every _handle_full_turn.
# Body clearly labels source (user vs loop) so the operator can tell what
# fired the run.
#
#   SMTP creds (operator-level): SMTP_HOST, SMTP_PORT, SMTP_USERNAME,
#                                SMTP_PASSWORD, FROM_EMAIL — env vars
#   Per-app config (UI-tunable): _EMAIL_STORE = .email_store.json
#       { "enabled": bool, "recipient": str,
#         "min_leads": int (skip if leads_count < this),
#         "include_loop": bool, "include_user": bool }
_EMAIL_STORE = _DIR / ".email_store.json"

# Default model: NO master "enabled" toggle. Recipient + valid SMTP creds are
# the implicit gate — set them and you get emails by default. Per-source
# toggles let you opt out of one kind of run while keeping the other.
#
# Email addresses pre-filled to the operator's account so they only have
# to paste the app password to start sending. Override anytime in the UI.
_DEFAULT_EMAIL_ADDRESS = "anupama.murthi@gmail.com"
_EMAIL_DEFAULTS = {
    "recipient":     _DEFAULT_EMAIL_ADDRESS,
    "min_leads":     0,
    "include_user":  True,
    "include_loop":  True,
    # SMTP creds (optional UI overrides; fall back to env vars when blank)
    "smtp_host":     "smtp.gmail.com",
    "smtp_port":     587,
    "smtp_username": _DEFAULT_EMAIL_ADDRESS,
    "smtp_password": "",
    "smtp_from":     _DEFAULT_EMAIL_ADDRESS,
}


def _email_load() -> dict:
    try:
        loaded = json.loads(_EMAIL_STORE.read_text())
    except Exception:
        loaded = {}
    cfg = dict(_EMAIL_DEFAULTS)
    cfg.update({k: v for k, v in (loaded or {}).items() if k in _EMAIL_DEFAULTS})
    return cfg


def _email_save(cfg: dict) -> None:
    try:
        _EMAIL_STORE.write_text(json.dumps(cfg, indent=2))
    except Exception as exc:
        log.warning("email store save failed: %s", exc)


def _smtp_settings() -> dict:
    """Effective SMTP creds: UI overrides win, then env vars, then defaults."""
    cfg = _email_load()
    env_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    env_port = int(os.getenv("SMTP_PORT", "587"))
    env_user = os.getenv("SMTP_USERNAME", "")
    env_pass = os.getenv("SMTP_PASSWORD", "")
    env_from = os.getenv("FROM_EMAIL", env_user)
    return {
        "host":     cfg.get("smtp_host") or env_host,
        "port":     int(cfg.get("smtp_port") or 0) or env_port,
        "username": cfg.get("smtp_username") or env_user,
        "password": cfg.get("smtp_password") or env_pass,
        "from":     cfg.get("smtp_from") or env_from,
    }


def _render_email_html(thread_id: str, question: str, answer: str,
                       leads: dict | None, source: str,
                       loop_id: str | None, elapsed_human: str) -> tuple[str, str]:
    """Return (subject, html_body). HTML stays simple & client-safe."""
    is_loop = source == "loop"
    src_label = ("🔁 LOOP FIRE" if is_loop else "👤 USER REQUEST")
    src_color = ("#a78bfa" if is_loop else "#94a3b8")
    leads_count = (len(leads.get("leads", []) or []) if leads else 0)
    location = (leads.get("location") if leads else None) or "—"

    subject = f"Ouroboros · {src_label} · {leads_count} leads · {question[:60]}"

    # Top-3 lead summary (deep_dive=True ones)
    rows = ""
    if leads:
        top = [l for l in (leads.get("leads") or [])
               if l.get("deep_dive")][:3]
        for l in top:
            rows += (
                f"<tr>"
                f"<td style='padding:6px 10px;border-bottom:1px solid #2a2a2a;color:#e6edf3'>"
                f"<strong>{html.escape(str(l.get('name', '?')))}</strong>"
                f"<div style='color:#888;font-size:11px'>{html.escape(str(l.get('category', '')))}</div></td>"
                f"<td style='padding:6px 10px;border-bottom:1px solid #2a2a2a;color:#facc15;font-weight:bold'>"
                f"{l.get('fit_score', '—')}/10</td>"
                f"<td style='padding:6px 10px;border-bottom:1px solid #2a2a2a;color:#cbd5e1;font-size:12px'>"
                f"{html.escape((l.get('pitch', '') or '')[:240])}…</td>"
                f"</tr>"
            )
    leads_table = (
        f"<table style='width:100%;border-collapse:collapse;background:#0d1117;"
        f"border:1px solid #2a2a2a;border-radius:6px;margin-top:14px'>"
        f"<thead><tr><th style='text-align:left;padding:8px 10px;color:#8b949e;"
        f"font-size:11px;text-transform:uppercase;border-bottom:1px solid #2a2a2a'>Lead</th>"
        f"<th style='text-align:left;padding:8px 10px;color:#8b949e;font-size:11px;"
        f"text-transform:uppercase;border-bottom:1px solid #2a2a2a'>Fit</th>"
        f"<th style='text-align:left;padding:8px 10px;color:#8b949e;font-size:11px;"
        f"text-transform:uppercase;border-bottom:1px solid #2a2a2a'>Pitch</th></tr></thead>"
        f"<tbody>{rows or '<tr><td colspan=3 style=\"padding:14px;color:#888;text-align:center\">No leads on this run.</td></tr>'}</tbody></table>"
    )

    loop_line = (
        f"<div style='font-size:12px;color:#888;margin-top:6px'>"
        f"Loop id: <code style='color:#c4b5fd'>{html.escape(loop_id or '')}</code></div>"
        if is_loop and loop_id else ""
    )

    body = f"""<!DOCTYPE html>
<html><body style='font-family:-apple-system,system-ui,sans-serif;background:#161b22;
color:#e6edf3;padding:24px;margin:0'>
  <div style='max-width:700px;margin:0 auto'>
    <div style='display:inline-block;padding:4px 12px;border-radius:12px;
                background:rgba(167,139,250,0.18);border:1px solid {src_color};
                color:{src_color};font-weight:bold;font-size:12px;letter-spacing:0.5px'>
      {src_label}
    </div>
    <h2 style='color:#e6edf3;margin:14px 0 4px'>{html.escape(question)}</h2>
    <div style='color:#8b949e;font-size:13px'>
      Location: <strong>{html.escape(str(location))}</strong>
      &nbsp;·&nbsp; {leads_count} leads
      &nbsp;·&nbsp; {html.escape(elapsed_human)}
      &nbsp;·&nbsp; thread <code>{html.escape(thread_id[:8])}</code>
    </div>
    {loop_line}
    {leads_table}
    <p style='color:#6b7280;font-size:11px;margin-top:18px'>
      Sent automatically by Ouroboros after a lead-hunt run completed.
      Configure or disable from the Email panel in the app UI.
    </p>
  </div>
</body></html>"""
    return subject, body


def _email_send_with_creds(to: str, subject: str, html_body: str,
                            host: str, port: int, username: str,
                            password: str, from_addr: str) -> tuple[bool, str]:
    """Blocking send with explicit SMTP creds. Run via asyncio.to_thread."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = from_addr
        msg["To"]      = to
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP(host, port, timeout=20) as srv:
            srv.starttls()
            srv.login(username, password)
            srv.send_message(msg)
        return True, f"sent to {to} via {host}:{port}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _email_send_sync(to: str, subject: str, html_body: str) -> tuple[bool, str]:
    """Blocking send using the stored/env SMTP settings. Used by background
    fire-and-forget sends after every run."""
    s = _smtp_settings()
    if not s["username"] or not s["password"] or not s["from"]:
        return False, "missing SMTP creds (SMTP_USERNAME/SMTP_PASSWORD/FROM_EMAIL or UI overrides)"
    if not to:
        return False, "no recipient configured"
    return _email_send_with_creds(to, subject, html_body,
                                  s["host"], s["port"], s["username"],
                                  s["password"], s["from"])


async def _maybe_send_email_for_run(thread_id: str, question: str,
                                     answer: str, leads: dict | None,
                                     source: str, loop_id: str | None,
                                     elapsed_human: str) -> None:
    """Fire-and-forget email send. The gate is: recipient set, SMTP creds
    available, and the per-source toggle for this run's source is on.
    Must never raise — pure best-effort."""
    try:
        cfg = _email_load()
        recipient = (cfg.get("recipient") or "").strip()
        if not recipient:
            return  # implicit "off"
        if source == "loop" and not cfg.get("include_loop", True):
            return
        if source == "user" and not cfg.get("include_user", True):
            return
        leads_count = len(leads.get("leads", []) or []) if leads else 0
        if leads_count < int(cfg.get("min_leads", 0)):
            log.info("[%s] email skipped — leads (%d) below min_leads (%d)",
                     thread_id[:8], leads_count, cfg.get("min_leads", 0))
            return
        subject, body = _render_email_html(
            thread_id, question, answer, leads, source, loop_id, elapsed_human
        )
        ok, info = await asyncio.to_thread(_email_send_sync, recipient, subject, body)
        if ok:
            log.info("[%s] email %s sent (%s): %s",
                     thread_id[:8], source, info, subject[:80])
        else:
            log.warning("[%s] email %s NOT sent: %s",
                        thread_id[:8], source, info)
    except Exception as exc:
        log.warning("[%s] _maybe_send_email_for_run failed: %s", thread_id[:8], exc)


def _coerce(value):
    """Best-effort coerce a supervisor variable to JSON-safe form."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_coerce(v) for v in value]
    if isinstance(value, dict):
        return {k: _coerce(v) for k, v in value.items()}
    return repr(value)


_DELEGATE_RE = re.compile(r"\bdelegate_to_([a-zA-Z0-9_]+)\s*\(")


def _agent_call_trace(supervisor) -> dict:
    """Extract an ordered trace of which specialist agents were called.

    The supervisor's planner emits `delegate_to_<agent>(...)` calls in
    AIMessage code blocks; each delegation produces an `Execution
    output:` HumanMessage immediately after. Walk the chat history and
    pair them up so we have:

      [ {step, agent, has_output, output_len, output_preview}, ... ]

    plus a per-agent count summary. Best-effort — if the supervisor
    state isn't available we return an empty trace.
    """
    trace: list[dict] = []
    counts: dict[str, int] = {}
    try:
        state = supervisor._supervisor_state
        messages = (
            state.get("supervisor_chat_messages", [])
            if isinstance(state, dict)
            else getattr(state, "supervisor_chat_messages", []) or []
        )
        step = 0
        for i, msg in enumerate(messages):
            role    = type(msg).__name__
            content = getattr(msg, "content", "") or ""
            if not isinstance(content, str):
                content = str(content)
            if role != "AIMessage":
                continue
            # Find every delegate_to_<name>( in this planner code block.
            for m in _DELEGATE_RE.finditer(content):
                agent = m.group(1)
                step += 1
                # The Execution output that follows this AIMessage is the
                # next HumanMessage with content starting "Execution output:".
                exec_out = ""
                for j in range(i + 1, len(messages)):
                    later = messages[j]
                    if type(later).__name__ != "HumanMessage":
                        continue
                    later_content = getattr(later, "content", "") or ""
                    if not isinstance(later_content, str):
                        later_content = str(later_content)
                    if later_content.startswith("Execution output:"):
                        exec_out = later_content[len("Execution output:"):].lstrip("\n")
                        break
                trace.append({
                    "step":           step,
                    "msg_index":      i,
                    "agent":          agent,
                    "has_output":     bool(exec_out),
                    "output_len":     len(exec_out),
                    "output_preview": exec_out[:300],
                })
                counts[agent] = counts.get(agent, 0) + 1
    except Exception as exc:
        log.debug("agent trace extraction failed: %s", exc)
    return {"calls": trace, "counts": counts, "total_calls": len(trace)}


def _harvest_supervisor_state(supervisor) -> dict:
    """Pull variables + chat messages out of the supervisor's last state.
    The supervisor's variables_manager preserves every variable created
    during code execution (including `final` from phase 3); the chat
    messages preserve every `Execution output:` line.
    """
    out: dict = {"variables": {}, "stages": []}

    try:
        vm = supervisor.variables_manager
        for name in vm.get_variable_names():
            try:
                out["variables"][name] = _coerce(vm.get_variable(name))
            except Exception as exc:
                out["variables"][name] = f"<unreadable: {exc}>"
    except Exception as exc:
        out["variables"]["__error__"] = str(exc)

    try:
        state = supervisor._supervisor_state
        messages = (
            state.get("supervisor_chat_messages", [])
            if isinstance(state, dict)
            else getattr(state, "supervisor_chat_messages", []) or []
        )
        for i, msg in enumerate(messages):
            role = type(msg).__name__
            content = getattr(msg, "content", "") or ""
            if not isinstance(content, str):
                content = str(content)
            stage = {
                "i":       i,
                "role":    role,
                "len":     len(content),
                "content": content[:12000],
            }
            if content.startswith("Execution output:"):
                stage["kind"] = "execution_output"
            out["stages"].append(stage)
    except Exception as exc:
        out["stages"].append({"error": str(exc)})

    return out


def _writer_output_from_state(supervisor) -> str | None:
    """Best-effort recovery of the writer specialist's full output.

    The supervisor's outer Conversational LLM tends to paraphrase the
    writer's JSON down to a one-liner, dropping the lead board. But the
    writer's actual output is preserved in two places:

      1. supervisor.variables_manager['final']  (the prelude binds
         `final = await delegate_to_pitch_email_writer(...)`)
      2. supervisor_chat_messages — the Execution output line that
         followed phase 3's `print(final)`.

    Try (1) first; fall back to (2).
    """
    try:
        vm = supervisor.variables_manager
        names = list(vm.get_variable_names())
        for cand in ("final", "writer_output", "lead_board", "enriched_list"):
            if cand in names:
                val = vm.get_variable(cand)
                if isinstance(val, str) and '"leads"' in val:
                    return val
    except Exception as exc:
        log.debug("variables_manager unreadable: %s", exc)

    try:
        state = supervisor._supervisor_state
        messages = (
            state.get("supervisor_chat_messages", [])
            if isinstance(state, dict)
            else getattr(state, "supervisor_chat_messages", []) or []
        )
        # Walk in reverse — the writer's print(final) is the LAST
        # Execution output before the supervisor's conversational turn.
        for msg in reversed(messages):
            content = getattr(msg, "content", "") or ""
            if not isinstance(content, str):
                continue
            if content.startswith("Execution output:") and '"leads"' in content:
                return content[len("Execution output:"):].lstrip("\n").strip()
    except Exception as exc:
        log.debug("chat-messages scan failed: %s", exc)

    return None


def _format_elapsed(ms: int) -> str:
    s = ms / 1000.0
    if s < 1:
        return f"{ms} ms"
    if s < 60:
        return f"{s:.1f} s"
    m = int(s // 60)
    rem = s - m * 60
    return f"{m}m {rem:.0f}s"


def _save_run(thread_id: str, question: str, answer: str,
              leads: dict | None, supervisor,
              started_at: datetime, elapsed_ms: int,
              source: str = "user", loop_id: str | None = None) -> str | None:
    """Persist this turn's metadata to runs/<thread_id>/<ts>.json so we
    can pick apart what each stage actually produced. Best-effort —
    failure here must never break the /ask response.

    `source` distinguishes a normal user turn ("user") from a loop fire
    ("loop"); `loop_id` is set when source='loop' so the UI can link
    back to the originating loop in the loops dashboard.
    """
    try:
        ts       = datetime.now(timezone.utc)
        run_dir  = _RUNS_DIR / re.sub(r"[^a-zA-Z0-9_\-]", "_", thread_id)[:64]
        run_dir.mkdir(parents=True, exist_ok=True)
        fname    = ts.strftime("%Y%m%dT%H%M%SZ") + ".json"
        path     = run_dir / fname
        agent_trace = _agent_call_trace(supervisor)
        record = {
            "thread_id":         thread_id,
            "timestamp":         ts.isoformat(),
            "started_at":        started_at.isoformat(),
            "elapsed_ms":        elapsed_ms,
            "elapsed_human":     _format_elapsed(elapsed_ms),
            "question":          question,
            "answer_full":       answer or "",
            "answer_len":        len(answer or ""),
            "leads_extracted":   bool(leads),
            "leads_count":       len(leads.get("leads", []) or []) if leads else 0,
            "leads":             leads,
            "agent_trace":       agent_trace,
            "supervisor_state":  _harvest_supervisor_state(supervisor),
            "source":            source,
            "loop_id":           loop_id,
        }
        path.write_text(json.dumps(record, indent=2, default=str, ensure_ascii=False))
        fanout = ", ".join(
            f"{a}×{n}" for a, n in agent_trace.get("counts", {}).items()
        ) or "(none)"
        log.info("[%s] run saved (%s%s): %s (%s, agents=[%s], stages=%d, vars=%d)",
                 thread_id[:8], source,
                 f"/{loop_id}" if loop_id else "",
                 path, record["elapsed_human"], fanout,
                 len(record["supervisor_state"].get("stages", [])),
                 len(record["supervisor_state"].get("variables", {})))
        return str(path)
    except Exception as exc:
        log.warning("[%s] run save failed: %s", thread_id[:8], exc)
        return None


def _normalize_leads_obj(obj: dict | None) -> dict | None:
    """Normalize the writer's JSON to the {location, leads:[…]} schema the
    right-panel UI expects. Tolerates writer-drift such as `lead_board`
    instead of `leads`, `company_name`/`business_name`/`title` for the
    lead name, missing top-level `location`, and `email_guess`/
    `owner_email_guess` for the contact email."""
    if not isinstance(obj, dict):
        return None
    out = dict(obj)

    # Top-level: leads container alias
    if "leads" not in out:
        for alt in ("lead_board", "results", "businesses"):
            if isinstance(out.get(alt), list):
                out["leads"] = out[alt]
                break
    if not isinstance(out.get("leads"), list):
        return None  # not a recognizable leads payload

    # Per-lead key aliases — only set the canonical key if missing.
    name_aliases  = ("company_name", "business_name", "title")
    email_aliases = ("email_guess", "owner_email_guess", "owner_email")
    norm_leads = []
    for raw in out["leads"]:
        if not isinstance(raw, dict):
            norm_leads.append(raw); continue
        l = dict(raw)
        if "name" not in l:
            for alt in name_aliases:
                if l.get(alt):
                    l["name"] = l[alt]; break
        if "email" not in l:
            for alt in email_aliases:
                if l.get(alt):
                    l["email"] = l[alt]; break
        norm_leads.append(l)
    out["leads"] = norm_leads

    # Top-level location: derive from the first lead's address if absent.
    if not out.get("location"):
        for l in norm_leads:
            addr = l.get("address") if isinstance(l, dict) else None
            if addr:
                # Take the trailing "City, ZIP" or last comma-separated chunk.
                parts = [p.strip() for p in str(addr).split(",") if p.strip()]
                if len(parts) >= 2:
                    out["location"] = ", ".join(parts[-2:])
                else:
                    out["location"] = parts[-1]
                break
    return out


def _extract_leads_json(text: str) -> dict | None:
    """Extract the writer's leads object from the supervisor's final answer.

    The writer fences its JSON in ```json``` per its SKILL.md, but the
    supervisor's planner sometimes summarises and strips the fence,
    leaving bare JSON or JSON-with-prose. Try four extraction shapes:
      1. fenced ```json``` block
      2. whole text as JSON
      3. first balanced { … } that contains a "leads"/"lead_board" key
      4. last balanced { … } in the text (some planners append extra
         prose after the JSON; we want the JSON, not the prose).

    Result is then normalized via _normalize_leads_obj to the canonical
    {location, leads:[{name, …}]} shape the right-panel UI expects.
    """
    if not text:
        return None

    def _is_leads_payload(obj):
        return isinstance(obj, dict) and any(
            isinstance(obj.get(k), list) for k in ("leads", "lead_board", "results", "businesses")
        )

    # 1. Fenced
    for raw in _JSON_FENCE_RE.findall(text):
        try:
            obj = json.loads(raw.strip())
            if _is_leads_payload(obj):
                return _normalize_leads_obj(obj)
        except json.JSONDecodeError:
            continue

    # 2. Whole text
    try:
        obj = json.loads(text.strip())
        if _is_leads_payload(obj):
            return _normalize_leads_obj(obj)
    except json.JSONDecodeError:
        pass

    # 3 + 4: balanced-brace scan.
    candidates: list[dict] = []
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and start >= 0:
                chunk = text[start:i + 1]
                try:
                    obj = json.loads(chunk)
                    if _is_leads_payload(obj):
                        candidates.append(obj)
                except json.JSONDecodeError:
                    pass
                start = -1
    if candidates:
        return _normalize_leads_obj(candidates[-1])

    return None


# ── Cheap user-input parser for session updates ─────────────────────────
# We keep this tiny and conservative — we only want to give the supervisor
# the minimum context (location + focus) it needs in the prompt. The agent
# doesn't read the session dict directly.

_LOCATION_HINT_RE = re.compile(
    r"\b(?:in|near|around|at)\s+([A-Z][\w &\-,'.]+?)(?:\s+(?:that|for|with|focus|pitch|—)|[?.,]|$)",
    re.IGNORECASE,
)


def _maybe_update_session(session: dict, question: str) -> None:
    """Heuristic: catch a location mention and stash it. The supervisor's
    own planner is the source of truth — this just helps continuity for
    follow-up questions where the user says 'now scout salons there'."""
    m = _LOCATION_HINT_RE.search(question)
    if m and not session["target_location"]:
        session["target_location"] = m.group(1).strip().rstrip(",.")


# ── Supervisor build ────────────────────────────────────────────────────

# Prepended to every /ask payload. CugaSupervisor.description is dead
# (cuga_supervisor_graph.py:379 hardcodes special_instructions=None);
# the user message is the only injection point.
#
# CRITICAL: do NOT include any triple-backtick sequences in this string.
# The supervisor extracts code via re.findall(r'```python(.*?)```')
# (cuga_supervisor_graph.py:35,63). Any extra triple-backtick in a code
# block — even inside a regex literal or a quoted example — corrupts
# the extraction (the non-greedy match closes on the wrong fence,
# producing malformed code with no print(), and the SDK then
# misclassifies the response as "final text answer, no code"). Use the
# words "JSON-fenced" / "code fence" instead of literal triple-backticks
# in any prose; use neutral angle brackets <like> in any code examples
# that need to allude to fences.
_TASK_PRELUDE = """\
=== OUROBOROS LEAD-HUNT CONTRACT ===

Every user request below is a lead-hunt. You are the supervisor; you
delegate to specialists. Run THREE PHASES in order. Phase 3 is
MANDATORY — the UI cannot render anything without it.

CORE DATA STRUCTURE: a single dict `enrichments` keyed by the candidate
index (0, 1, 2). Each value is itself a dict that accumulates the per-
candidate enrichment fields as the five sweeps run. By phase 3 every
candidate has its own self-contained bundle, so the writer never has
to align parallel lists.

PHASE 1 — scout + parse + initialize.
    user_question = <user request as Python string>
    scout_result = await delegate_to_scout(task=user_question)
    try:
        data = json.loads(scout_result.strip())
        candidates = data.get("candidates", []) or []
    except (json.JSONDecodeError, ValueError, AttributeError):
        data, candidates = {}, []
    top = candidates[:3]
    enrichments = {}
    for i in range(len(top)):
        enrichments[i] = {"candidate": top[i]}
    print(f"Got {len(candidates)} candidates; deep-diving top {len(top)}")

PHASE 2 — five specialist sweeps. Each sweep is ONE code block. Inside
the block, loop with enumerate(top) and call exactly ONE specialist;
write every return value into `enrichments[i][<key>]`. Run ALL FIVE
sweeps, in the exact order below. Do NOT skip any sweep. Do NOT
proceed to phase 3 until all five have completed. If a candidate has
no website, store the empty string under its key so the slot still
exists.

SWEEP 1 — voice_of_customer (every candidate):
    for i, c in enumerate(top):
        r = await delegate_to_voice_of_customer(
            task=f"Find verbatim review friction for {json.dumps(c)} in {data.get('display_name', '')}"
        )
        enrichments[i]["voc"] = r
    print(enrichments)

SWEEP 2 — site_auditor (skip empty website):
    for i, c in enumerate(top):
        if not c.get("website"):
            enrichments[i]["audit"] = ""
            continue
        r = await delegate_to_site_auditor(
            task=f"Audit this business: {json.dumps(c)}"
        )
        enrichments[i]["audit"] = r
    print(enrichments)

SWEEP 3 — revenue_estimator (every candidate):
    for i, c in enumerate(top):
        r = await delegate_to_revenue_estimator(
            task=f"Estimate ARR band for {json.dumps(c)} in {data.get('display_name', '')}"
        )
        enrichments[i]["revenue"] = r
    print(enrichments)

SWEEP 4 — person_finder (skip empty website):
    for i, c in enumerate(top):
        if not c.get("website"):
            enrichments[i]["person"] = ""
            continue
        r = await delegate_to_person_finder(
            task=f"Find decision-maker + email pattern for {json.dumps(c)}"
        )
        enrichments[i]["person"] = r
    print(enrichments)

SWEEP 5 — stack_scanner (skip empty website):
    for i, c in enumerate(top):
        if not c.get("website"):
            enrichments[i]["stack"] = ""
            continue
        r = await delegate_to_stack_scanner(
            task=f"Fingerprint third-party tools at {c.get('website', '')}"
        )
        enrichments[i]["stack"] = r
    print(enrichments)

PHASE 3 — writer. Build a SINGLE self-contained enriched_list so the
writer never has to zip parallel lists. Each entry is a complete bundle:
the candidate plus its audit / voc / revenue / person / stack.

    enriched_list = [enrichments[i] for i in range(len(top))]
    location_obj = {
        "location":     data.get("location", ""),
        "display_name": data.get("display_name", ""),
        "lat":          data.get("lat"),
        "lon":          data.get("lon"),
    }
    writer_task = (
        "Build the final ranked lead board per your SKILL.md schema.\\n\\n"
        f"User request: {user_question}\\n\\n"
        f"Location: {json.dumps(location_obj)}\\n\\n"
        f"All scout candidates (use #4..N as preliminary, deep_dive=false leads): {json.dumps(candidates)}\\n\\n"
        f"Enriched top {len(top)} (each dict carries its own audit / voc / revenue / person / stack):\\n"
        f"{json.dumps(enriched_list)}\\n\\n"
        "REQUIREMENTS — read these carefully:\\n"
        "1. Top 3 leads MUST have deep_dive=true. Every other field on the lead schema must be populated from the matching enrichment bundle (do not leave them null).\\n"
        "2. fit_score MUST be an integer 1-10. Never null.\\n"
        "3. pitch MUST be 60-150 words and cite at least one CONCRETE signal pulled from this lead's voc / audit / stack / person bundle. Quote a review verbatim if voc has one. Name a missing website feature if audit has one. Name an incumbent tool if stack has one. End with the CUGA capability that closes the gap and a measurable lift.\\n"
        "4. email_draft MUST have non-empty subject AND body, per your SKILL.md email rules.\\n"
        "5. Pull review-citation URLs from voc into evidence[]. Pull website_signals from audit. Pull stack into stack. Pull owner name + email_guess from person. Pull ARR band from revenue.\\n"
        "6. If a particular bundle field is empty, OMIT only that signal — do not fabricate. The pitch must still cite at least one real signal from another field.\\n"
        "7. Lower-ranked candidates (4..N): deep_dive=false, 1-2 sentence preliminary pitch from OSM data alone, skip the deep-dive fields per SKILL.md.\\n"
        "8. Use the location object verbatim for the top-level location/display_name/lat/lon.\\n\\n"
        "Output the JSON-fenced lead board first, then 2 short paragraphs of summary."
    )
    final = await delegate_to_pitch_email_writer(task=writer_task)
    print(final)

RETURN. After phase 3 returns, reply with the writer's output verbatim
as plain text (TYPE 2, no code fence). Do not paraphrase, do not wrap,
do not summarise.

HARD RULES:
  - Initialize `enrichments` dict in phase 1 BEFORE any sweep. Every
    phase-2 sweep WRITES into enrichments[i][<key>] for every i in
    range(len(top)). Skipped iterations write the empty string.
  - One specialist kind per code block. Loop with enumerate(top) inside
    the block to call that specialist for every candidate.
  - Every code block must contain at least one print() — the
    supervisor's code extractor requires it.
  - Never write three-backticks-in-a-row inside any code block. The
    extractor mis-truncates and your block is silently dropped.
  - Run ALL FIVE sweeps before calling the writer. Do not call the
    writer twice. Do not skip phase 3.
  - Reference only variables that have already been created in a
    prior code block.
  - If a specialist errors (timeout, exception), set enrichments[i][<key>]
    to the empty string and continue. Do not abort the cascade.
  - If `top` is empty (scout returned no candidates), skip phase 2 and
    call phase 3 with enriched_list = [].

OPTIONAL PHASE 4 — schedule a watch. Only if the user explicitly asks for
recurring monitoring (e.g. "watch weekly", "re-run every 5 minutes",
"keep checking", "rerun this each Monday"), after phase 3 returns:
  - In a SEPARATE code block, call the loops tool directly. It is
    available to you as `schedule_recurring`:
        loop_id = await schedule_recurring(
            cadence="<the cadence the user named>",
            prompt=user_question + " (diff against last run)",
        )
        print(loop_id)
    Cadence accepts: intervals like "5m"/"2h"/"1d", raw cron
    "0 9 * * *", or shorthand like "daily", "weekly", "every weekday".
  - Mention the scheduled loop id in your final reply on its own line:
    "Watch scheduled: <loop_id>."
  - Do NOT schedule unless the user asked for it. One-off lead-hunts
    are the default.

=== USER REQUEST ===
"""


async def _attach_policies(supervisor) -> None:
    """Wire CUGA policies onto the supervisor's specialists.

    The policy store is shared across all CugaAgent instances in this
    process (one sqlite-vec DB), so we add each policy ONCE on a
    representative agent and let the runtime trigger filters
    (target_tools, AlwaysTrigger on agent response) scope enforcement at
    call time:

      - intent_guard `ouroboros_abuse_guard` — keyword-triggered; fires
        whenever any specialist's input contains harassment / doxxing
        intent. Added once on the writer; visible to all.
      - tool_guide `prefer_independents` — `target_tools=
        ["find_local_businesses"]` scopes it to the scout's tool.
      - output_formatter `leads_board_formatter` — fires on
        agent_response with keywords {"leads", "lead board"} so it
        matches only the writer's final synthesis, not specialists' raw
        returns.

    `reset_policy_storage=True` on the *first* agent built clears the
    shared DB so re-runs don't accumulate duplicates.
    """
    agents = getattr(supervisor, "_agents", {}) or {}
    if not agents:
        log.warning("no agents on supervisor; skipping policy attach")
        return

    writer = agents.get("pitch_email_writer")
    scout  = agents.get("scout")
    primary = writer or next(iter(agents.values()))

    # Reset shared storage so a process restart doesn't accumulate
    # duplicates of the same policy. Note: the policy DB lives at
    # <cuga_sdk_path>/dbs/cuga.db (NOT inside the app), so without this
    # clear, every restart leaves stale policies behind.
    try:
        ok = await primary.policies.clear()
        log.info("policy store cleared: %s", ok)
    except Exception as exc:
        log.debug("policy store clear skipped: %s", exc)

    # 1. Intent guard — wide-scope refusal.
    try:
        await primary.policies.add_intent_guard(
            name="ouroboros_abuse_guard",
            keywords=["harass", "dox", "stalk", "scrape personal",
                       "find someone's home address", "track down"],
            response=(
                "I can help with finding businesses that would benefit "
                "from a CUGA agent — not with locating individuals or "
                "personal information. Try rephrasing in terms of a "
                "business or a neighborhood."
            ),
        )
    except Exception as exc:
        log.warning("intent_guard skipped: %s", exc)

    # 2. Tool guide — only the find_local_businesses tool gets enriched.
    if scout is not None:
        try:
            await scout.policies.add_tool_guide(
                name="prefer_independents",
                content=(
                    "When you see global chains in the result list "
                    "(Starbucks, McDonald's, Hilton, Subway, KFC, etc.), "
                    "drop them from your shortlist. Independent 1–5 "
                    "location businesses are the target."
                ),
                target_tools=["find_local_businesses"],
            )
        except Exception as exc:
            log.warning("tool_guide skipped: %s", exc)

    # 3. Output formatter — keyword-trigger on the writer's response so
    #    it only fires when the writer's prose mentions "leads".
    if writer is not None:
        try:
            await writer.policies.add_output_formatter(
                name="leads_board_formatter",
                format_config=(
                    "Always emit a fenced ```json``` block containing the "
                    "leads schema documented in your SKILL.md, followed "
                    "by a 2-paragraph prose summary that names the top 3 "
                    "leads and their angle, ending with one line of next "
                    "steps."
                ),
                format_type="markdown",
                keywords=["leads", "lead board", "shortlist", "ranked"],
            )
        except Exception as exc:
            log.warning("output_formatter skipped: %s", exc)


def make_supervisor():
    from cuga.sdk import CugaSupervisor
    from _llm import create_llm
    from specialists import make_all

    # AGENT_SETTING_CONFIG is set at module top (before cuga import).
    model = create_llm(
        provider=os.getenv("LLM_PROVIDER"),
        model=os.getenv("LLM_MODEL"),
    )

    agents = make_all(model=model)
    supervisor = CugaSupervisor(
        agents=agents,
        model=model,
        # description= is dead in this SDK branch (never rendered into
        # the supervisor's prompt). We inject the cascade rules via
        # _TASK_PRELUDE on the user message in /ask instead.
        # Step accounting (each block = 2 steps: model + execute):
        #   phase 1 (scout+parse+init):  2
        #   phase 2 (5 specialists × up to 3 candidates, often <15
        #             due to website conditionals): 20–30
        #   phase 3 (writer):            2
        #   misc planner indecision/retries: 5–15
        # 100 caps comfortably over the median 35–50.
        cuga_lite_max_steps=100,
        # CUGA loops: lets the supervisor schedule itself to re-run a
        # query later (weekly diff for new businesses, daily refresh of
        # a hot lead, etc.) by calling schedule_recurring / schedule_wakeup
        # tools — auto-injected into every internal specialist.
        enable_loops=True,
        loops_agent_name="ouroboros_supervisor",
    )
    return supervisor


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

    # Mount CUGA loops UI + API (visible at /cuga/loops/). Optional — guarded
    # so an SDK without the loops module still boots ouroboros normally.
    try:
        from cuga.backend.loops.api import router as _loops_router
        from cuga.backend.loops.service import get_loops_service
        get_loops_service().set_app_name("ouroboros")
        app.include_router(_loops_router)
        log.info("mounted CUGA loops at /cuga/loops/")
    except Exception as _err:
        log.warning("CUGA loops not mounted: %s", _err)

    _supervisor = None
    _policies_attached = False
    _init_lock = asyncio.Lock()

    async def _get_supervisor():
        nonlocal _supervisor, _policies_attached
        async with _init_lock:
            if _supervisor is None:
                log.info("Initialising CugaSupervisor with 7 specialists…")
                _supervisor = make_supervisor()
                log.info("Supervisor ready; attaching policies…")
                try:
                    await _attach_policies(_supervisor)
                    _policies_attached = True
                except Exception as exc:
                    log.warning("policy attach partially failed: %s", exc)
                log.info("Specialists: %s",
                         list(getattr(_supervisor, "_agents", {}).keys()))
            return _supervisor

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(_HTML)

    async def _handle_full_turn(question: str, thread_id: str,
                                *, source: str = "user",
                                loop_id: str | None = None) -> dict:
        """Run one supervisor turn end-to-end and persist the run record.

        Shared between POST /ask (source='user') and the loops-service
        callback (source='loop'). Stamps `source` + `loop_id` into the
        saved run JSON so the UI can distinguish them.
        """
        session = _get_session(thread_id)
        _maybe_update_session(session, question)

        session_brief = _format_session_brief(session)
        augmented = (
            f"{_TASK_PRELUDE}"
            f"{question}\n\n"
            f"[session:{session_brief}] "
            f"[thread:{thread_id}]"
        )
        import time as _time
        started_at = datetime.now(timezone.utc)
        t0 = _time.monotonic()
        try:
            supervisor = await _get_supervisor()
            result = await supervisor.invoke(augmented, thread_id=thread_id)
            elapsed_ms = int((_time.monotonic() - t0) * 1000)
            log.info("[%s] supervisor.invoke (%s) completed in %s",
                     thread_id[:8], source, _format_elapsed(elapsed_ms))
            answer = (
                result.answer if hasattr(result, "answer") else str(result)
            )

            leads = _extract_leads_json(answer)
            if not leads:
                writer_raw = _writer_output_from_state(supervisor)
                if writer_raw:
                    log.info("[%s] supervisor paraphrased; recovered writer "
                             "output (%d chars)", thread_id[:8], len(writer_raw))
                    recovered = _extract_leads_json(writer_raw)
                    if recovered:
                        leads  = recovered
                        answer = writer_raw

            if leads:
                leads["_at"] = datetime.now(timezone.utc).isoformat()
                session["leads"] = leads
                if leads.get("location"):
                    session["target_location"] = leads["location"]
                session["history"].insert(0, leads)
                session["history"] = session["history"][:6]
                log.info("[%s] leads parsed: %d items in %s",
                         thread_id[:8],
                         len(leads.get("leads", []) or []),
                         leads.get("location", "?"))
            else:
                log.warning("[%s] no leads extracted (answer length: %d chars)",
                            thread_id[:8], len(answer or ""))

            _save_run(thread_id, question, answer, leads, supervisor,
                      started_at=started_at, elapsed_ms=elapsed_ms,
                      source=source, loop_id=loop_id)

            # Fire-and-forget email notification. Never blocks the response.
            asyncio.create_task(_maybe_send_email_for_run(
                thread_id, question, answer, leads,
                source, loop_id, _format_elapsed(elapsed_ms),
            ))

            return {
                "answer":        answer,
                "thread_id":     thread_id,
                "elapsed_ms":    elapsed_ms,
                "elapsed_human": _format_elapsed(elapsed_ms),
                "source":        source,
                "loop_id":       loop_id,
            }
        except Exception as exc:
            elapsed_ms = int((_time.monotonic() - t0) * 1000)
            log.exception("Supervisor invocation failed (%s) after %s",
                          source, _format_elapsed(elapsed_ms))
            return {
                "answer":        f"Error: {exc}",
                "thread_id":     thread_id,
                "elapsed_ms":    elapsed_ms,
                "elapsed_human": _format_elapsed(elapsed_ms),
                "source":        source,
                "loop_id":       loop_id,
                "_error":        True,
            }

    # Override the loops service callable so loop fires go through the
    # same _handle_full_turn path as user asks. They land in runs/<thread>/
    # alongside user runs, with source='loop' + loop_id so the UI can
    # tell them apart.
    try:
        from cuga.backend.loops.service import current_loop_id, get_loops_service
        async def _loop_invoke(prompt: str, thread_id: str) -> str:
            lid = current_loop_id.get()
            res = await _handle_full_turn(prompt, thread_id,
                                          source="loop", loop_id=lid)
            return res.get("answer") or ""
        get_loops_service().register_agent("ouroboros_supervisor", _loop_invoke)
        log.info("registered ouroboros_supervisor with loops service "
                 "(loop fires will be saved as runs with source='loop')")
    except Exception as _err:
        log.warning("could not override loops callback: %s", _err)

    @app.post("/ask")
    async def api_ask(req: AskReq):
        thread_id = req.thread_id or str(uuid.uuid4())
        result = await _handle_full_turn(req.question, thread_id, source="user")
        if result.pop("_error", False):
            return JSONResponse(status_code=500, content=result)
        return result

    @app.get("/session/{thread_id}")
    async def api_session(thread_id: str):
        return _get_session(thread_id)

    @app.get("/health")
    async def health():
        return {"ok": True}

    # ── Email panel ────────────────────────────────────────────────
    @app.get("/email/config")
    async def email_get():
        cfg = _email_load()
        # Mask the saved password before sending to client
        cfg_safe = dict(cfg)
        cfg_safe["smtp_password"] = "•••" if cfg.get("smtp_password") else ""
        eff = _smtp_settings()
        return {
            "config":   cfg_safe,
            "effective": {
                "host":         eff["host"],
                "port":         eff["port"],
                "username":     eff["username"],
                "from":         eff["from"],
                "has_password": bool(eff["password"]),
                "ready":        bool(eff["host"] and eff["port"] and
                                     eff["username"] and eff["password"] and eff["from"]),
            },
        }

    from pydantic import field_validator
    class _EmailCfgReq(BaseModel):
        recipient: str = ""
        min_leads: int = 0
        include_user: bool = True
        include_loop: bool = True
        # SMTP overrides — leave blank to use env vars
        smtp_host: str = ""
        smtp_port: int = 0
        smtp_username: str = ""
        smtp_password: str = ""    # empty means "no change"; "•••" sentinel preserved
        smtp_from: str = ""

        # Browsers (and our JS) may send "" for cleared number inputs.
        # Pydantic v2 rejects empty-string-as-int → 422. Coerce here so
        # callers don't need to remember.
        @field_validator("smtp_port", "min_leads", mode="before")
        @classmethod
        def _empty_int_to_zero(cls, v):
            if v == "" or v is None:
                return 0
            return v

    @app.post("/email/config")
    async def email_set(req: _EmailCfgReq):
        new_cfg = req.model_dump()
        existing = _email_load()
        # Preserve existing password if client sent placeholder (or blank)
        if not new_cfg.get("smtp_password") or new_cfg["smtp_password"] == "•••":
            new_cfg["smtp_password"] = existing.get("smtp_password", "")
        _email_save(new_cfg)
        log.info("email config saved: recipient=%s min_leads=%d user=%s loop=%s "
                 "smtp_overrides=%s",
                 new_cfg["recipient"], new_cfg["min_leads"],
                 new_cfg["include_user"], new_cfg["include_loop"],
                 bool(new_cfg["smtp_host"] or new_cfg["smtp_username"]))
        # Return masked
        out = dict(new_cfg); out["smtp_password"] = "•••" if new_cfg["smtp_password"] else ""
        return {"ok": True, "config": out}

    @app.post("/email/test")
    async def email_test(req: _EmailCfgReq):
        """Send a test email using the request body's settings.

        The body is REQUIRED (was previously Optional, which FastAPI handled
        unreliably — Pydantic-model body params with `Optional[...] = None`
        sometimes deserialize as None even when JSON is sent. Save endpoint
        worked because it used a required signature). UI always sends a body;
        keeping it required is correct and simpler."""
        saved = _email_load()
        env_pw = os.getenv("SMTP_PASSWORD", "")
        diag = {
            "body_password_chars": len(req.smtp_password or ""),
            "body_password_is_sentinel": req.smtp_password == "•••",
            "body_recipient":   req.recipient,
            "saved_password_chars": len(saved.get("smtp_password") or ""),
            "env_SMTP_PASSWORD_set":  bool(env_pw),
            "saved_recipient":  saved.get("recipient", ""),
        }
        log.info("email_test diag: %s", diag)

        # Resolve effective settings: body fields override saved file; saved
        # password is preserved when client sends blank or sentinel.
        recipient = (req.recipient or "").strip()
        password = req.smtp_password
        if not password or password == "•••":
            password = saved.get("smtp_password", "") or env_pw
        host = req.smtp_host or saved.get("smtp_host") or os.getenv("SMTP_HOST", "smtp.gmail.com")
        port = int(req.smtp_port or saved.get("smtp_port") or 0) or int(os.getenv("SMTP_PORT", "587"))
        username = req.smtp_username or saved.get("smtp_username") or os.getenv("SMTP_USERNAME", "")
        from_addr = req.smtp_from or saved.get("smtp_from") or os.getenv("FROM_EMAIL", username)

        # Validate, returning a precise message about WHAT is missing + diagnostics.
        missing = []
        if not recipient: missing.append("recipient")
        if not host:      missing.append("SMTP host")
        if not port:      missing.append("SMTP port")
        if not username:  missing.append("SMTP username")
        if not password:  missing.append("SMTP password")
        if not from_addr: missing.append("From address")
        if missing:
            err_msg = f"missing: {', '.join(missing)}."
            if "SMTP password" in missing:
                err_msg += (
                    f" (received {diag['body_password_chars']} chars from form, "
                    f"saved={diag['saved_password_chars']} chars, "
                    f"env_var_set={diag['env_SMTP_PASSWORD_set']})"
                )
            return JSONResponse(status_code=400, content={
                "ok": False,
                "error": err_msg,
                "diag": diag,
            })

        subject, body = _render_email_html(
            thread_id="test-thread",
            question="Test email — Ouroboros email panel",
            answer="(this is a test send; no supervisor was invoked)",
            leads={"location": "Pleasantville, NY",
                   "leads": [{"name": "Sample Restaurant",
                              "category": "italian",
                              "fit_score": 8,
                              "deep_dive": True,
                              "pitch": "Sample pitch text demonstrating the lead format. "
                                       "Replace this with a real run to see actual content."}]},
            source="user", loop_id=None, elapsed_human="0s",
        )
        ok, info = await asyncio.to_thread(
            _email_send_with_creds, recipient, subject, body,
            host, port, username, password, from_addr,
        )
        if not ok:
            return JSONResponse(status_code=500, content={"ok": False, "error": info})
        return {"ok": True, "info": info}

    @app.get("/runs")
    async def api_all_runs():
        """List every saved run across every thread on disk.

        Defensive fallback for the UI's past-runs drawer: even if the
        browser's localStorage thread_id was wiped, the user can still
        browse runs from prior sessions. Returns the same per-row
        summary shape as /runs/<thread_id>, plus a `thread_id` field on
        each row so the UI can scope-load that run.
        """
        if not _RUNS_DIR.exists():
            return {"runs": []}
        all_runs = []
        for thread_dir in sorted(_RUNS_DIR.iterdir()):
            if not thread_dir.is_dir():
                continue
            thread_id = thread_dir.name
            for f in sorted(thread_dir.glob("*.json")):
                entry = {
                    "file":      f.name,
                    "thread_id": thread_id,
                    "size":      f.stat().st_size,
                    "url":       f"/runs/{thread_id}/{f.name}",
                }
                try:
                    data = json.loads(f.read_text())
                    entry["question"]      = data.get("question")
                    entry["elapsed_human"] = data.get("elapsed_human")
                    entry["elapsed_ms"]    = data.get("elapsed_ms")
                    entry["leads_count"]   = data.get("leads_count")
                    trace = data.get("agent_trace") or {}
                    entry["agent_counts"]  = trace.get("counts") or {}
                    entry["total_calls"]   = trace.get("total_calls") or 0
                    entry["timestamp"]     = data.get("timestamp")
                    entry["source"]        = data.get("source") or "user"
                    entry["loop_id"]       = data.get("loop_id")
                except Exception:
                    pass
                all_runs.append(entry)
        # Newest first across all threads.
        all_runs.sort(key=lambda r: r.get("timestamp") or r["file"], reverse=True)
        return {"runs": all_runs}

    @app.get("/runs/{thread_id}")
    async def api_runs(thread_id: str):
        """List saved per-turn metadata for a thread, with a trace summary."""
        safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", thread_id)[:64]
        run_dir = _RUNS_DIR / safe
        if not run_dir.exists():
            return {"thread_id": thread_id, "runs": []}
        files = sorted(run_dir.glob("*.json"))
        runs = []
        for f in files:
            entry = {
                "file":  f.name,
                "size":  f.stat().st_size,
                "url":   f"/runs/{thread_id}/{f.name}",
            }
            # Cheap peek for a summary — load the file and pull a few
            # top-level fields. The full record is at the detail URL.
            try:
                data = json.loads(f.read_text())
                entry["question"]      = data.get("question")
                entry["elapsed_human"] = data.get("elapsed_human")
                entry["elapsed_ms"]    = data.get("elapsed_ms")
                entry["leads_count"]   = data.get("leads_count")
                trace = data.get("agent_trace") or {}
                entry["agent_counts"]  = trace.get("counts") or {}
                entry["total_calls"]   = trace.get("total_calls") or 0
                entry["timestamp"]     = data.get("timestamp")
                entry["source"]        = data.get("source") or "user"
                entry["loop_id"]       = data.get("loop_id")
            except Exception:
                pass
            runs.append(entry)
        return {"thread_id": thread_id, "runs": runs}

    @app.get("/runs/{thread_id}/{filename}")
    async def api_run_detail(thread_id: str, filename: str):
        """Return the saved metadata for one turn."""
        safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", thread_id)[:64]
        # filename arrives untrusted — reject anything that's not a
        # bare ts-stamped json file in the thread's own dir.
        if not re.fullmatch(r"\d{8}T\d{6}Z\.json", filename):
            return JSONResponse(status_code=400, content={"error": "bad filename"})
        path = _RUNS_DIR / safe / filename
        if not path.exists():
            return JSONResponse(status_code=404, content={"error": "not found"})
        try:
            return json.loads(path.read_text())
        except Exception as exc:
            return JSONResponse(status_code=500,
                                content={"error": f"read failed: {exc}"})

    @app.get("/specialists")
    async def specialists():
        sup = await _get_supervisor()
        agents = getattr(sup, "_agents", {}) or {}
        return {
            "count": len(agents),
            "specialists": [
                {"name": n, "description": getattr(a, "description", "")}
                for n, a in agents.items()
            ],
        }

    print(f"\n  Ouroboros (multi-agent)  →  http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ── CLI entry point ──────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Ouroboros — multi-agent CUGA lead generation",
    )
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
