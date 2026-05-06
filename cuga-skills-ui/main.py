"""
cuga-skills-ui — the simplest possible UX for trying a CUGA skill.

What it does:
  1. Scans ../cuga-skills/ for SKILL.md files (frontmatter `name` + `description`).
  2. Lets you "import" a skill — copies it into a runtime .cuga/skills/<name>/
     folder so `discover_skills(cuga_folder)` picks it up.
  3. Builds a `CugaAgent(cuga_folder=...)` in-process and POSTs your question
     to it. No separate CUGA server, no OpenSandbox, no Docker required.

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

Skill execution: the agent reads each loaded skill's body via `load_skill` and
follows the playbook. OpenSandbox shell tools (`run_command`, `write_file`, …)
are intentionally disabled so this app runs without Docker — companion scripts
won't execute, but the playbook prompt is the value here.
"""
from __future__ import annotations

# Set Dynaconf env BEFORE importing cuga so settings load with skills on
# and OpenSandbox / shell tools off (no Docker dependency).
import os
os.environ.setdefault("DYNACONF_SKILLS__ENABLED", "true")
os.environ.setdefault("DYNACONF_ADVANCED_FEATURES__OPENSANDBOX_SANDBOX", "false")
os.environ.setdefault("DYNACONF_ADVANCED_FEATURES__ENABLE_SHELL_TOOL", "false")

import argparse
import importlib.util
import logging
import re
import shutil
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
# Runtime cuga folder — we copy imported skills here, then point CugaAgent at it.
# ---------------------------------------------------------------------------

_RUNTIME_CUGA = _HERE / ".cuga"
_RUNTIME_SKILLS = _RUNTIME_CUGA / "skills"


def import_skill(skill: dict) -> Path:
    """Copy a skill folder into <runtime>/.cuga/skills/<name>/."""
    src = Path(skill["dir"])
    dst = _RUNTIME_SKILLS / skill["name"]
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)
    log.info("Imported skill %r → %s", skill["name"], dst)
    return dst


def uninstall_skill(name: str) -> bool:
    dst = _RUNTIME_SKILLS / name
    if not dst.exists():
        return False
    shutil.rmtree(dst)
    log.info("Removed skill %r from %s", name, dst)
    return True


def list_imported() -> list[str]:
    if not _RUNTIME_SKILLS.is_dir():
        return []
    return sorted(p.name for p in _RUNTIME_SKILLS.iterdir() if (p / "SKILL.md").is_file())


def _load_skill_tools(skill_dir: Path) -> list:
    """Convention: if a skill has `tools.py` exporting `TOOLS = [...]`, load it.

    Returns the list of LangChain tools to pass to CugaAgent. Empty list if
    the skill has no tools.py.
    """
    tools_path = skill_dir / "tools.py"
    if not tools_path.is_file():
        return []
    spec = importlib.util.spec_from_file_location(
        f"_cuga_skill_{skill_dir.name}_tools", tools_path
    )
    if spec is None or spec.loader is None:
        return []
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        log.warning("Failed to import %s: %s", tools_path, e)
        return []
    tools = getattr(module, "TOOLS", None)
    if not isinstance(tools, list):
        log.warning("%s has no TOOLS list — skipping", tools_path)
        return []
    log.info("Loaded %d tool(s) from %s", len(tools), tools_path)
    return tools


# ---------------------------------------------------------------------------
# Lazy CugaAgent — built on first /ask, after at least one skill is imported.
# ---------------------------------------------------------------------------

_agent = None
_agent_skill_signature: tuple[str, ...] = ()


def _build_agent():
    """Construct a CugaAgent pointed at the runtime cuga_folder.

    Skills are auto-discovered by CUGA from <cuga_folder>/skills/**/SKILL.md
    when settings.skills.enabled is true (set via env above).
    """
    _provider_toml = {
        "rits":      "settings.rits.toml",
        "watsonx":   "settings.watsonx.toml",
        "openai":    "settings.openai.toml",
        "anthropic": "settings.openai.toml",  # anthropic uses openai-compat internally
        "litellm":   "settings.litellm.toml",
        "ollama":    "settings.openai.toml",
    }
    provider = (os.getenv("LLM_PROVIDER") or "").lower()
    toml = _provider_toml.get(provider, "settings.rits.toml")
    os.environ.setdefault("AGENT_SETTING_CONFIG", toml)

    from cuga import CugaAgent
    from _llm import create_llm

    # Gather native tools from each imported skill's tools.py (if any).
    skill_tools = []
    for skill_name in list_imported():
        skill_tools.extend(_load_skill_tools(_RUNTIME_SKILLS / skill_name))

    return CugaAgent(
        model=create_llm(
            provider=os.getenv("LLM_PROVIDER"),
            model=os.getenv("LLM_MODEL"),
        ),
        tools=skill_tools or None,
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
            s["has_tools"] = (Path(s["dir"]) / "tools.py").is_file()
        return {
            "available": available,
            "skills_root": str(skills_root),
            "runtime_cuga_folder": str(_RUNTIME_CUGA),
        }

    @app.post("/import")
    async def api_import(req: NameReq):
        avail = {s["name"]: s for s in discover_skill_dirs(skills_root)}
        if req.name not in avail:
            raise HTTPException(404, f"Unknown skill: {req.name!r}")
        dst = import_skill(avail[req.name])
        global _agent
        _agent = None  # rebuild on next /ask
        return {"ok": True, "name": req.name, "dst": str(dst)}

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

_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>cuga-skills</title>
<style>
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    background:#0f1117;color:#e2e8f0;min-height:100vh;padding:24px 24px 48px}
  .wrap{max-width:760px;margin:0 auto}
  h1{font-size:18px;font-weight:700;margin-bottom:4px}
  .sub{font-size:11px;color:#6b7280;margin-bottom:20px;line-height:1.6}
  .sub code{background:#1f2937;padding:1px 5px;border-radius:3px}
  .card{background:#1a1a2e;border:1px solid #2d2d4a;border-radius:10px;
    padding:16px 18px;margin-bottom:16px}
  .card h2{font-size:13px;font-weight:600;color:#c5cae9;margin-bottom:12px;
    display:flex;align-items:center;gap:8px}
  textarea,input,button{font-family:inherit;font-size:13px}
  textarea,input{width:100%;padding:8px 10px;border-radius:7px;
    background:#0f1117;border:1px solid #374151;color:#e2e8f0;outline:none}
  textarea:focus,input:focus{border-color:#16a34a}
  textarea{min-height:64px;resize:vertical}
  button{padding:7px 14px;border-radius:7px;border:none;background:#16a34a;
    color:#fff;cursor:pointer;font-weight:600;white-space:nowrap}
  button:hover{background:#15803d}
  button:disabled{background:#374151;color:#6b7280;cursor:default}
  button.secondary{background:#1f2937;color:#9ca3af;border:1px solid #374151}
  button.secondary:hover{background:#374151;color:#fff}
  .skill{display:flex;justify-content:space-between;align-items:flex-start;
    gap:10px;padding:10px 12px;border:1px solid #2d2d4a;border-radius:8px;
    margin-bottom:8px;background:#0f1117}
  .skill:hover{border-color:#374151}
  .skill .meta{flex:1;min-width:0}
  .skill .name{font-size:13px;font-weight:600;color:#f1f5f9;
    display:flex;align-items:center;gap:6px}
  .skill .desc{font-size:11px;color:#9ca3af;line-height:1.5;margin-top:4px}
  .skill .actions{display:flex;gap:6px;flex-shrink:0}
  .badge{padding:1px 7px;border-radius:7px;font-size:10px;font-weight:600}
  .badge-installed{background:#052e16;color:#4ade80}
  .badge-available{background:#1f2937;color:#9ca3af}
  .badge-tools{background:#1e3a5f;color:#60a5fa;margin-left:4px}
  .answer{margin-top:10px;padding:12px;border-radius:7px;background:#0f1117;
    border:1px solid #2d2d4a;font-size:13px;line-height:1.6;color:#d1d5db;
    white-space:pre-wrap;display:none}
  .answer.vis{display:block}
  .err{color:#f87171}
  .empty{font-size:12px;color:#6b7280;padding:14px;text-align:center;
    border:1px dashed #2d2d4a;border-radius:8px}
</style></head>
<body><div class="wrap">

  <h1>🎒 cuga-skills</h1>
  <div class="sub" id="sub-meta">
    Imports skills from a local library, then asks questions against an
    in-process <code>CugaAgent</code> — no separate CUGA backend.
  </div>

  <div class="card">
    <h2>Skills <span style="margin-left:auto;font-size:11px;color:#6b7280;font-weight:400" id="counts"></span></h2>
    <div id="skill-list"><div class="empty">Loading…</div></div>
  </div>

  <div class="card">
    <h2>Ask the agent</h2>
    <textarea id="question" placeholder="e.g. Easy hikes near Yosemite, CA"></textarea>
    <div style="display:flex;gap:8px;margin-top:10px;align-items:center">
      <button id="ask-btn" onclick="ask()" disabled>Ask</button>
      <span class="sub" style="margin:0 0 0 4px" id="ask-status">Import a skill to enable.</span>
    </div>
    <div id="answer" class="answer"></div>
  </div>

</div>

<script>
let STATE = { available: [], skills_root: '' };

async function loadSkills() {
  const r = await fetch('/skills');
  STATE = await r.json();
  renderSkills();
}

function renderSkills() {
  const list = document.getElementById('skill-list');
  const counts = document.getElementById('counts');
  const installed = STATE.available.filter(s => s.installed).length;
  counts.textContent = `${STATE.available.length} available · ${installed} installed`;
  if (!STATE.available.length) {
    list.innerHTML = `<div class="empty">No SKILL.md files in <code>${esc(STATE.skills_root||'')}</code></div>`;
    syncAskState();
    return;
  }
  list.innerHTML = STATE.available.map(s => `
    <div class="skill">
      <div class="meta">
        <div class="name">
          ${esc(s.name)}
          <span class="badge ${s.installed?'badge-installed':'badge-available'}">
            ${s.installed?'installed':'available'}
          </span>
          ${s.has_tools?'<span class="badge badge-tools">+ tools</span>':''}
        </div>
        <div class="desc">${esc(s.description||'')}</div>
      </div>
      <div class="actions">
        ${s.installed
          ? `<button class="secondary" onclick="doRemove('${esc(s.name)}')">Remove</button>`
          : `<button onclick="doImport('${esc(s.name)}')">Import</button>`}
      </div>
    </div>`).join('');
  syncAskState();
}

function syncAskState() {
  const anyInstalled = STATE.available.some(s => s.installed);
  document.getElementById('ask-btn').disabled = !anyInstalled;
  document.getElementById('ask-status').textContent = anyInstalled
    ? 'Imported: ' + STATE.available.filter(s => s.installed).map(s => s.name).join(', ')
    : 'Import a skill to enable.';
}

async function doImport(name) { await postAction('/import', name, 'Import failed'); await loadSkills(); }
async function doRemove(name) {
  if (!confirm('Remove '+name+'?')) return;
  await postAction('/uninstall', name, 'Remove failed'); await loadSkills();
}
async function postAction(path, name, errLabel) {
  const r = await fetch(path, { method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({name}) });
  const d = await r.json();
  if (!r.ok || d.error) alert(errLabel+': '+(d.detail||d.error||r.status));
}

async function ask() {
  const q = document.getElementById('question').value.trim();
  if (!q) return;
  const btn = document.getElementById('ask-btn');
  const out = document.getElementById('answer');
  btn.disabled = true; btn.textContent = 'Thinking…';
  out.className = 'answer vis';
  out.textContent = '…';
  try {
    const r = await fetch('/ask', { method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({question: q}) });
    const d = await r.json();
    if (d.error) {
      out.innerHTML = '<span class="err">'+esc(d.detail||d.error)+'</span>';
    } else {
      out.textContent = d.answer || '(empty answer)';
    }
  } catch(e) {
    out.innerHTML = '<span class="err">'+esc(e.message)+'</span>';
  } finally {
    btn.disabled = false; btn.textContent = 'Ask';
  }
}

function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/'/g,'&#39;');
}

loadSkills();
</script>
</body></html>"""


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
    print(f"  runtime .cuga   →  {_RUNTIME_CUGA}\n")

    import uvicorn
    uvicorn.run(make_app(skills_root), host="0.0.0.0", port=args.port,
                log_level="warning")


if __name__ == "__main__":
    main()
