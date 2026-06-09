"""Ouroboros specialist factories.

Each `make_<name>()` returns a CugaAgent loaded from one skill folder
(SKILL.md + tools.py). The supervisor in main.py wires these into a
CugaSupervisor.

A specialist is the union of:
  - SKILL.md frontmatter + body  → `special_instructions`
  - tools.py `TOOLS` list         → `tools`
  - Optional MCP tools from the   → injected by `bind_web_search`
    web bridge (web_search)         pattern in the skill's tools.py
  - Per-specialist step cap        → forwarded to CugaSupervisor as the
                                      cuga_lite_max_steps for that agent
                                      (currently set on the supervisor
                                      level — see main.py)
  - `agent.description` attribute  → so the supervisor's planner sees a
                                      meaningful summary in the
                                      delegate_to_<name> tool list

The skills folder is the source of truth. If you change a SKILL.md, you
get the change on the next process restart with no code edit.
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from langchain_core.tools import BaseTool

_DIR        = Path(__file__).parent
_SKILLS_DIR = _DIR / "skills"


# ── Frontmatter parser (vendored, no SDK import) ─────────────────────────

def _parse_skill(skill_md_path: Path) -> tuple[dict, str]:
    text = skill_md_path.read_text()
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm_block = text[3:end].strip()
    body = text[end + 4:].lstrip()

    # Tiny key: value parser; we only need name + description, both single-line.
    fm: dict[str, Any] = {}
    for raw in fm_block.splitlines():
        line = raw.rstrip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fm[key.strip()] = value.strip()
    return fm, body


# ── Skill loader ─────────────────────────────────────────────────────────

@dataclass
class Skill:
    name:        str
    description: str
    body:        str
    tools:       list[BaseTool]
    bind_search: Optional[Callable[[Callable], None]]  # for skills that need web_search


def _load_tools_module(skill_dir: Path):
    """Load skills/<name>/tools.py as a module. We do this manually so each
    skill's tools.py is namespaced under `ouroboros_skills.<name>.tools` and
    the imports don't collide between skills."""
    name = skill_dir.name
    module_name = f"ouroboros_skills.{name}.tools"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(
        module_name, skill_dir / "tools.py",
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load skill tools at {skill_dir}/tools.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_skill(name: str) -> Skill:
    skill_dir = _SKILLS_DIR / name
    fm, body  = _parse_skill(skill_dir / "SKILL.md")
    mod       = _load_tools_module(skill_dir)
    tools     = list(getattr(mod, "TOOLS", []) or [])
    bind_fn   = getattr(mod, "bind_web_search", None)
    return Skill(
        name=fm.get("name", name),
        description=fm.get("description", "").strip(),
        body=body,
        tools=tools,
        bind_search=bind_fn,
    )


# ── MCP web_search resolver ──────────────────────────────────────────────
# Loaded once at startup; multiple skills bind to the same coroutine.

_WEB_SEARCH_TOOL: Optional[BaseTool] = None


def _resolve_web_search() -> Optional[BaseTool]:
    global _WEB_SEARCH_TOOL
    if _WEB_SEARCH_TOOL is not None:
        return _WEB_SEARCH_TOOL
    try:
        sys.path.insert(0, str(_DIR.parent))   # so `_mcp_bridge` resolves
        from _mcp_bridge import load_tools     # type: ignore
    except ImportError:
        return None
    mcp_tools = load_tools(["web"])
    for t in mcp_tools:
        if t.name == "web_search":
            _WEB_SEARCH_TOOL = t
            return t
    return None


def _bind_web_search_into(skill: Skill) -> None:
    if skill.bind_search is None:
        return
    web = _resolve_web_search()
    if web is None:
        # Skill will raise at call-time; let it surface the error there.
        return
    coro = getattr(web, "coroutine", None) or getattr(web, "_arun", None)
    if coro is None:
        return

    async def _wrapped(query: str, max_results: int = 5):
        return await coro(query=query, max_results=max_results)

    skill.bind_search(_wrapped)


# ── Agent factories ──────────────────────────────────────────────────────

def _make_agent(skill: Skill, *, model, extra_tools: list[BaseTool] | None = None):
    """Build a CugaAgent for one skill."""
    from cuga.sdk import CugaAgent

    _bind_web_search_into(skill)
    tools = list(skill.tools) + list(extra_tools or [])

    agent = CugaAgent(
        model=model,
        tools=tools,
        special_instructions=skill.body,
        cuga_folder=str(_DIR / f".cuga_{skill.name}"),
        enable_knowledge=False,
        auto_load_policies=False,
    )
    # The supervisor reads `agent.description` to populate the
    # delegate_to_<name> tool's docstring (cuga_supervisor_graph.py:283).
    agent.description = skill.description
    return agent


def make_scout(*, model):
    return _make_agent(_load_skill("scout"), model=model)


def make_site_auditor(*, model):
    return _make_agent(_load_skill("site_auditor"), model=model)


def make_voice_of_customer(*, model):
    skill = _load_skill("voice_of_customer")
    # No host-side extras — search_reviews wraps web_search via bind_web_search.
    return _make_agent(skill, model=model)


def make_person_finder(*, model):
    return _make_agent(_load_skill("person_finder"), model=model)


def make_stack_scanner(*, model):
    return _make_agent(_load_skill("stack_scanner"), model=model)


def make_revenue_estimator(*, model):
    return _make_agent(_load_skill("revenue_estimator"), model=model)


def make_pitch_email_writer(*, model):
    return _make_agent(_load_skill("pitch_email_writer"), model=model)


SPECIALIST_NAMES: list[str] = [
    "scout",
    "site_auditor",
    "voice_of_customer",
    "person_finder",
    "stack_scanner",
    "revenue_estimator",
    "pitch_email_writer",
]


def make_all(*, model) -> dict[str, Any]:
    """Return {name: CugaAgent} for the supervisor."""
    return {
        "scout":              make_scout(model=model),
        "site_auditor":       make_site_auditor(model=model),
        "voice_of_customer":  make_voice_of_customer(model=model),
        "person_finder":      make_person_finder(model=model),
        "stack_scanner":      make_stack_scanner(model=model),
        "revenue_estimator":  make_revenue_estimator(model=model),
        "pitch_email_writer": make_pitch_email_writer(model=model),
    }
