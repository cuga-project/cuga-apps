"""
cuga-skills-ui — the simplest possible UX for trying a CUGA skill.

What it does:
  1. Scans ../cuga-skills/ for SKILL.md files (frontmatter `name` + `description`).
  2. Lets you "import" a skill — copies it into both:
        ./.cuga/skills/<name>/                    so cuga's loader registers it
        /tmp/cuga_workspace/skills/<name>/        so SKILL.md's run_command paths resolve
  3. Builds a `CugaAgent(cuga_folder=…)` in-process. The host provides a
     native `run_command` tool that subprocesses on the local machine, so the
     agent invokes the skill's `scripts/*.py` exactly the way an OpenSandbox
     host would — same SKILL.md, same answer.

This host emulates the OpenSandbox sandbox in-process: faster, no Docker, but
also no isolation. Don't expose this to untrusted skills or networks.

Run:
    pip install -r requirements.txt
    pip install -e /path/to/cuga-agent-skills-branch   # exposes `from cuga import CugaAgent`
    export ANTHROPIC_API_KEY=...                        # or RITS_API_KEY, OPENAI_API_KEY, …
    python main.py
    python main.py --port 28910 --provider anthropic

Env:
    LLM_PROVIDER  rits | anthropic | openai | ollama | watsonx | litellm
    LLM_MODEL     model override
    SKILLS_DIR    directory to scan for skills (default: ../cuga-skills)
"""
from __future__ import annotations

# Set Dynaconf env BEFORE importing cuga so settings load with skills on
# and OpenSandbox shell tools off (we provide our own host-side run_command).
import os
os.environ.setdefault("DYNACONF_SKILLS__ENABLED", "true")
os.environ.setdefault("DYNACONF_ADVANCED_FEATURES__OPENSANDBOX_SANDBOX", "false")
os.environ.setdefault("DYNACONF_ADVANCED_FEATURES__ENABLE_SHELL_TOOL", "false")

import argparse
import logging
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Reuse the existing multi-provider LLM factory from cuga-apps.
_HERE = Path(__file__).parent.resolve()
_CUGA_APPS = _HERE.parent / "cuga-apps" / "apps"
if str(_CUGA_APPS) not in sys.path:
    sys.path.insert(0, str(_CUGA_APPS))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Skill discovery (lightweight — independent of cuga's loader)
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body). Tolerant of missing PyYAML."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    raw, body = m.group(1), m.group(2)
    try:
        import yaml  # type: ignore
        return yaml.safe_load(raw) or {}, body
    except ImportError:
        out: dict = {}
        for line in raw.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                out[k.strip()] = v.strip().strip('"').strip("'")
        return out, body


def discover_skill_dirs(skills_root: Path) -> list[dict]:
    """Find every SKILL.md under skills_root → [{name, description, dir, source}]."""
    out: list[dict] = []
    if not skills_root.is_dir():
        return out
    for skill_md in sorted(skills_root.rglob("SKILL.md")):
        try:
            fm, _body = _parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("Failed to parse %s: %s", skill_md, e)
            continue
        out.append({
            "name": (fm.get("name") or skill_md.parent.name).strip(),
            "description": (fm.get("description") or "").strip(),
            "dir": str(skill_md.parent),
            "source": str(skill_md),
        })
    return out


# ---------------------------------------------------------------------------
# Two install targets:
#   - <runtime>/.cuga/skills/<name>/            for cuga's discover_skills
#   - /tmp/cuga_workspace/skills/<name>/        for SKILL.md's run_command paths
# Mirrors what OpenSandbox does, so the same SKILL.md works in both hosts.
# ---------------------------------------------------------------------------

_RUNTIME_CUGA = _HERE / ".cuga"
_RUNTIME_SKILLS = _RUNTIME_CUGA / "skills"
_SANDBOX_DIR = Path("/tmp/cuga_workspace")
_SANDBOX_SKILLS = _SANDBOX_DIR / "skills"


def import_skill(skill: dict) -> dict:
    """Copy a skill folder into both install targets. Returns {cuga_dst, sandbox_dst}."""
    src = Path(skill["dir"])
    out: dict[str, str] = {}
    for target_root, key in (
        (_RUNTIME_SKILLS, "cuga_dst"),
        (_SANDBOX_SKILLS, "sandbox_dst"),
    ):
        dst = target_root / skill["name"]
        if dst.exists():
            shutil.rmtree(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)
        out[key] = str(dst)
    log.info("Imported skill %r → %s + %s", skill["name"], out["cuga_dst"], out["sandbox_dst"])
    return out


def uninstall_skill(name: str) -> bool:
    removed_any = False
    for target_root in (_RUNTIME_SKILLS, _SANDBOX_SKILLS):
        dst = target_root / name
        if dst.exists():
            shutil.rmtree(dst)
            removed_any = True
    if removed_any:
        log.info("Uninstalled skill %r from both targets", name)
    return removed_any


def list_imported() -> list[str]:
    if not _RUNTIME_SKILLS.is_dir():
        return []
    return sorted(p.name for p in _RUNTIME_SKILLS.iterdir() if (p / "SKILL.md").is_file())


# ---------------------------------------------------------------------------
# Host-side `run_command` — the agent's only tool besides load_skill.
# ---------------------------------------------------------------------------

def _make_run_command_tool():
    """Return an @tool wrapper around subprocess.run, scoped to /tmp/cuga_workspace."""
    from langchain_core.tools import tool

    @tool
    def run_command(cmd: str) -> str:
        """Run a shell command in the workspace and return its combined output.

        Args:
            cmd: a shell command line, e.g.
                 "python /tmp/cuga_workspace/skills/<skill>/scripts/<file>.py <args>"

        Returns stdout, with any stderr appended after a separator on non-zero exit.
        Errors that prevent the subprocess from running are returned as
        '[error] <type>: <msg>'. The agent should treat the return value as
        text to parse — JSON helpers should `json.loads(...)` it.
        """
        _SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
        try:
            argv = shlex.split(cmd)
            if not argv:
                return "[error] empty command"
            # Map `python` / `python3` to the running interpreter so the host
            # uses the venv that has cuga + the skill's pip deps installed.
            # OpenSandbox does the equivalent inside its container.
            if argv[0] in ("python", "python3"):
                argv[0] = sys.executable
            result = subprocess.run(
                argv,
                cwd=str(_SANDBOX_DIR),
                capture_output=True, text=True, timeout=120,
            )
            out = result.stdout or ""
            if result.returncode != 0:
                out += f"\n[stderr]\n{result.stderr or ''}\n[exit {result.returncode}]"
            return out
        except subprocess.TimeoutExpired:
            return "[error] command timed out after 120s"
        except FileNotFoundError as e:
            return f"[error] FileNotFoundError: {e}"
        except Exception as e:
            return f"[error] {type(e).__name__}: {e}"

    return run_command


# ---------------------------------------------------------------------------
# Lazy CugaAgent — built on first /ask, after at least one skill is imported.
# ---------------------------------------------------------------------------

_agent = None
_agent_skill_signature: tuple[str, ...] = ()


def _build_agent():
    """Construct a CugaAgent pointed at the runtime cuga_folder, plus run_command."""
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
        tools=[_make_run_command_tool()],
        cuga_folder=str(_RUNTIME_CUGA),
    )


def get_agent():
    """Build (or rebuild) the agent if the imported skill set has changed."""
    global _agent, _agent_skill_signature
    sig = tuple(list_imported())
    if not sig:
        raise HTTPException(400, "No skills imported yet — pick one and click Import first.")
    if _agent is None or sig != _agent_skill_signature:
        _agent = _build_agent()
        _agent_skill_signature = sig
        log.info("Built CugaAgent with skills: %s", sig)
    return _agent


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

class AskReq(BaseModel):
    question: str


class NameReq(BaseModel):
    name: str


def make_app(skills_root: Path) -> FastAPI:
    app = FastAPI(title="cuga-skills UI")
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    @app.get("/skills")
    async def api_skills():
        available = discover_skill_dirs(skills_root)
        imported = set(list_imported())
        for s in available:
            s["installed"] = s["name"] in imported
            scripts_dir = Path(s["dir"]) / "scripts"
            s["has_scripts"] = scripts_dir.is_dir()
            s["script_count"] = (
                sum(1 for _ in scripts_dir.glob("*.py")) if scripts_dir.is_dir() else 0
            )
        return {
            "available": available,
            "skills_root": str(skills_root),
            "runtime_cuga_folder": str(_RUNTIME_CUGA),
            "sandbox_dir": str(_SANDBOX_DIR),
        }

    @app.get("/skill/{name}")
    async def api_skill_detail(name: str):
        avail = {s["name"]: s for s in discover_skill_dirs(skills_root)}
        if name not in avail:
            raise HTTPException(404, f"Unknown skill: {name!r}")
        s = avail[name]
        md_path = Path(s["dir"]) / "SKILL.md"
        content = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
        scripts_dir = Path(s["dir"]) / "scripts"
        scripts = (
            sorted(p.name for p in scripts_dir.glob("*.py"))
            if scripts_dir.is_dir() else []
        )
        return {
            **s,
            "content": content,
            "scripts": scripts,
            "installed": name in set(list_imported()),
        }

    @app.post("/import")
    async def api_import(req: NameReq):
        avail = {s["name"]: s for s in discover_skill_dirs(skills_root)}
        if req.name not in avail:
            raise HTTPException(404, f"Unknown skill: {req.name!r}")
        targets = import_skill(avail[req.name])
        global _agent
        _agent = None  # rebuild on next /ask
        return {"ok": True, "name": req.name, **targets}

    @app.post("/uninstall")
    async def api_uninstall(req: NameReq):
        if not uninstall_skill(req.name):
            raise HTTPException(404, f"Skill not installed: {req.name!r}")
        global _agent
        _agent = None
        return {"ok": True, "name": req.name}

    @app.post("/ask")
    async def api_ask(req: AskReq):
        try:
            agent = get_agent()
        except HTTPException:
            raise
        except ModuleNotFoundError as exc:
            return JSONResponse({
                "error": (
                    f"{exc}. Install cuga in this venv: "
                    "`pip install -e /path/to/cuga-agent-skills-branch` "
                    "(or run from a venv where it's already installed)."
                )
            }, status_code=500)
        try:
            result = await agent.invoke(req.question, thread_id="ui")
            return {"answer": result.answer}
        except Exception as exc:
            log.exception("Agent error")
            return JSONResponse({"error": str(exc)}, status_code=500)

    @app.get("/", response_class=HTMLResponse)
    async def root():
        return HTMLResponse(_HTML)

    return app


# ---------------------------------------------------------------------------
# Single-page HTML (vanilla JS, no build step)
# ---------------------------------------------------------------------------

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CUGA Skills — Marketplace</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
  /* ─── Carbon Design System (g100 dark theme) tokens ─────────────────── */
  :root{
    --bg:#000000;
    --layer-00:#000000;
    --layer-01:#161616;
    --layer-02:#262626;
    --layer-03:#393939;
    --layer-hover:#2c2c2c;
    --field-01:#262626;
    --border-subtle-00:#262626;
    --border-subtle-01:#393939;
    --border-strong:#6f6f6f;
    --text-primary:#f4f4f4;
    --text-secondary:#c6c6c6;
    --text-helper:#a8a8a8;
    --text-placeholder:#6f6f6f;
    --text-on-color:#ffffff;
    --interactive:#0f62fe;
    --interactive-hover:#0353e9;
    --interactive-active:#002d9c;
    --link-primary:#78a9ff;
    --focus:#ffffff;
    --support-success:#42be65;
    --support-warning:#f1c21b;
    --support-error:#fa4d56;
    --support-info:#4589ff;
    --accent-magenta:#ee5396;
    --accent-purple:#a56eff;
    --accent-cyan:#33b1ff;
    --accent-teal:#08bdba;
    --motion:cubic-bezier(0.2, 0, 0.38, 0.9);
    --motion-fast:cubic-bezier(0.2, 0, 1, 0.9);
  }

  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  html,body{height:100%}
  body{
    font-family:'IBM Plex Sans','Helvetica Neue',Arial,sans-serif;
    background:var(--bg);
    color:var(--text-primary);
    -webkit-font-smoothing:antialiased;
    -moz-osx-font-smoothing:grayscale;
    overflow-x:hidden;
    line-height:1.4;
  }
  ::selection{background:var(--interactive);color:#fff}

  /* ─── Aurora hero glow ─────────────────────────────────────────────── */
  .aurora{
    position:fixed;inset:0;pointer-events:none;z-index:0;overflow:hidden;
  }
  .aurora::before,.aurora::after{
    content:"";position:absolute;border-radius:50%;filter:blur(120px);
    opacity:0.55;mix-blend-mode:screen;
    animation:drift 22s ease-in-out infinite;
  }
  .aurora::before{
    width:60vw;height:60vw;left:-10vw;top:-20vw;
    background:radial-gradient(circle,#0f62fe 0%,#002d9c 35%,transparent 70%);
  }
  .aurora::after{
    width:45vw;height:45vw;right:-10vw;top:-10vw;
    background:radial-gradient(circle,#a56eff 0%,#ee5396 40%,transparent 70%);
    animation-delay:-8s;animation-duration:28s;
  }
  @keyframes drift{
    0%,100%{transform:translate(0,0) scale(1)}
    33%{transform:translate(40px,30px) scale(1.05)}
    66%{transform:translate(-30px,20px) scale(0.97)}
  }

  /* Subtle grid overlay across everything */
  .grid-overlay{
    position:fixed;inset:0;pointer-events:none;z-index:1;
    background-image:
      linear-gradient(to right,rgba(255,255,255,0.025) 1px,transparent 1px),
      linear-gradient(to bottom,rgba(255,255,255,0.025) 1px,transparent 1px);
    background-size:64px 64px;
    mask-image:linear-gradient(to bottom,#000 0%,#000 40%,transparent 90%);
    -webkit-mask-image:linear-gradient(to bottom,#000 0%,#000 40%,transparent 90%);
  }

  /* ─── Top bar ──────────────────────────────────────────────────────── */
  .topbar{
    position:sticky;top:0;z-index:30;
    background:rgba(0,0,0,0.72);
    backdrop-filter:blur(14px) saturate(160%);
    -webkit-backdrop-filter:blur(14px) saturate(160%);
    border-bottom:1px solid var(--border-subtle-01);
    padding:0 24px;height:48px;
    display:flex;align-items:center;gap:16px;
  }
  .brand{display:flex;align-items:center;gap:10px;font-weight:600;font-size:14px;letter-spacing:-0.005em}
  .brand-mark{
    width:22px;height:22px;border-radius:5px;
    background:linear-gradient(135deg,var(--interactive) 0%,var(--accent-purple) 100%);
    display:grid;place-items:center;font-family:'IBM Plex Mono',monospace;
    font-weight:600;font-size:11px;color:#fff;
    box-shadow:0 0 24px rgba(15,98,254,0.45);
  }
  .brand-mark::after{content:"C"}
  .brand .product{color:var(--text-secondary);font-weight:400}
  .brand .sep{color:var(--border-strong);font-weight:300}
  .brand .marketplace{
    background:linear-gradient(90deg,#78a9ff,#a56eff);
    -webkit-background-clip:text;background-clip:text;color:transparent;
    font-weight:600;
  }
  .topbar-search{flex:1;max-width:520px;margin:0 auto;position:relative}
  .topbar-search input{
    width:100%;height:32px;padding:0 36px 0 36px;
    background:var(--field-01);border:1px solid transparent;
    color:var(--text-primary);font-size:13px;
    border-radius:0;outline:none;
    transition:border-color 0.15s var(--motion);
  }
  .topbar-search input::placeholder{color:var(--text-placeholder)}
  .topbar-search input:focus{
    outline:2px solid var(--focus);outline-offset:-2px;
  }
  .topbar-search .icon{
    position:absolute;left:10px;top:50%;transform:translateY(-50%);
    color:var(--text-helper);width:16px;height:16px;
  }
  .topbar-search kbd{
    position:absolute;right:8px;top:50%;transform:translateY(-50%);
    font-family:'IBM Plex Mono',monospace;font-size:10px;
    color:var(--text-helper);background:var(--layer-02);
    padding:2px 6px;border-radius:2px;border:1px solid var(--border-subtle-01);
  }
  .topbar-actions{display:flex;align-items:center;gap:4px}
  .icon-btn{
    width:32px;height:32px;display:grid;place-items:center;cursor:pointer;
    color:var(--text-secondary);background:transparent;border:none;
    transition:background 0.12s var(--motion);
  }
  .icon-btn:hover{background:var(--layer-hover);color:var(--text-primary)}
  .icon-btn svg{width:16px;height:16px}

  /* ─── Hero ─────────────────────────────────────────────────────────── */
  main{position:relative;z-index:2}
  .hero{
    padding:88px 24px 48px;max-width:1280px;margin:0 auto;position:relative;
  }
  .eyebrow{
    display:inline-flex;align-items:center;gap:8px;
    font-family:'IBM Plex Mono',monospace;font-size:11px;
    text-transform:uppercase;letter-spacing:0.08em;
    color:var(--text-helper);
    padding:5px 10px;border:1px solid var(--border-subtle-01);
    background:rgba(22,22,22,0.6);
    border-radius:999px;margin-bottom:20px;
  }
  .eyebrow .pulse{
    width:6px;height:6px;border-radius:50%;background:var(--support-success);
    box-shadow:0 0 0 0 rgba(66,190,101,0.7);
    animation:pulse 1.8s infinite;
  }
  @keyframes pulse{
    0%{box-shadow:0 0 0 0 rgba(66,190,101,0.7)}
    70%{box-shadow:0 0 0 8px rgba(66,190,101,0)}
    100%{box-shadow:0 0 0 0 rgba(66,190,101,0)}
  }
  .hero h1{
    font-family:'IBM Plex Sans',sans-serif;
    font-size:clamp(40px,6vw,72px);font-weight:300;
    line-height:1.05;letter-spacing:-0.02em;
    color:var(--text-primary);
    margin-bottom:16px;
  }
  .hero h1 .accent{
    background:linear-gradient(90deg,#78a9ff 0%,#a56eff 50%,#ee5396 100%);
    -webkit-background-clip:text;background-clip:text;color:transparent;
    font-weight:600;
  }
  .hero p{
    font-size:18px;line-height:1.55;max-width:640px;
    color:var(--text-secondary);margin-bottom:36px;font-weight:300;
  }
  .hero-stats{display:flex;gap:0;border-top:1px solid var(--border-subtle-01);
    border-bottom:1px solid var(--border-subtle-01);max-width:780px}
  .stat{
    flex:1;padding:20px 24px 20px 0;
    border-right:1px solid var(--border-subtle-01);
  }
  .stat:last-child{border-right:none}
  .stat .label{
    font-family:'IBM Plex Mono',monospace;font-size:11px;
    text-transform:uppercase;letter-spacing:0.06em;
    color:var(--text-helper);margin-bottom:6px;
  }
  .stat .value{
    font-size:32px;font-weight:300;letter-spacing:-0.01em;
    color:var(--text-primary);font-variant-numeric:tabular-nums;
  }
  .stat .value .unit{font-size:14px;color:var(--text-helper);margin-left:6px;font-weight:400}

  /* ─── Section header ──────────────────────────────────────────────── */
  .section{max-width:1280px;margin:0 auto;padding:0 24px 32px;position:relative}
  .section-head{
    display:flex;align-items:flex-end;justify-content:space-between;
    padding:48px 0 24px;border-bottom:1px solid var(--border-subtle-01);
    margin-bottom:24px;
  }
  .section-head h2{
    font-size:28px;font-weight:300;letter-spacing:-0.01em;
  }
  .section-head .sub{
    font-size:13px;color:var(--text-helper);margin-top:6px;
  }
  .filters{display:flex;gap:0;align-items:center}
  .pill{
    padding:6px 14px;font-size:12px;font-weight:500;
    background:transparent;border:1px solid var(--border-subtle-01);
    color:var(--text-secondary);cursor:pointer;
    border-right:none;
    transition:background 0.12s var(--motion),color 0.12s var(--motion);
    font-family:'IBM Plex Sans',sans-serif;
  }
  .pill:first-child{border-radius:0}
  .pill:last-child{border-right:1px solid var(--border-subtle-01)}
  .pill:hover{background:var(--layer-hover);color:var(--text-primary)}
  .pill.on{
    background:var(--text-primary);color:#000;
    border-color:var(--text-primary);
  }
  .pill .n{
    margin-left:6px;font-family:'IBM Plex Mono',monospace;
    opacity:0.7;font-size:11px;
  }

  /* ─── Skill grid ──────────────────────────────────────────────────── */
  .grid{
    display:grid;
    grid-template-columns:repeat(auto-fill,minmax(340px,1fr));
    gap:1px;background:var(--border-subtle-01);
    border:1px solid var(--border-subtle-01);
  }
  .card{
    background:var(--layer-01);
    padding:24px;cursor:pointer;
    position:relative;display:flex;flex-direction:column;
    min-height:220px;
    transition:background 0.16s var(--motion);
    overflow:hidden;
  }
  .card::before{
    content:"";position:absolute;left:0;right:0;top:0;height:3px;
    background:var(--card-accent,linear-gradient(90deg,var(--interactive),var(--accent-purple)));
    opacity:0;transform:translateY(-3px);
    transition:opacity 0.16s var(--motion),transform 0.16s var(--motion);
  }
  .card:hover{background:var(--layer-02)}
  .card:hover::before{opacity:1;transform:translateY(0)}
  .card-head{display:flex;align-items:flex-start;gap:14px;margin-bottom:14px}
  .card-icon{
    width:40px;height:40px;border-radius:0;
    background:var(--card-accent,linear-gradient(135deg,var(--interactive),var(--accent-purple)));
    display:grid;place-items:center;flex-shrink:0;
    font-family:'IBM Plex Mono',monospace;font-weight:600;
    font-size:18px;color:#fff;letter-spacing:-0.02em;
    position:relative;
  }
  .card-icon::after{
    content:"";position:absolute;inset:0;
    background:linear-gradient(135deg,rgba(255,255,255,0.18),transparent 60%);
  }
  .card-title{flex:1;min-width:0}
  .card-name{
    font-size:16px;font-weight:600;color:var(--text-primary);
    margin-bottom:4px;letter-spacing:-0.005em;
    overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  }
  .card-slug{
    font-family:'IBM Plex Mono',monospace;font-size:11px;
    color:var(--text-helper);
  }
  .card-desc{
    font-size:13px;line-height:1.55;color:var(--text-secondary);
    flex:1;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;
    overflow:hidden;
  }
  .card-foot{
    display:flex;align-items:center;justify-content:space-between;
    margin-top:18px;padding-top:14px;
    border-top:1px solid var(--border-subtle-01);gap:8px;
  }
  .card-tags{display:flex;gap:6px;flex-wrap:wrap;flex:1;min-width:0}
  .tag{
    font-family:'IBM Plex Mono',monospace;font-size:10px;
    text-transform:uppercase;letter-spacing:0.04em;
    padding:3px 7px;border-radius:0;
    background:var(--layer-02);color:var(--text-helper);
  }
  .tag.installed{
    background:rgba(66,190,101,0.15);color:var(--support-success);
  }
  .tag.scripts{
    background:rgba(15,98,254,0.18);color:var(--link-primary);
  }
  .card-cta{
    font-family:'IBM Plex Sans',sans-serif;font-size:12px;
    color:var(--text-secondary);display:flex;align-items:center;gap:4px;
    flex-shrink:0;
  }
  .card-cta svg{width:12px;height:12px;transition:transform 0.16s var(--motion)}
  .card:hover .card-cta svg{transform:translateX(3px)}

  /* Skeleton loading state */
  .skeleton{
    background:var(--layer-01);min-height:220px;padding:24px;
    position:relative;overflow:hidden;
  }
  .skeleton::after{
    content:"";position:absolute;inset:0;
    background:linear-gradient(90deg,transparent,rgba(255,255,255,0.04),transparent);
    animation:shimmer 1.4s infinite;
  }
  @keyframes shimmer{
    0%{transform:translateX(-100%)}
    100%{transform:translateX(100%)}
  }

  /* Empty state */
  .empty{
    grid-column:1/-1;padding:64px 24px;text-align:center;
    color:var(--text-helper);
  }
  .empty svg{width:48px;height:48px;margin:0 auto 16px;opacity:0.4}
  .empty h3{font-size:18px;font-weight:400;color:var(--text-secondary);margin-bottom:6px}
  .empty p{font-size:13px;line-height:1.5}
  .empty code{
    font-family:'IBM Plex Mono',monospace;font-size:12px;
    background:var(--layer-01);padding:2px 6px;color:var(--text-secondary);
  }

  /* ─── Detail modal ─────────────────────────────────────────────────── */
  .modal-mask{
    position:fixed;inset:0;z-index:50;
    background:rgba(0,0,0,0.7);backdrop-filter:blur(8px);
    -webkit-backdrop-filter:blur(8px);
    display:none;align-items:flex-start;justify-content:center;
    padding:48px 24px;overflow-y:auto;
    animation:fade 0.18s var(--motion);
  }
  .modal-mask.open{display:flex}
  @keyframes fade{from{opacity:0}to{opacity:1}}
  .modal{
    background:var(--layer-01);
    border:1px solid var(--border-subtle-01);
    width:100%;max-width:880px;
    box-shadow:0 24px 80px rgba(0,0,0,0.5);
    animation:rise 0.22s var(--motion);
    position:relative;
  }
  @keyframes rise{
    from{opacity:0;transform:translateY(12px)}
    to{opacity:1;transform:translateY(0)}
  }
  .modal-head{
    padding:28px 32px 20px;
    border-bottom:1px solid var(--border-subtle-01);
    position:relative;
    background:var(--layer-01);
    position:sticky;top:0;z-index:2;
  }
  .modal-head::before{
    content:"";position:absolute;left:0;right:0;top:0;height:3px;
    background:var(--modal-accent,linear-gradient(90deg,var(--interactive),var(--accent-purple)));
  }
  .modal-close{
    position:absolute;top:16px;right:16px;
    width:32px;height:32px;background:transparent;border:none;cursor:pointer;
    color:var(--text-secondary);display:grid;place-items:center;
    transition:background 0.12s var(--motion);
  }
  .modal-close:hover{background:var(--layer-hover);color:var(--text-primary)}
  .modal-close svg{width:16px;height:16px}
  .modal-title{display:flex;align-items:center;gap:14px;margin-bottom:8px}
  .modal-title .card-icon{width:36px;height:36px;font-size:16px}
  .modal-title h2{
    font-size:24px;font-weight:500;letter-spacing:-0.01em;
  }
  .modal-slug{
    font-family:'IBM Plex Mono',monospace;font-size:12px;color:var(--text-helper);
  }
  .modal-desc{font-size:14px;color:var(--text-secondary);margin:14px 0 0;line-height:1.55;max-width:680px}
  .modal-meta{display:flex;gap:16px;margin-top:18px;flex-wrap:wrap}
  .modal-meta .m{
    display:flex;align-items:center;gap:6px;font-size:12px;
    color:var(--text-helper);font-family:'IBM Plex Mono',monospace;
  }
  .modal-meta .m svg{width:13px;height:13px;opacity:0.7}
  .modal-actions{
    display:flex;gap:1px;background:var(--border-subtle-01);
    border-top:1px solid var(--border-subtle-01);
    border-bottom:1px solid var(--border-subtle-01);
  }
  .btn{
    flex:1;padding:14px 16px;
    font-family:'IBM Plex Sans',sans-serif;font-size:14px;font-weight:400;
    background:var(--layer-01);color:var(--text-primary);
    border:none;cursor:pointer;text-align:left;
    display:flex;align-items:center;gap:10px;
    transition:background 0.12s var(--motion);
  }
  .btn:hover{background:var(--layer-02)}
  .btn:disabled{cursor:not-allowed;color:var(--text-placeholder)}
  .btn svg{width:14px;height:14px;flex-shrink:0}
  .btn.primary{background:var(--interactive);color:#fff}
  .btn.primary:hover{background:var(--interactive-hover)}
  .btn.danger{color:var(--support-error)}
  .btn .spinner{
    width:12px;height:12px;border:2px solid currentColor;
    border-right-color:transparent;border-radius:50%;
    animation:spin 0.8s linear infinite;
  }
  @keyframes spin{to{transform:rotate(360deg)}}

  .modal-body{padding:28px 32px 32px}
  .markdown{
    font-size:14px;line-height:1.7;color:var(--text-secondary);
  }
  .markdown h1,.markdown h2,.markdown h3{
    color:var(--text-primary);font-weight:500;
    margin:24px 0 12px;letter-spacing:-0.005em;line-height:1.3;
  }
  .markdown h1{font-size:22px;margin-top:0}
  .markdown h2{font-size:18px;padding-bottom:6px;border-bottom:1px solid var(--border-subtle-01)}
  .markdown h3{font-size:15px}
  .markdown p{margin-bottom:14px}
  .markdown ul,.markdown ol{margin-bottom:14px;padding-left:24px}
  .markdown li{margin-bottom:5px}
  .markdown code{
    font-family:'IBM Plex Mono',monospace;font-size:12.5px;
    background:var(--layer-02);padding:1px 6px;color:#a6c8ff;
    border-radius:0;
  }
  .markdown pre{
    background:var(--bg);padding:16px;
    border:1px solid var(--border-subtle-01);
    overflow-x:auto;margin:14px 0;font-size:12.5px;
    border-left:2px solid var(--interactive);
  }
  .markdown pre code{background:transparent;padding:0;color:var(--text-secondary)}
  .markdown a{color:var(--link-primary);text-decoration:none;border-bottom:1px solid transparent}
  .markdown a:hover{border-bottom-color:currentColor}
  .markdown table{
    width:100%;border-collapse:collapse;margin:14px 0;font-size:13px;
  }
  .markdown th,.markdown td{
    padding:8px 12px;text-align:left;
    border-bottom:1px solid var(--border-subtle-01);
  }
  .markdown th{
    background:var(--layer-02);color:var(--text-primary);
    font-weight:500;font-size:11px;text-transform:uppercase;
    letter-spacing:0.06em;
  }
  .markdown blockquote{
    border-left:2px solid var(--support-warning);
    padding:8px 14px;background:rgba(241,194,27,0.05);
    margin:14px 0;color:var(--text-secondary);
  }

  /* ─── Console panel (ask the agent) ───────────────────────────────── */
  .console{
    max-width:1280px;margin:0 auto;padding:48px 24px 96px;position:relative;
  }
  .console-shell{
    background:var(--layer-01);border:1px solid var(--border-subtle-01);
    overflow:hidden;
  }
  .console-head{
    display:flex;align-items:center;gap:10px;
    padding:10px 16px;
    border-bottom:1px solid var(--border-subtle-01);
    background:var(--layer-02);
    font-family:'IBM Plex Mono',monospace;font-size:11px;
    color:var(--text-helper);
  }
  .dot{width:10px;height:10px;border-radius:50%;background:var(--layer-03)}
  .dot.r{background:#fa4d56}
  .dot.y{background:#f1c21b}
  .dot.g{background:#42be65}
  .console-title{margin-left:8px;letter-spacing:0.04em;text-transform:uppercase}
  .console-tag{
    margin-left:auto;font-size:10px;
    color:var(--support-success);display:flex;align-items:center;gap:5px;
  }
  .console-tag .pulse{
    width:6px;height:6px;border-radius:50%;background:var(--support-success);
    box-shadow:0 0 6px var(--support-success);
  }
  .console-tag.off .pulse{background:var(--text-placeholder);box-shadow:none}
  .console-tag.off{color:var(--text-helper)}
  .console-body{padding:0}

  .active-skills{
    display:flex;align-items:center;gap:8px;flex-wrap:wrap;
    padding:14px 20px;border-bottom:1px solid var(--border-subtle-01);
    background:rgba(15,98,254,0.04);
  }
  .active-skills .label{
    font-family:'IBM Plex Mono',monospace;font-size:11px;
    color:var(--text-helper);text-transform:uppercase;letter-spacing:0.06em;
  }
  .chip{
    display:inline-flex;align-items:center;gap:6px;
    padding:4px 10px 4px 6px;font-size:12px;
    background:var(--layer-02);color:var(--text-primary);
    border:1px solid var(--border-subtle-01);
  }
  .chip-dot{
    width:14px;height:14px;border-radius:0;
    background:var(--card-accent,linear-gradient(135deg,var(--interactive),var(--accent-purple)));
    display:grid;place-items:center;font-family:'IBM Plex Mono',monospace;
    font-size:9px;font-weight:600;color:#fff;
  }
  .chip .x{
    width:14px;height:14px;display:grid;place-items:center;
    cursor:pointer;color:var(--text-helper);font-size:14px;line-height:1;
    margin-left:2px;
  }
  .chip .x:hover{color:var(--support-error)}
  .active-empty{
    font-family:'IBM Plex Mono',monospace;font-size:11px;
    color:var(--text-placeholder);
  }

  .ask-form{display:flex;flex-direction:column}
  .ask-input-row{
    display:flex;align-items:flex-start;
    border-bottom:1px solid var(--border-subtle-01);
  }
  .prompt-prefix{
    padding:18px 8px 18px 20px;
    font-family:'IBM Plex Mono',monospace;font-size:14px;
    color:var(--accent-cyan);user-select:none;
  }
  textarea#question{
    flex:1;padding:18px 20px 18px 0;
    background:transparent;border:none;outline:none;resize:none;
    color:var(--text-primary);font-size:15px;
    font-family:'IBM Plex Sans',sans-serif;line-height:1.5;
    min-height:60px;max-height:200px;
  }
  textarea#question::placeholder{color:var(--text-placeholder)}
  .ask-bar{
    display:flex;align-items:center;gap:12px;
    padding:12px 16px 12px 20px;
  }
  .ask-bar .examples{
    display:flex;gap:6px;flex-wrap:wrap;flex:1;
  }
  .ex{
    font-size:11px;font-family:'IBM Plex Mono',monospace;
    color:var(--text-helper);background:transparent;
    border:1px dashed var(--border-subtle-01);
    padding:4px 8px;cursor:pointer;
    transition:all 0.12s var(--motion);
  }
  .ex:hover{
    color:var(--text-primary);border-color:var(--border-strong);
    border-style:solid;
  }
  .ask-btn{
    padding:0 16px;height:36px;
    background:var(--interactive);border:none;color:#fff;
    font-family:'IBM Plex Sans',sans-serif;font-size:13px;font-weight:500;
    cursor:pointer;display:flex;align-items:center;gap:8px;
    transition:background 0.12s var(--motion);
  }
  .ask-btn:hover:not(:disabled){background:var(--interactive-hover)}
  .ask-btn:disabled{
    background:var(--layer-02);color:var(--text-placeholder);cursor:not-allowed;
  }
  .ask-btn svg{width:14px;height:14px}
  .ask-btn .spinner{
    width:12px;height:12px;border:2px solid currentColor;
    border-right-color:transparent;border-radius:50%;
    animation:spin 0.8s linear infinite;
  }
  .ask-btn kbd{
    margin-left:4px;font-size:10px;opacity:0.75;
    font-family:'IBM Plex Mono',monospace;
  }

  /* Answer area */
  .answer-wrap{display:none;border-top:1px solid var(--border-subtle-01)}
  .answer-wrap.vis{display:block}
  .answer-head{
    display:flex;align-items:center;gap:10px;
    padding:12px 20px;font-family:'IBM Plex Mono',monospace;
    font-size:11px;color:var(--text-helper);text-transform:uppercase;
    letter-spacing:0.06em;border-bottom:1px solid var(--border-subtle-01);
    background:var(--layer-02);
  }
  .answer-head .right{margin-left:auto;text-transform:none;letter-spacing:0;font-family:'IBM Plex Mono',monospace}
  .answer-body{
    padding:20px;font-size:14px;line-height:1.7;
    color:var(--text-primary);white-space:pre-wrap;word-wrap:break-word;
    max-height:600px;overflow-y:auto;
  }
  .answer-body.markdown{white-space:normal}
  .answer-body .err{color:var(--support-error)}
  .thinking{
    display:flex;align-items:center;gap:10px;
    color:var(--text-helper);font-size:13px;
  }
  .thinking .bar{
    width:3px;height:14px;background:var(--accent-cyan);
    animation:think 1s ease-in-out infinite;
  }
  .thinking .bar:nth-child(2){animation-delay:0.15s}
  .thinking .bar:nth-child(3){animation-delay:0.3s}
  @keyframes think{
    0%,100%{transform:scaleY(0.5);opacity:0.5}
    50%{transform:scaleY(1);opacity:1}
  }

  /* ─── Toasts ────────────────────────────────────────────────────────── */
  .toasts{
    position:fixed;bottom:24px;right:24px;z-index:60;
    display:flex;flex-direction:column;gap:8px;
  }
  .toast{
    background:var(--layer-02);
    border:1px solid var(--border-subtle-01);
    border-left:3px solid var(--support-success);
    padding:12px 16px;font-size:13px;color:var(--text-primary);
    min-width:280px;display:flex;align-items:center;gap:10px;
    animation:slide 0.18s var(--motion);
    box-shadow:0 8px 24px rgba(0,0,0,0.4);
  }
  .toast.err{border-left-color:var(--support-error)}
  .toast svg{width:16px;height:16px;flex-shrink:0;color:var(--support-success)}
  .toast.err svg{color:var(--support-error)}
  @keyframes slide{
    from{opacity:0;transform:translateX(20px)}
    to{opacity:1;transform:translateX(0)}
  }

  /* ─── Footer ───────────────────────────────────────────────────────── */
  footer{
    border-top:1px solid var(--border-subtle-01);
    padding:32px 24px;color:var(--text-helper);font-size:12px;
    font-family:'IBM Plex Mono',monospace;
    display:flex;justify-content:space-between;align-items:center;
    max-width:1280px;margin:0 auto;flex-wrap:wrap;gap:12px;
  }
  footer a{color:var(--link-primary);text-decoration:none}
  footer a:hover{text-decoration:underline}
  footer .paths{display:flex;gap:16px;flex-wrap:wrap}
  footer .paths span{color:var(--text-placeholder)}
  footer .paths code{color:var(--text-secondary)}

  /* ─── Responsive ──────────────────────────────────────────────────── */
  @media (max-width:720px){
    .topbar-search{display:none}
    .hero{padding:48px 20px 32px}
    .hero h1{font-size:40px}
    .hero p{font-size:15px}
    .stat .value{font-size:24px}
    .grid{grid-template-columns:1fr}
    .modal-head,.modal-body{padding:20px}
    .modal-actions{flex-wrap:wrap}
  }
</style>
</head>
<body>

<div class="aurora"></div>
<div class="grid-overlay"></div>

<header class="topbar">
  <div class="brand">
    <span class="brand-mark"></span>
    <span>CUGA</span>
    <span class="sep">/</span>
    <span class="marketplace">skills</span>
    <span class="product" style="font-size:11px;margin-left:4px;color:var(--text-placeholder);font-family:'IBM Plex Mono',monospace">v1.0</span>
  </div>
  <div class="topbar-search">
    <svg class="icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
      <circle cx="7" cy="7" r="5"/><path d="m11 11 3 3"/>
    </svg>
    <input id="search" placeholder="Search skills, capabilities, scripts…" autocomplete="off">
    <kbd>⌘K</kbd>
  </div>
  <div class="topbar-actions">
    <a class="icon-btn" href="https://github.com/" target="_blank" rel="noopener" title="Repo">
      <svg viewBox="0 0 16 16" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8a8 8 0 0 0 5.47 7.59c.4.07.55-.17.55-.38v-1.34c-2.22.48-2.69-1.07-2.69-1.07-.36-.92-.89-1.17-.89-1.17-.73-.5.05-.49.05-.49.81.06 1.23.83 1.23.83.72 1.22 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.13 0 0 .67-.21 2.2.82a7.5 7.5 0 0 1 4 0c1.53-1.03 2.2-.82 2.2-.82.44 1.11.16 1.93.08 2.13.51.56.82 1.28.82 2.15 0 3.07-1.86 3.75-3.65 3.95.29.25.54.74.54 1.49v2.21c0 .21.15.46.55.38A8 8 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>
    </a>
    <button class="icon-btn" onclick="loadSkills(true)" title="Refresh">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2v4h-4M2 14v-4h4"/><path d="M13 6a5.5 5.5 0 0 0-10-1M3 10a5.5 5.5 0 0 0 10 1"/></svg>
    </button>
  </div>
</header>

<main>
  <section class="hero">
    <div class="eyebrow">
      <span class="pulse"></span>
      <span>Live · in-process CUGA agent</span>
    </div>
    <h1>Skills <span class="accent">marketplace</span><br>for autonomous agents.</h1>
    <p>Browse a library of CUGA skills — drop-in capabilities with shipped scripts. Import to mount the skill into the agent's runtime, then ask in natural language. The agent picks up <code style="font-family:'IBM Plex Mono',monospace;font-size:14px;color:#a6c8ff;background:rgba(15,98,254,0.12);padding:1px 6px">load_skill</code> and runs.</p>
    <div class="hero-stats">
      <div class="stat">
        <div class="label">Available</div>
        <div class="value" id="stat-available">0</div>
      </div>
      <div class="stat">
        <div class="label">Installed</div>
        <div class="value" id="stat-installed">0<span class="unit">active</span></div>
      </div>
      <div class="stat">
        <div class="label">Scripts</div>
        <div class="value" id="stat-scripts">0<span class="unit">.py shipped</span></div>
      </div>
      <div class="stat">
        <div class="label">Runtime</div>
        <div class="value" id="stat-runtime" style="font-size:14px;line-height:1.4;font-family:'IBM Plex Mono',monospace;padding-top:8px">—</div>
      </div>
    </div>
  </section>

  <section class="section">
    <div class="section-head">
      <div>
        <h2>Browse skills</h2>
        <div class="sub" id="skills-sub">Scanning local library…</div>
      </div>
      <div class="filters">
        <button class="pill on" data-filter="all">All <span class="n" id="n-all">0</span></button>
        <button class="pill" data-filter="installed">Installed <span class="n" id="n-installed">0</span></button>
        <button class="pill" data-filter="scripts">With scripts <span class="n" id="n-scripts">0</span></button>
      </div>
    </div>
    <div class="grid" id="skill-grid">
      <div class="skeleton"></div><div class="skeleton"></div>
      <div class="skeleton"></div><div class="skeleton"></div>
    </div>
  </section>

  <section class="console">
    <div class="section-head" style="margin-bottom:0;padding-bottom:24px">
      <div>
        <h2>Try the agent</h2>
        <div class="sub">Active skills are passed to a <code style="font-family:'IBM Plex Mono',monospace">CugaAgent</code>; ask anything.</div>
      </div>
    </div>
    <div class="console-shell">
      <div class="console-head">
        <span class="dot r"></span><span class="dot y"></span><span class="dot g"></span>
        <span class="console-title">cuga-agent</span>
        <span class="console-tag off" id="agent-status">
          <span class="pulse"></span><span id="agent-status-text">no skills imported</span>
        </span>
      </div>
      <div class="active-skills" id="active-skills">
        <span class="label">Active:</span>
        <span class="active-empty">none — import a skill above</span>
      </div>
      <form class="ask-form" id="ask-form" onsubmit="event.preventDefault();ask()">
        <div class="ask-input-row">
          <span class="prompt-prefix">$</span>
          <textarea id="question" rows="2" placeholder="Ask the agent something — e.g. easy hikes near Yosemite, CA"></textarea>
        </div>
        <div class="ask-bar">
          <div class="examples" id="examples"></div>
          <button class="ask-btn" id="ask-btn" disabled type="submit">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="m2 8 12 0M9 3l5 5-5 5"/></svg>
            <span id="ask-btn-text">Ask</span>
            <kbd>⌘↵</kbd>
          </button>
        </div>
        <div class="answer-wrap" id="answer-wrap">
          <div class="answer-head">
            <span>response</span>
            <span class="right" id="answer-meta"></span>
          </div>
          <div class="answer-body" id="answer"></div>
        </div>
      </form>
    </div>
  </section>
</main>

<div class="modal-mask" id="modal" onclick="if(event.target===this)closeModal()">
  <div class="modal" id="modal-inner">
    <div class="modal-head">
      <button class="modal-close" onclick="closeModal()" aria-label="Close">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="m3 3 10 10M13 3 3 13"/></svg>
      </button>
      <div class="modal-title">
        <div class="card-icon" id="m-icon"></div>
        <div>
          <h2 id="m-name">…</h2>
          <div class="modal-slug" id="m-slug">…</div>
        </div>
      </div>
      <p class="modal-desc" id="m-desc">…</p>
      <div class="modal-meta" id="m-meta"></div>
    </div>
    <div class="modal-actions" id="m-actions"></div>
    <div class="modal-body">
      <div class="markdown" id="m-content">Loading…</div>
    </div>
  </div>
</div>

<div class="toasts" id="toasts"></div>

<footer>
  <div>
    <strong style="color:var(--text-secondary)">CUGA Skills Marketplace</strong>
    · in-process · no docker · no isolation
  </div>
  <div class="paths" id="paths"></div>
</footer>

<script>
/* ════════════════════════════════════════════════════════════════════
   State
   ════════════════════════════════════════════════════════════════════ */
const STATE = {
  available: [],
  skills_root: '',
  runtime_cuga_folder: '',
  sandbox_dir: '',
  filter: 'all',
  query: '',
  modalSkill: null,
};

/* Deterministic gradient per skill name — six tasteful Carbon-friendly pairs */
const PALETTES = [
  ['#0f62fe','#a56eff'],   // blue → purple
  ['#33b1ff','#08bdba'],   // cyan → teal
  ['#a56eff','#ee5396'],   // purple → magenta
  ['#ee5396','#ff832b'],   // magenta → orange
  ['#08bdba','#42be65'],   // teal → green
  ['#0f62fe','#33b1ff'],   // blue → cyan
  ['#ff832b','#f1c21b'],   // orange → yellow
  ['#a56eff','#0f62fe'],   // purple → blue
];
function paletteOf(name){
  let h = 0;
  for (const c of String(name||'')) h = (h*31 + c.charCodeAt(0)) >>> 0;
  return PALETTES[h % PALETTES.length];
}
function gradientOf(name){
  const [a,b] = paletteOf(name);
  return `linear-gradient(135deg,${a} 0%,${b} 100%)`;
}
function initials(name){
  const parts = String(name||'?').split(/[_\s\-]+/).filter(Boolean);
  if (!parts.length) return '?';
  if (parts.length === 1) return parts[0].slice(0,2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}
function prettify(name){
  return String(name||'').replace(/[_-]+/g,' ').replace(/\b\w/g,c=>c.toUpperCase());
}
function esc(s){
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

/* ════════════════════════════════════════════════════════════════════
   Loading & rendering
   ════════════════════════════════════════════════════════════════════ */
async function loadSkills(showToast){
  try {
    const r = await fetch('/skills');
    const data = await r.json();
    Object.assign(STATE, data);
    render();
    if (showToast) toast('Refreshed.', 'ok');
  } catch (e) {
    toast('Failed to load skills: ' + e.message, 'err');
  }
}

function filterSkills(){
  let list = STATE.available.slice();
  if (STATE.filter === 'installed') list = list.filter(s => s.installed);
  if (STATE.filter === 'scripts')   list = list.filter(s => s.has_scripts);
  const q = STATE.query.trim().toLowerCase();
  if (q) {
    list = list.filter(s =>
      (s.name||'').toLowerCase().includes(q) ||
      (s.description||'').toLowerCase().includes(q));
  }
  return list;
}

function render(){
  renderStats();
  renderGrid();
  renderActiveSkills();
  renderExamples();
  renderPaths();
  syncAskState();
}

function animateCount(el, target){
  const start = parseInt(el.dataset.v || '0', 10);
  const dur = 520;
  const t0 = performance.now();
  function step(now){
    const t = Math.min(1, (now - t0) / dur);
    const e = 1 - Math.pow(1 - t, 3);
    const v = Math.round(start + (target - start) * e);
    const unit = el.querySelector('.unit');
    el.textContent = v;
    if (unit) el.appendChild(unit);
    if (t < 1) requestAnimationFrame(step);
    else el.dataset.v = String(target);
  }
  requestAnimationFrame(step);
}

function renderStats(){
  const total = STATE.available.length;
  const installed = STATE.available.filter(s => s.installed).length;
  const scripts = STATE.available.reduce((n,s) => n + (s.script_count || 0), 0);
  animateCount(document.getElementById('stat-available'), total);
  animateCount(document.getElementById('stat-installed'), installed);
  animateCount(document.getElementById('stat-scripts'), scripts);

  const rt = document.getElementById('stat-runtime');
  const rel = (STATE.runtime_cuga_folder||'').split('/').slice(-2).join('/') || '—';
  rt.textContent = rel;

  document.getElementById('n-all').textContent = total;
  document.getElementById('n-installed').textContent = installed;
  document.getElementById('n-scripts').textContent = STATE.available.filter(s=>s.has_scripts).length;
  document.getElementById('skills-sub').textContent =
    `${total} discovered in ${STATE.skills_root || '—'}`;
}

function renderGrid(){
  const grid = document.getElementById('skill-grid');
  const list = filterSkills();

  if (!STATE.available.length){
    grid.innerHTML = `
      <div class="empty">
        <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="8" y="12" width="48" height="40" rx="2"/>
          <path d="M8 22h48M16 32h32M16 40h20"/>
        </svg>
        <h3>No skills found</h3>
        <p>Drop a folder with <code>SKILL.md</code> into <code>${esc(STATE.skills_root)}</code> and refresh.</p>
      </div>`;
    return;
  }
  if (!list.length){
    grid.innerHTML = `
      <div class="empty">
        <h3>Nothing matches</h3>
        <p>Try a different filter or clear the search.</p>
      </div>`;
    return;
  }

  grid.innerHTML = list.map(s => {
    const grad = gradientOf(s.name);
    const init = initials(s.name);
    const tags = [];
    if (s.installed)   tags.push(`<span class="tag installed">✓ installed</span>`);
    if (s.has_scripts) tags.push(`<span class="tag scripts">${s.script_count||1} script${(s.script_count||1)>1?'s':''}</span>`);
    return `
      <article class="card" data-name="${esc(s.name)}" style="--card-accent:${grad}" onclick="openModal('${esc(s.name)}')">
        <div class="card-head">
          <div class="card-icon" style="background:${grad}">${esc(init)}</div>
          <div class="card-title">
            <div class="card-name">${esc(prettify(s.name))}</div>
            <div class="card-slug">${esc(s.name)}</div>
          </div>
        </div>
        <p class="card-desc">${esc(s.description || 'No description provided.')}</p>
        <div class="card-foot">
          <div class="card-tags">${tags.join('')}</div>
          <div class="card-cta">
            details
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="m6 3 5 5-5 5"/></svg>
          </div>
        </div>
      </article>`;
  }).join('');
}

function renderActiveSkills(){
  const wrap = document.getElementById('active-skills');
  const installed = STATE.available.filter(s => s.installed);
  const tag = document.getElementById('agent-status');
  const txt = document.getElementById('agent-status-text');
  if (!installed.length){
    wrap.innerHTML = `<span class="label">Active:</span>
      <span class="active-empty">none — import a skill above</span>`;
    tag.classList.add('off');
    txt.textContent = 'no skills imported';
    return;
  }
  tag.classList.remove('off');
  txt.textContent = `agent ready · ${installed.length} skill${installed.length>1?'s':''}`;
  wrap.innerHTML = `<span class="label">Active:</span>` + installed.map(s => `
    <span class="chip" style="--card-accent:${gradientOf(s.name)}">
      <span class="chip-dot">${esc(initials(s.name))}</span>
      ${esc(s.name)}
      <span class="x" onclick="event.stopPropagation();doRemove('${esc(s.name)}')" title="Remove">×</span>
    </span>`).join('');
}

function renderExamples(){
  const installed = STATE.available.filter(s => s.installed);
  const ex = document.getElementById('examples');
  if (!installed.length){ ex.innerHTML=''; return; }
  // Pull a 4-word hint from each installed skill's description.
  const hints = installed.slice(0,3).map(s => {
    const seed = (s.description||'').replace(/[.,;:].*/,'').split(/\s+/).slice(0,8).join(' ');
    return seed || `try the ${s.name} skill`;
  });
  ex.innerHTML = hints.map(h =>
    `<button type="button" class="ex" onclick="setQuestion(${JSON.stringify(h).replace(/"/g,'&quot;')})">› ${esc(h)}</button>`
  ).join('');
}

function renderPaths(){
  const el = document.getElementById('paths');
  el.innerHTML = `
    <span>library: <code>${esc(STATE.skills_root||'—')}</code></span>
    <span>runtime: <code>${esc(STATE.runtime_cuga_folder||'—')}</code></span>
    <span>sandbox: <code>${esc(STATE.sandbox_dir||'—')}</code></span>
  `;
}

function syncAskState(){
  const anyInstalled = STATE.available.some(s => s.installed);
  document.getElementById('ask-btn').disabled = !anyInstalled;
}

function setQuestion(text){
  const ta = document.getElementById('question');
  ta.value = text;
  ta.focus();
  autoresize(ta);
}

/* ════════════════════════════════════════════════════════════════════
   Filters & search
   ════════════════════════════════════════════════════════════════════ */
document.querySelectorAll('.pill').forEach(p => {
  p.addEventListener('click', () => {
    document.querySelectorAll('.pill').forEach(x => x.classList.remove('on'));
    p.classList.add('on');
    STATE.filter = p.dataset.filter;
    renderGrid();
  });
});
document.getElementById('search').addEventListener('input', e => {
  STATE.query = e.target.value;
  renderGrid();
});

/* ⌘K / Ctrl+K → focus search; ⌘↵ → submit ask */
window.addEventListener('keydown', e => {
  const meta = e.metaKey || e.ctrlKey;
  if (meta && (e.key === 'k' || e.key === 'K')) {
    e.preventDefault();
    document.getElementById('search').focus();
  }
  if (meta && e.key === 'Enter') {
    e.preventDefault();
    if (!document.getElementById('ask-btn').disabled) ask();
  }
  if (e.key === 'Escape') closeModal();
});

/* ════════════════════════════════════════════════════════════════════
   Modal — skill detail with rendered SKILL.md
   ════════════════════════════════════════════════════════════════════ */
async function openModal(name){
  STATE.modalSkill = name;
  const m = document.getElementById('modal');
  const grad = gradientOf(name);
  const init = initials(name);
  m.classList.add('open');
  document.body.style.overflow = 'hidden';
  document.getElementById('modal-inner').style.setProperty('--modal-accent', grad);
  document.getElementById('m-icon').style.background = grad;
  document.getElementById('m-icon').textContent = init;
  document.getElementById('m-name').textContent = prettify(name);
  document.getElementById('m-slug').textContent = name;
  document.getElementById('m-desc').textContent = '';
  document.getElementById('m-meta').innerHTML = '';
  document.getElementById('m-content').textContent = 'Loading…';
  document.getElementById('m-actions').innerHTML = '';

  try {
    const r = await fetch(`/skill/${encodeURIComponent(name)}`);
    if (!r.ok) throw new Error(`Skill detail: ${r.status}`);
    const d = await r.json();
    document.getElementById('m-desc').textContent = d.description || '—';
    document.getElementById('m-meta').innerHTML = [
      iconMeta('directory', d.dir),
      d.scripts.length ? iconMeta('scripts', d.scripts.join(' · ')) : '',
      d.installed ? `<span class="m" style="color:var(--support-success)">● installed</span>` : `<span class="m">○ available</span>`,
    ].filter(Boolean).join('');
    const body = stripFrontmatter(d.content || '');
    document.getElementById('m-content').innerHTML = renderMarkdown(body || '*No SKILL.md body.*');
    document.getElementById('m-actions').innerHTML = renderModalActions(d);
  } catch (e) {
    document.getElementById('m-content').innerHTML = `<span style="color:var(--support-error)">${esc(e.message)}</span>`;
  }
}

function iconMeta(label, value){
  return `<span class="m"><strong style="color:var(--text-secondary);font-weight:500">${esc(label)}:</strong>&nbsp;${esc(value)}</span>`;
}

function renderModalActions(d){
  const installBtn = d.installed
    ? `<button class="btn danger" onclick="doRemove('${esc(d.name)}', true)">
         <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 5h10M6 5V3h4v2M5 5l1 9h4l1-9"/></svg>
         Uninstall
       </button>`
    : `<button class="btn primary" onclick="doImport('${esc(d.name)}', true)">
         <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 2v9M4 7l4 4 4-4M3 14h10"/></svg>
         Install skill
       </button>`;
  const tryBtn = d.installed
    ? `<button class="btn" onclick="closeModal();document.getElementById('question').focus()">
         <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 3v10l4-3h6V3z"/></svg>
         Try in console
       </button>` : '';
  const docsBtn = `<button class="btn" onclick="window.open('','_blank')||alert('open ${esc(d.source||'')}')">
         <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 2h7l3 3v9H3z"/><path d="M10 2v3h3"/></svg>
         View source
       </button>`;
  return installBtn + tryBtn + docsBtn;
}

function stripFrontmatter(md){
  return md.replace(/^---\s*\n[\s\S]*?\n---\s*\n/, '');
}
function renderMarkdown(md){
  if (window.marked) {
    marked.setOptions({ gfm:true, breaks:false });
    return marked.parse(md);
  }
  return `<pre>${esc(md)}</pre>`;
}
function closeModal(){
  document.getElementById('modal').classList.remove('open');
  document.body.style.overflow = '';
  STATE.modalSkill = null;
}

/* ════════════════════════════════════════════════════════════════════
   Install / uninstall
   ════════════════════════════════════════════════════════════════════ */
async function doImport(name, fromModal){
  const ok = await postAction('/import', name, 'Import');
  if (ok) toast(`Imported ${name}`, 'ok');
  await loadSkills();
  if (fromModal) await openModal(name);
}
async function doRemove(name, fromModal){
  const ok = await postAction('/uninstall', name, 'Uninstall');
  if (ok) toast(`Removed ${name}`, 'ok');
  await loadSkills();
  if (fromModal) await openModal(name);
}
async function postAction(path, name, label){
  try {
    const r = await fetch(path, {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ name }),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok || d.error) {
      toast(`${label} failed: ${d.detail || d.error || r.status}`, 'err');
      return false;
    }
    return true;
  } catch (e) {
    toast(`${label} failed: ${e.message}`, 'err');
    return false;
  }
}

/* ════════════════════════════════════════════════════════════════════
   Ask the agent
   ════════════════════════════════════════════════════════════════════ */
function autoresize(ta){
  ta.style.height = 'auto';
  ta.style.height = Math.min(ta.scrollHeight, 200) + 'px';
}
const qEl = document.getElementById('question');
qEl.addEventListener('input', () => autoresize(qEl));

async function ask(){
  const q = qEl.value.trim();
  if (!q) return;
  const btn = document.getElementById('ask-btn');
  const btnText = document.getElementById('ask-btn-text');
  const wrap = document.getElementById('answer-wrap');
  const out = document.getElementById('answer');
  const meta = document.getElementById('answer-meta');

  btn.disabled = true;
  btnText.innerHTML = '<span class="spinner"></span> thinking';
  wrap.classList.add('vis');
  out.classList.remove('markdown');
  out.innerHTML = `
    <div class="thinking">
      <div class="bar"></div><div class="bar"></div><div class="bar"></div>
      <span>agent is loading skills, picking tools, executing scripts…</span>
    </div>`;
  meta.textContent = '';
  const t0 = performance.now();
  try {
    const r = await fetch('/ask', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ question: q }),
    });
    const d = await r.json();
    const dt = ((performance.now() - t0) / 1000).toFixed(2);
    meta.textContent = `${dt}s`;
    if (d.error || !r.ok) {
      out.innerHTML = `<span class="err">${esc(d.detail || d.error || ('HTTP ' + r.status))}</span>`;
    } else {
      const ans = d.answer || '(empty answer)';
      // Render as markdown if it looks like markdown, otherwise plain.
      if (/[#*`>\[]/.test(ans) && window.marked) {
        out.classList.add('markdown');
        out.innerHTML = renderMarkdown(ans);
      } else {
        out.textContent = ans;
      }
    }
  } catch (e) {
    out.innerHTML = `<span class="err">${esc(e.message)}</span>`;
  } finally {
    btn.disabled = false;
    btnText.textContent = 'Ask';
    syncAskState();
  }
}

/* ════════════════════════════════════════════════════════════════════
   Toasts
   ════════════════════════════════════════════════════════════════════ */
function toast(msg, kind){
  const c = document.getElementById('toasts');
  const el = document.createElement('div');
  el.className = 'toast' + (kind === 'err' ? ' err' : '');
  el.innerHTML = `
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
      ${kind === 'err'
        ? '<circle cx="8" cy="8" r="6"/><path d="M8 5v3M8 11v.01"/>'
        : '<circle cx="8" cy="8" r="6"/><path d="m5 8 2 2 4-4"/>'}
    </svg>
    <span>${esc(msg)}</span>`;
  c.appendChild(el);
  setTimeout(() => {
    el.style.transition = 'opacity 0.18s, transform 0.18s';
    el.style.opacity = '0';
    el.style.transform = 'translateX(20px)';
    setTimeout(() => el.remove(), 200);
  }, 2600);
}

/* ════════════════════════════════════════════════════════════════════
   Boot
   ════════════════════════════════════════════════════════════════════ */
loadSkills();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="cuga-skills UI (in-process agent)")
    parser.add_argument("--port", type=int, default=28910)
    parser.add_argument("--skills-dir", default=None,
        help="Source library to scan for SKILL.md (default: ../cuga-skills)")
    parser.add_argument("--provider", "-p", default=None,
        choices=["rits", "watsonx", "openai", "anthropic", "litellm", "ollama"])
    parser.add_argument("--model", "-m", default=None)
    args = parser.parse_args(argv)

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    skills_root = Path(args.skills_dir
        or os.getenv("SKILLS_DIR")
        or (_HERE.parent / "cuga-skills")).resolve()

    print(f"\n  cuga-skills UI  →  http://127.0.0.1:{args.port}")
    print(f"  source library  →  {skills_root}")
    print(f"  cuga skills dir →  {_RUNTIME_CUGA}/skills/")
    print(f"  sandbox dir     →  {_SANDBOX_DIR} (cwd for run_command)\n")

    import uvicorn
    uvicorn.run(make_app(skills_root), host="0.0.0.0", port=args.port,
                log_level="warning")


if __name__ == "__main__":
    main()
