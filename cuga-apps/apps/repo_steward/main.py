"""
Repo Steward — OSS maintainer copilot with visible policies and skills
======================================================================

A CUGA app that acts as a copilot for open-source maintainers: triage issues,
review PRs, draft changelog entries, welcome first-time contributors.

The right-hand panel surfaces what makes this app a CUGA app:
  - Which **skills** were available and which one(s) the agent loaded
  - Which **policies** fired and their verdicts (PASS / BLOCK / REDACTED)
  - Toggle switches to enable/disable individual policies and re-run the
    same prompt — the output visibly changes

Run:
    python main.py
    python main.py --port 28822
    python main.py --provider anthropic

Then open: http://127.0.0.1:28822
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

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

_SAMPLE = _DIR / "sample_repo"

# Specialist policy folders — each CugaAgent points at its own .cuga so its
# governance is scoped, and the supervisor routes between them.
_SPECIALIST_DIRS: dict[str, Path] = {
    "maintainer_steward": _DIR / "specialists" / "maintainer_steward" / ".cuga",
    "contributor_ally":   _DIR / "specialists" / "contributor_ally"   / ".cuga",
}

# Enable skills subsystem (reads .agents/skills/**/SKILL.md next to _DIR).
# Dynaconf uses the DYNACONF_ prefix for env-overrides in this codebase.
os.environ.setdefault("DYNACONF_SKILLS__ENABLED", "true")
# Point CUGA_FOLDER at the maintainer specialist — purely so the skills loader's
# legacy `.cuga/skills` fallback resolves to something sensible. Skills actually
# live under `.agents/skills/` which both specialists share.
os.environ.setdefault("CUGA_FOLDER", str(_SPECIALIST_DIRS["maintainer_steward"]))


# ---------------------------------------------------------------------------
# Turn log — per-turn capture of which skills loaded + which policies fired.
# Consumed by the right-hand UI panel.
# ---------------------------------------------------------------------------

_turn_log: list[dict] = []


def _record_turn(question: str, answer: str, events: dict) -> dict:
    entry = {
        "id":         uuid.uuid4().hex[:8],
        "question":   question,
        "answer":     answer,
        "skills":     events.get("skills", []),
        "tools":      events.get("tools", []),
        "policies":   events.get("policies", []),
        "fires":      events.get("fires", []),
        "reasoning":  events.get("reasoning", ""),
        "routed_to":  events.get("routed_to", ""),
        "sources":    events.get("sources", []),
        "at":         datetime.now(timezone.utc).isoformat(),
    }
    _turn_log.insert(0, entry)
    if len(_turn_log) > 50:
        _turn_log.pop()
    return entry


# ---------------------------------------------------------------------------
# Runtime repo state — the "currently active" repo the agent is working on.
# ---------------------------------------------------------------------------
#
# Shared across the process: tools read from here, /repo POST writes to here,
# /repo GET returns it for the UI header. Starts as the bundled sample_repo.

import subprocess
import threading
import urllib.request

_REPO_CACHE_ROOT = Path("/tmp/repo_steward")

_repo_state: dict = {
    "kind":         "sample",             # "sample" | "live"
    "owner":        "",
    "repo":         "",
    "ref":          "main",
    "clone_path":   str(_SAMPLE),         # sample_repo is the default workspace
    "clone_status": "ready",              # "ready" | "cloning" | "error"
    "clone_error":  "",
    "last_switched": datetime.now(timezone.utc).isoformat(),
}

_repo_state_lock = threading.Lock()


def _github_headers() -> dict[str, str]:
    """Return GitHub REST headers, optionally with a token for higher rate limit."""
    h = {"Accept": "application/vnd.github+json",
         "User-Agent": "repo-steward/1.0"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _github_api(path: str, params: dict | None = None, timeout: int = 10) -> Any:
    """GET an endpoint on api.github.com and return parsed JSON."""
    base = "https://api.github.com"
    if params:
        import urllib.parse as _u
        path = f"{path}?{_u.urlencode(params)}"
    req = urllib.request.Request(base + path, headers=_github_headers())
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _sanitize_slug(s: str) -> str:
    """Keep alnum + _- for filesystem paths; no path traversal."""
    return re.sub(r"[^a-zA-Z0-9_\-\.]", "_", s)[:64] or "unknown"


def _clone_dir(owner: str, repo: str, ref: str) -> Path:
    slug = f"{_sanitize_slug(owner)}__{_sanitize_slug(repo)}@{_sanitize_slug(ref)}"
    return _REPO_CACHE_ROOT / slug


def _do_clone(owner: str, repo: str, ref: str) -> None:
    """Shallow-clone <owner>/<repo>@<ref> into the cache. Runs in a thread."""
    target = _clone_dir(owner, repo, ref)
    url = f"https://github.com/{owner}/{repo}.git"
    try:
        _REPO_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        if target.exists():
            # Reuse cached clone
            with _repo_state_lock:
                _repo_state["clone_status"] = "ready"
                _repo_state["clone_path"]   = str(target)
                _repo_state["clone_error"]  = ""
            log.info("Reusing cached clone at %s", target)
            return

        log.info("Cloning %s@%s → %s", url, ref, target)
        # Shallow clone, single branch; read-only; fast.
        cmd = ["git", "clone", "--depth", "1", "--branch", ref, url, str(target)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "git clone failed")

        with _repo_state_lock:
            _repo_state["clone_status"] = "ready"
            _repo_state["clone_path"]   = str(target)
            _repo_state["clone_error"]  = ""
        log.info("Clone complete: %s", target)
    except Exception as e:
        log.warning("Clone failed for %s@%s: %s", url, ref, e)
        with _repo_state_lock:
            _repo_state["clone_status"] = "error"
            _repo_state["clone_error"]  = str(e)[:500]


def _switch_repo(owner: str, repo: str, ref: str = "main") -> dict:
    """Flip the active repo and kick off a background clone."""
    owner = owner.strip()
    repo  = repo.strip()
    ref   = (ref or "main").strip() or "main"
    if not owner or not repo:
        return {"ok": False, "error": "owner and repo are required"}

    with _repo_state_lock:
        _repo_state.update({
            "kind":          "live",
            "owner":         owner,
            "repo":          repo,
            "ref":           ref,
            "clone_status":  "cloning",
            "clone_error":   "",
            "last_switched": datetime.now(timezone.utc).isoformat(),
        })

    threading.Thread(
        target=_do_clone, args=(owner, repo, ref), daemon=True
    ).start()
    return {"ok": True, "owner": owner, "repo": repo, "ref": ref}


def _reset_to_sample() -> dict:
    """Point the active repo back at the bundled sample."""
    with _repo_state_lock:
        _repo_state.update({
            "kind":         "sample",
            "owner":        "",
            "repo":         "",
            "ref":          "main",
            "clone_path":   str(_SAMPLE),
            "clone_status": "ready",
            "clone_error":  "",
            "last_switched": datetime.now(timezone.utc).isoformat(),
        })
    return {"ok": True, "kind": "sample"}


# ---------------------------------------------------------------------------
# Tools — sample repo access + live repo switching + file/issue/PR browsing
# ---------------------------------------------------------------------------

def _make_tools():
    from langchain_core.tools import tool

    @tool
    def list_sample_issues() -> str:
        """List the bundled sample issues (number + title). Use this when the user asks
        what issues are in the demo repo or asks to browse them."""
        items = []
        for p in sorted((_SAMPLE / "issues").glob("*.json")):
            data = json.loads(p.read_text())
            items.append({"number": data["number"], "title": data["title"]})
        return json.dumps(items)

    @tool
    def get_sample_issue(number: int) -> str:
        """Fetch a bundled sample issue by number, returning its full JSON (title, body,
        author, labels, etc.). Use this when asked to triage a sample issue like '#102'."""
        p = _SAMPLE / "issues" / f"{number}.json"
        if not p.exists():
            return json.dumps({"error": f"No sample issue #{number}"})
        return p.read_text()

    @tool
    def list_sample_prs() -> str:
        """List the bundled sample PRs (number + title)."""
        items = []
        for p in sorted((_SAMPLE / "prs").glob("*.json")):
            data = json.loads(p.read_text())
            items.append({"number": data["number"], "title": data["title"]})
        return json.dumps(items)

    @tool
    def get_sample_pr(number: int) -> str:
        """Fetch a bundled sample PR by number, returning its full JSON."""
        p = _SAMPLE / "prs" / f"{number}.json"
        if not p.exists():
            return json.dumps({"error": f"No sample PR #{number}"})
        return p.read_text()

    @tool
    def get_contributing_md() -> str:
        """Return the CONTRIBUTING.md of the sample repo — use it to ground responses
        in the project's own conventions (commit format, issue template, etc.)."""
        p = _SAMPLE / "CONTRIBUTING.md"
        return p.read_text() if p.exists() else "(no CONTRIBUTING.md in sample repo)"

    @tool
    def fetch_github_issue(owner: str, repo: str, number: int) -> str:
        """Fetch a real public GitHub issue or PR via the unauthenticated REST API.
        Use only when the user provides a specific owner/repo/number and explicitly asks
        for a one-off live lookup WITHOUT switching the active repo. Prefer
        `set_repo` + `get_issue` for anything more than one call."""
        try:
            data = _github_api(f"/repos/{owner}/{repo}/issues/{number}")
            keep = {
                "number":   data.get("number"),
                "title":    data.get("title"),
                "state":    data.get("state"),
                "author":   (data.get("user") or {}).get("login"),
                "body":     data.get("body"),
                "labels":   [l.get("name") for l in data.get("labels", [])],
                "html_url": data.get("html_url"),
            }
            return json.dumps(keep)
        except Exception as e:
            return json.dumps({"error": str(e), "owner": owner, "repo": repo, "number": number})

    # -- Runtime repo switching ------------------------------------------------

    @tool
    def set_repo(owner: str, repo: str, ref: str = "main") -> str:
        """Switch the steward's active repo to <owner>/<repo>@<ref>.

        After this call, `list_issues`, `list_prs`, `get_issue`, `get_pr`, and
        `get_repo_file` all target the new repo. A shallow git clone starts
        in the background so file-browsing tools work seconds later.

        Call this ONCE per user request that names a repo (e.g. `use
        cuga-project/cuga-agent`, or a github.com URL). Do not call it for every
        subsequent tool."""
        result = _switch_repo(owner, repo, ref)
        return json.dumps(result)

    @tool
    def get_active_repo() -> str:
        """Return the currently active repo state — kind (sample|live), owner,
        repo, ref, and whether the background clone is ready. Call this if you
        are unsure which repo the user means."""
        with _repo_state_lock:
            snapshot = dict(_repo_state)
        return json.dumps(snapshot)

    @tool
    def reset_to_sample_repo() -> str:
        """Switch back to the bundled offline sample repo (issues 101-103, PRs
        55-57). Use this if the user asks to 'use the sample repo' or 'reset'."""
        return json.dumps(_reset_to_sample())

    # -- Active-repo browsing (GitHub REST) ------------------------------------

    def _require_live() -> dict | None:
        """Return an error dict if the active repo is the offline sample."""
        with _repo_state_lock:
            s = dict(_repo_state)
        if s["kind"] != "live" or not s["owner"] or not s["repo"]:
            return {"error": "No live repo active. Call set_repo(owner, repo) first."}
        return None

    @tool
    def list_issues(state: str = "open", limit: int = 20) -> str:
        """List issues on the ACTIVE live repo (set via `set_repo`).

        Args:
            state: 'open' (default), 'closed', or 'all'.
            limit: Max issues to return (1..50). Title + number only.

        Excludes pull requests — use `list_prs` for those."""
        err = _require_live()
        if err: return json.dumps(err)
        with _repo_state_lock:
            owner, repo = _repo_state["owner"], _repo_state["repo"]
        try:
            limit = max(1, min(int(limit), 50))
            data = _github_api(
                f"/repos/{owner}/{repo}/issues",
                params={"state": state, "per_page": limit},
            )
            # GitHub's /issues returns PRs too — filter them out
            items = [
                {"number": i["number"], "title": i["title"], "author": (i.get("user") or {}).get("login")}
                for i in data if "pull_request" not in i
            ]
            return json.dumps(items)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @tool
    def list_prs(state: str = "open", limit: int = 20) -> str:
        """List pull requests on the ACTIVE live repo (set via `set_repo`).

        Args:
            state: 'open' (default), 'closed', or 'all'.
            limit: Max PRs to return (1..50)."""
        err = _require_live()
        if err: return json.dumps(err)
        with _repo_state_lock:
            owner, repo = _repo_state["owner"], _repo_state["repo"]
        try:
            limit = max(1, min(int(limit), 50))
            data = _github_api(
                f"/repos/{owner}/{repo}/pulls",
                params={"state": state, "per_page": limit},
            )
            items = [
                {"number": p["number"], "title": p["title"], "author": (p.get("user") or {}).get("login")}
                for p in data
            ]
            return json.dumps(items)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @tool
    def get_issue(number: int) -> str:
        """Fetch a full issue from the ACTIVE live repo (set via `set_repo`)."""
        err = _require_live()
        if err: return json.dumps(err)
        with _repo_state_lock:
            owner, repo = _repo_state["owner"], _repo_state["repo"]
        try:
            data = _github_api(f"/repos/{owner}/{repo}/issues/{number}")
            keep = {
                "number":   data.get("number"),
                "title":    data.get("title"),
                "state":    data.get("state"),
                "author":   (data.get("user") or {}).get("login"),
                "author_association": data.get("author_association"),
                "body":     data.get("body"),
                "labels":   [l.get("name") for l in data.get("labels", [])],
                "html_url": data.get("html_url"),
            }
            return json.dumps(keep)
        except Exception as e:
            return json.dumps({"error": str(e), "number": number})

    @tool
    def get_pr(number: int) -> str:
        """Fetch a full PR from the ACTIVE live repo (set via `set_repo`)."""
        err = _require_live()
        if err: return json.dumps(err)
        with _repo_state_lock:
            owner, repo = _repo_state["owner"], _repo_state["repo"]
        try:
            data = _github_api(f"/repos/{owner}/{repo}/pulls/{number}")
            keep = {
                "number":        data.get("number"),
                "title":         data.get("title"),
                "state":         data.get("state"),
                "author":        (data.get("user") or {}).get("login"),
                "author_association": data.get("author_association"),
                "body":          data.get("body"),
                "changed_files": data.get("changed_files"),
                "additions":     data.get("additions"),
                "deletions":     data.get("deletions"),
                "html_url":      data.get("html_url"),
            }
            return json.dumps(keep)
        except Exception as e:
            return json.dumps({"error": str(e), "number": number})

    # -- File access over the cloned workspace ---------------------------------

    @tool
    def get_repo_file(path: str) -> str:
        """Read a file from the active repo's local clone (e.g. 'CONTRIBUTING.md',
        'CODEOWNERS', 'docs/ARCHITECTURE.md'). For sample repo, only
        CONTRIBUTING.md is present."""
        with _repo_state_lock:
            clone_path = Path(_repo_state["clone_path"])
            kind       = _repo_state["kind"]
            status     = _repo_state["clone_status"]
            err_msg    = _repo_state["clone_error"]
        if kind == "live" and status == "cloning":
            return json.dumps({"error": "Repo clone still in progress; retry in a few seconds."})
        if kind == "live" and status == "error":
            return json.dumps({"error": f"Repo clone failed: {err_msg}"})

        # Path-traversal guard: reject absolute paths and any '..' segments,
        # and require the resolved path to be inside clone_path.
        rel = (path or "").lstrip("/").strip()
        if not rel or ".." in Path(rel).parts:
            return json.dumps({"error": f"Invalid path: {path!r}"})
        target = (clone_path / rel).resolve()
        try:
            target.relative_to(clone_path.resolve())
        except ValueError:
            return json.dumps({"error": f"Path escapes workspace: {path!r}"})
        if not target.is_file():
            return json.dumps({"error": f"File not found: {path!r}"})
        try:
            return target.read_text(errors="replace")[:20000]
        except Exception as e:
            return json.dumps({"error": str(e)})

    return [
        list_sample_issues, get_sample_issue,
        list_sample_prs, get_sample_pr,
        get_contributing_md, fetch_github_issue,
        set_repo, get_active_repo, reset_to_sample_repo,
        list_issues, list_prs, get_issue, get_pr,
        get_repo_file,
    ]


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_MAINTAINER = """\
# Maintainer Steward — the governance-heavy specialist

You handle issue triage, PR review, changelog entries, release notes, and
any interaction where a maintainer is the audience. You do NOT handle
first-time-contributor welcome messages — those are routed to the
`contributor_ally` specialist by the supervisor.

## Which repo are we working on?

You always have an **active repo**. It starts as the bundled offline `sample`
repo (issues 101-103, PRs 55-57, CONTRIBUTING.md present). For any other
repo, you have to switch to it first.

- If the user mentions `owner/repo`, a `github.com/owner/repo` URL, or says
  "switch to X", call `set_repo(owner, repo)` ONCE at the start of the turn.
- For a one-off lookup ("what's issue 42 in cuga-project/cuga-agent?"),
  prefer `fetch_github_issue(owner, repo, 42)` — don't switch the active
  repo for a single question.
- If you're unsure which repo the user means, call `get_active_repo` first.

Once active, use:
- `list_issues(state, limit)` / `list_prs(state, limit)` — browse.
- `get_issue(number)` / `get_pr(number)` — fetch the full artifact.
- `get_repo_file(path)` — read a file from the cloned repo (e.g.
  `CONTRIBUTING.md`, `CODEOWNERS`, `docs/ARCHITECTURE.md`).

For the sample repo keep using `list_sample_issues` / `get_sample_issue` /
`list_sample_prs` / `get_sample_pr` / `get_contributing_md`.

## How to answer

1. **Fetch the artifact FIRST.** If the user mentioned an issue or PR number,
   call the matching getter in an isolated code block and print the result:
   - Sample repo:  `get_sample_issue` / `get_sample_pr`
   - Live repo:    `get_issue` / `get_pr` (after `set_repo`)
   - One-off:      `fetch_github_issue(owner, repo, number)`
   Store the result in a named variable (e.g. `issue`, `pr`) — subsequent
   code blocks must reference it so the sandbox validator accepts them.

2. **Load the matching skill in the SAME code block as a reference to that
   variable.** The sandbox security validator rejects code that does not touch
   at least one named context variable. So write:

   ```python
   skill = await load_skill("issue_triage")
   print(skill)
   _ = issue  # reference fetched artifact so the validator accepts this block
   ```

   Do NOT call `load_skill` in a code block that only contains the call —
   always co-reference a previously-fetched variable.

   Skill → task mapping (your scope):
   - Triaging an issue → `issue_triage`
   - Reviewing a PR → `pr_review`
   - Drafting a changelog entry (one PR → one line) → `changelog_entry`
   - Composing release notes spanning multiple PRs → `release_notes`
   Do NOT load `contributor_welcome` — that skill is owned by the other
   specialist and should not be invoked from this context.

3. **Ground in project conventions.** Call `get_contributing_md` when your
   answer depends on commit-format rules, issue templates, or similar
   project-level conventions.

4. **Follow the skill's output format exactly.** After loading, render the
   final markdown answer matching the structure in the skill body verbatim —
   section headings, pills, checklists. The skill is the source of truth.

## General rules

- Cite which issue/PR number you are responding to.
- When the user asks "what can you do?", list the available skills by name
  (they are shown in the <available_skills> block) — do not invent capabilities.
- Keep responses concise. Maintainers are busy.
"""


_SYSTEM_CONTRIBUTOR = """\
# Contributor Ally — the welcoming specialist

You handle interactions where a first-time or new contributor is the audience:
welcome comments on a first PR, replies to "how do I contribute?" questions,
encouragement after a rough review. You do NOT triage issues, review PRs,
or draft release notes — those are owned by the `maintainer_steward` specialist.

## Which repo are we working on?

You share the active-repo state with the maintainer specialist. Use the same
tools if you need to look something up:

- Sample repo: `get_sample_issue` / `get_sample_pr` / `get_contributing_md`
- Live repo (set_repo already called elsewhere): `get_issue` / `get_pr` /
  `get_repo_file("CONTRIBUTING.md")`

But usually you don't need to — a welcome comment is about tone, not content.

## How to answer

1. **Pick the right skill.** In almost all cases: `contributor_welcome`.

2. **Load it in a code block that co-references the PR/issue data you're
   responding to.** The sandbox validator needs a context reference:

   ```python
   skill = await load_skill("contributor_welcome")
   print(skill)
   _ = pr  # reference fetched artifact so the validator accepts this block
   ```

3. **Follow the skill body exactly** — it has strict tone rules (no
   exclamation marks, no merge promise, under 120 words, neutral sign-off).

## General rules

- You're the face of the project to newcomers. Tone matters more than
  terseness.
- Never promise a review or merge timeline.
- Don't recite the contributing guide; quote the specific part that matters.
- If the user asks you to do something outside your scope (triage, review),
  say briefly that it's outside your scope — the supervisor will route it
  correctly next time.
"""


# ---------------------------------------------------------------------------
# Agent construction — two specialists + a CugaSupervisor
# ---------------------------------------------------------------------------

# Description strings the supervisor LLM uses to route each user turn. Keep
# them action-oriented and mutually exclusive; routing quality is proportional
# to how cleanly these describe the split.
_MAINTAINER_DESC = (
    "Maintainer-side governance: triage issues, review pull requests, draft "
    "changelog entries, compose release notes. Operates under strict policies "
    "(security disclosure escalation, no merge promises, no version "
    "predictions, PII redaction). Route here when the user's request is about "
    "processing an issue/PR or producing release content."
)
_CONTRIBUTOR_DESC = (
    "Contributor-facing replies: welcome comments for first-time contributors, "
    "friendly answers to 'how do I contribute?' questions, encouragement on "
    "new PRs. Operates under a 'welcoming tone required' policy that rewrites "
    "scolding or gatekeeping language. Route here when the user's request is "
    "about addressing a contributor (not processing their artifact)."
)


def make_agents():
    """Construct both specialists and a supervisor that routes between them.

    Returns (supervisor, specialists_dict). Each specialist:
      - has its own _SYSTEM_* prompt scoped to its role
      - owns its own .cuga/ folder (so policy sets are genuinely different)
      - shares the full tool list (repo state is process-global)
    """
    from cuga import CugaAgent, CugaSupervisor
    from _llm import create_llm

    model = create_llm(
        provider=os.getenv("LLM_PROVIDER"),
        model=os.getenv("LLM_MODEL"),
    )

    # The policy storage backend is shared across agent instances in this
    # process. Only the first specialist resets storage on init; the second
    # one merely upserts its own policies into the shared store. Otherwise
    # the second agent's reset would wipe the first's policies.
    maintainer = CugaAgent(
        model=model,
        tools=_make_tools(),
        special_instructions=_SYSTEM_MAINTAINER,
        cuga_folder=str(_SPECIALIST_DIRS["maintainer_steward"]),
        auto_load_policies=True,
        reset_policy_storage=True,    # first specialist: clear any stale state
        filesystem_sync=False,
    )
    maintainer.description = _MAINTAINER_DESC

    contributor = CugaAgent(
        model=model,
        tools=_make_tools(),
        special_instructions=_SYSTEM_CONTRIBUTOR,
        cuga_folder=str(_SPECIALIST_DIRS["contributor_ally"]),
        auto_load_policies=True,
        reset_policy_storage=False,   # second specialist: must NOT reset
        filesystem_sync=False,
    )
    contributor.description = _CONTRIBUTOR_DESC

    specialists: dict[str, CugaAgent] = {
        "maintainer_steward": maintainer,
        "contributor_ally":   contributor,
    }

    supervisor = CugaSupervisor(
        agents=specialists,
        model=model,
        description=(
            "Route every request to exactly one specialist. Use "
            "`maintainer_steward` for anything about processing issues, PRs, "
            "changelogs, or release notes. Use `contributor_ally` for any "
            "reply addressed to a new/first-time contributor (welcomes, "
            "encouragement, 'how do I contribute?' answers). When in doubt "
            "between the two, pick the specialist whose policies are more "
            "relevant to the output the user will see."
        ),
    )
    return supervisor, specialists


# ---------------------------------------------------------------------------
# Policy introspection — list/toggle across all specialists.
#
# Each specialist owns its own policy storage. In the UI we tag every policy
# with the specialist it belongs to, and toggles are routed to the correct
# one via a composite "<specialist>:<policy_id>" identifier.
# ---------------------------------------------------------------------------


def _compose_pid(specialist: str, policy_id: str) -> str:
    return f"{specialist}::{policy_id}"


def _split_pid(composite: str) -> tuple[str, str]:
    if "::" in composite:
        spec, pid = composite.split("::", 1)
        return spec, pid
    return "", composite


def _parse_policy_file(path: Path, sub_to_type: dict[str, str]) -> Optional[dict]:
    """Read a policy markdown file and return (id, name, description, type).
    Source of truth is the filesystem; shared backend storage only carries
    `enabled` state which is looked up separately."""
    try:
        text = path.read_text()
    except Exception:
        return None
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    header = text[3:end]
    name = description = None
    explicit_id = None
    priority = 50
    for line in header.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if k == "name":        name = v
        elif k == "description": description = v
        elif k == "id":        explicit_id = v
        elif k == "priority":
            try: priority = int(v)
            except Exception: pass
    if not name:
        return None
    ptype = sub_to_type.get(path.parent.name, "policy")
    # Default id mirrors the folder_loader's naming: "<type>_<stem>"
    pid = explicit_id or f"{ptype}_{path.stem}"
    return {
        "id":          pid,
        "name":        name,
        "description": description or "",
        "type":        ptype,
        "priority":    priority,
    }


async def _enabled_map_for(agent) -> dict[str, bool]:
    """Return {policy_id: enabled} as known to the shared backend storage."""
    try:
        policy_system = await agent.policies._ensure_policy_system()
        if not policy_system:
            return {}
        policies = await policy_system.storage.list_policies(enabled_only=False)
    except Exception as e:
        log.debug("Could not read enabled map: %s", e)
        return {}
    out: dict[str, bool] = {}
    for p in policies:
        out[getattr(p, "id", "")] = bool(getattr(p, "enabled", True))
    return out


async def _list_policies_snapshot(specialists: dict) -> list[dict]:
    """List policies per specialist by reading each specialist's .cuga/ folder
    on disk. Shared-storage enabled state is merged in.

    CUGA's policy backend storage is a process-wide singleton, so using
    `agent.policies.list()` would double-count (both agents see both sets).
    The filesystem is our authoritative source of ownership.
    """
    sub_to_type = {
        "intent_guards":     "intent_guard",
        "output_formatters": "output_formatter",
        "playbooks":         "playbook",
        "tool_guides":       "tool_guide",
    }
    # enabled map is shared, so reading from any one specialist suffices
    any_agent = next(iter(specialists.values())) if specialists else None
    enabled_map = await _enabled_map_for(any_agent) if any_agent else {}

    out: list[dict] = []
    for spec_name, _agent in specialists.items():
        root = _SPECIALIST_DIRS.get(spec_name)
        if not root or not root.is_dir():
            continue
        for sub in _WATCH_SUBDIRS:
            folder = root / sub
            if not folder.is_dir():
                continue
            for p in sorted(folder.glob("*.md")):
                parsed = _parse_policy_file(p, sub_to_type)
                if not parsed:
                    continue
                out.append({
                    "id":          _compose_pid(spec_name, parsed["id"]),
                    "raw_id":      parsed["id"],
                    "specialist":  spec_name,
                    "name":        parsed["name"],
                    "description": parsed["description"],
                    "type":        parsed["type"],
                    "enabled":     enabled_map.get(parsed["id"], True),
                    "priority":    parsed["priority"],
                })
    return out


async def _set_policy_enabled_on_agent(agent, policy_id: str, enabled: bool) -> bool:
    """Flip the `enabled` flag on a policy and push the update back to storage.

    The PoliciesManager has no `set_enabled` — the supported pattern is
    get → mutate → storage.update_policy(policy) → policy_system.initialize().
    """
    try:
        policy_system = await agent.policies._ensure_policy_system()
        if not policy_system:
            log.warning("No policy system available to toggle %s", policy_id)
            return False

        storage = policy_system.storage
        policy = await storage.get_policy(policy_id)
        if policy is None:
            log.warning("Policy not found: %s", policy_id)
            return False

        policy.enabled = enabled
        await storage.update_policy(policy)
        log.info("Policy %s enabled=%s", policy_id, enabled)
        return True
    except Exception as e:
        log.warning("Failed to toggle policy %s: %s", policy_id, e)
        return False


async def _set_policy_enabled(specialists: dict, composite_id: str, enabled: bool) -> bool:
    """Dispatch a toggle to the specialist that owns the given composite policy id."""
    spec_name, raw_id = _split_pid(composite_id)
    agent = specialists.get(spec_name)
    if not agent:
        log.warning("Unknown specialist in policy id: %s", composite_id)
        return False
    return await _set_policy_enabled_on_agent(agent, raw_id, enabled)


# ---------------------------------------------------------------------------
# Live policy authoring — watch each specialist's .cuga/ for new or modified
# markdown files, reload them into that specialist's storage, and preserve
# runtime toggles.
# ---------------------------------------------------------------------------

_WATCH_SUBDIRS = ("intent_guards", "output_formatters", "playbooks", "tool_guides")

# Tracks mtimes per specialist; first scan establishes baseline without triggering
_watch_state: dict[str, dict[str, float]] = {}
# Last successful reload (unix seconds) — surfaced to the UI
_last_reload_at: float = 0.0


def _scan_specialist_mtimes(cuga_dir: Path) -> dict[str, float]:
    """Return {filepath: mtime} for every markdown file under the watched subdirs
    of a single specialist's .cuga folder."""
    mtimes: dict[str, float] = {}
    for sub in _WATCH_SUBDIRS:
        folder = cuga_dir / sub
        if not folder.is_dir():
            continue
        for p in folder.glob("*.md"):
            try:
                mtimes[str(p)] = p.stat().st_mtime
            except OSError:
                continue
    return mtimes


async def _reload_policies_preserving_toggles_for(spec_name: str, agent, cuga_dir: Path) -> dict:
    """Re-read a single specialist's .cuga markdown and merge into its storage,
    but keep any runtime `enabled=False` toggles the user flipped in the UI.
    """
    global _last_reload_at

    before = {p["raw_id"]: p["enabled"]
              for p in await _list_policies_snapshot({spec_name: agent})}
    try:
        result = await agent.policies.load_from_folder(str(cuga_dir))
    except Exception as e:
        log.warning("Policy reload failed for %s: %s", spec_name, e)
        return {"ok": False, "error": str(e), "specialist": spec_name}

    after = {p["raw_id"]: p["enabled"]
             for p in await _list_policies_snapshot({spec_name: agent})}
    restored = []
    for raw_id, was_enabled in before.items():
        if not was_enabled and after.get(raw_id, True):
            ok = await _set_policy_enabled_on_agent(agent, raw_id, False)
            if ok:
                restored.append(raw_id)

    _last_reload_at = time.time()
    log.info(
        "Policy reload (%s): %d file(s), %d loaded, %d toggle(s) preserved",
        spec_name, len(result.get("files", [])), result.get("count", 0), len(restored),
    )
    return {
        "ok":         True,
        "specialist": spec_name,
        "count":      result.get("count", 0),
        "files":      [os.path.basename(f) for f in result.get("files", [])],
        "errors":     result.get("errors", []),
        "restored":   restored,
    }


async def _reload_all_policies_preserving_toggles(specialists: dict) -> dict:
    """Re-read every specialist and return a combined result."""
    combined = {"ok": True, "per_specialist": []}
    for spec_name, agent in specialists.items():
        combined["per_specialist"].append(
            await _reload_policies_preserving_toggles_for(
                spec_name, agent, _SPECIALIST_DIRS[spec_name]
            )
        )
    return combined


async def _policy_watcher_loop(specialists: dict, interval: float = 2.0) -> None:
    """Background task: poll every specialist's .cuga/ mtimes, reloading only
    the specialist whose folder changed. Deletions are ignored by design."""
    global _watch_state
    _watch_state = {
        name: _scan_specialist_mtimes(_SPECIALIST_DIRS[name])
        for name in specialists
    }
    total = sum(len(m) for m in _watch_state.values())
    log.info(
        "Policy watcher started: monitoring %d file(s) across %d specialist(s)",
        total, len(specialists),
    )

    while True:
        await asyncio.sleep(interval)
        try:
            for spec_name, agent in specialists.items():
                folder = _SPECIALIST_DIRS[spec_name]
                current = _scan_specialist_mtimes(folder)
                prev_map = _watch_state.get(spec_name, {})
                changed = False
                for path, mtime in current.items():
                    prev = prev_map.get(path)
                    if prev is None or mtime > prev + 0.05:
                        log.info("Policy file %s in %s: %s",
                                 "added" if prev is None else "modified",
                                 spec_name, os.path.basename(path))
                        changed = True
                if changed:
                    await _reload_policies_preserving_toggles_for(spec_name, agent, folder)
                _watch_state[spec_name] = current
        except Exception as e:
            log.warning("Policy watcher iteration failed: %s", e)


# ---------------------------------------------------------------------------
# Skill introspection — read SKILL.md files directly for the panel
# ---------------------------------------------------------------------------

def _list_skills_snapshot() -> list[dict]:
    # Skills live under .agents/skills/ (the canonical path on feat/skills-support)
    # and are shared across specialists.
    roots = [_DIR / ".agents" / "skills"]
    out: list[dict] = []
    seen: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("SKILL.md")):
            try:
                text = p.read_text()
            except Exception:
                continue
            name, desc = _parse_skill_frontmatter(text)
            if not name or name in seen:
                continue
            seen.add(name)
            out.append({
                "name":        name,
                "description": desc or "",
                "source":      str(p.relative_to(_DIR)),
            })
    return out


def _parse_skill_frontmatter(text: str) -> tuple[str | None, str | None]:
    if not text.startswith("---"):
        return None, None
    end = text.find("\n---", 3)
    if end == -1:
        return None, None
    header = text[3:end]
    name = desc = None
    for line in header.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if k == "name":
            name = v
        elif k == "description":
            desc = v
    return name, desc


# ---------------------------------------------------------------------------
# Web app
# ---------------------------------------------------------------------------

class AskReq(BaseModel):
    question: str


class TogglePolicyReq(BaseModel):
    policy_id: str
    enabled: bool


class SetRepoReq(BaseModel):
    owner: str
    repo: str
    ref: str = "main"


# ---------------------------------------------------------------------------
# Transcript scraping — extract skill/tool usage from the graph's chat_messages
# ---------------------------------------------------------------------------

_LOAD_SKILL_RE = re.compile(r'load_skill\(\s*["\']([a-zA-Z0-9_\-]+)["\']\s*\)')
_DELEGATE_RE = re.compile(r'delegate_to_([a-zA-Z0-9_]+)\s*\(')


def _extract_routing_from_supervisor(supervisor, thread_id: str) -> str:
    """Return the specialist the supervisor delegated to on this thread.

    The supervisor state uses `supervisor_chat_messages` (not `chat_messages`).
    The LLM emits native tool calls like `delegate_to_<specialist>(task=...)` —
    these live either inside content (when models echo code fences) or on
    AIMessage.tool_calls as structured entries.
    """
    try:
        state = supervisor.graph.get_state({"configurable": {"thread_id": thread_id}})
    except Exception as e:
        log.debug("Could not fetch supervisor state: %s", e)
        return ""
    values = getattr(state, "values", None) or {}
    messages = (
        values.get("supervisor_chat_messages")
        or values.get("chat_messages")
        or values.get("messages")
        or []
    )
    last = ""
    for msg in messages:
        # Case 1: structured tool_calls on AIMessage
        tcs = getattr(msg, "tool_calls", None)
        if tcs:
            for tc in tcs:
                name = ""
                if isinstance(tc, dict):
                    name = tc.get("name") or tc.get("function", {}).get("name", "")
                else:
                    name = getattr(tc, "name", "") or ""
                if isinstance(name, str) and name.startswith("delegate_to_"):
                    last = name[len("delegate_to_"):]
        # Case 2: text content echoes the call
        content = getattr(msg, "content", None)
        if content is None and isinstance(msg, dict):
            content = msg.get("content", "")
        if isinstance(content, str):
            for match in _DELEGATE_RE.findall(content):
                last = match
    return last


def _extract_from_graph_state(
    agent,
    thread_id: str,
    known_tool_names: set[str],
    known_skill_names: set[str],
) -> tuple[list[str], list[str], list[dict], str]:
    """Read the thread's state and pull out:
      - skills loaded via `load_skill("<name>")`
      - tools invoked as `await <tool>(...)`
      - policies that actually fired (from cuga_lite_metadata)
      - a one-line "what the agent decided to do" summary, taken from the
        first substantive assistant message (pre-tool-call narration).
    """
    skills: list[str] = []
    tools: list[str] = []
    fired: list[dict] = []
    reasoning: str = ""

    try:
        state = agent.graph.get_state({"configurable": {"thread_id": thread_id}})
    except Exception as e:
        log.debug("Could not fetch graph state for transcript: %s", e)
        return skills, tools, fired, reasoning

    values = getattr(state, "values", None) or {}
    messages = values.get("chat_messages") or values.get("messages") or []

    for i, msg in enumerate(messages):
        content = getattr(msg, "content", None)
        if content is None and isinstance(msg, dict):
            content = msg.get("content", "")
        if not isinstance(content, str):
            continue

        for match in _LOAD_SKILL_RE.findall(content):
            if match in known_skill_names and match not in skills:
                skills.append(match)

        for name in known_tool_names:
            if re.search(rf'\b{re.escape(name)}\s*\(', content) and name not in tools:
                tools.append(name)

        # First assistant message that mentions a plan — skip the initial user
        # prompt (i==0) and any "Execution output:" echoes from the sandbox.
        if not reasoning and i > 0 and content.strip() and not content.lstrip().startswith("Execution output"):
            # Take the prose BEFORE any code block.
            first = content.split("```", 1)[0].strip()
            if first:
                # One short line: prefer the first sentence, cap at 280 chars.
                line = first.splitlines()[0].strip()
                if len(line) < 40 and len(first.splitlines()) > 1:
                    # one-word intros like "Thinking." — grab the next line too
                    line = " ".join(l.strip() for l in first.splitlines()[:2])
                reasoning = line[:280]

    # Authoritative policy-fire info from cuga_lite_metadata
    meta = values.get("cuga_lite_metadata") or {}
    if meta.get("policy_matched"):
        fired.append({
            "id":           meta.get("policy_id"),
            "name":         meta.get("policy_name"),
            "type":         meta.get("policy_type"),
            "applied":      bool(meta.get("output_formatter_applied", False)),
            "reasoning":    meta.get("policy_reasoning", ""),
            "original":     meta.get("original_response", ""),
            "formatted":    meta.get("formatted_response", ""),
        })

    return skills, tools, fired, reasoning


# ---------------------------------------------------------------------------
# Auto-triage pipeline — background loop that discovers issues on the active
# repo and runs `issue_triage` on each, without human prompting. Every run is
# a *draft*: nothing is posted back to GitHub. Output lands in the Auto-Triage
# queue for the maintainer to review.
# ---------------------------------------------------------------------------

_auto_state: dict[str, Any] = {
    "running":        False,
    "mode":           "idle",      # "idle" | "sample-burst" | "live-poll"
    "polls":          0,
    "processed":      0,
    "errors":         0,
    "last_error":     "",
    "last_poll_at":   0.0,
    "last_event":     "",
    "interval_s":     60,
}

_auto_state_lock = threading.Lock()
_auto_stop_event: asyncio.Event | None = None
_auto_task: asyncio.Task | None = None

# Issues already processed this session: {(kind, owner, repo, number)}
_auto_seen: set[tuple[str, str, str, int]] = set()

# Queue of draft triages the agent produced, most-recent first (capped).
_auto_queue: list[dict] = []


def _auto_snapshot() -> dict:
    with _auto_state_lock:
        s = dict(_auto_state)
    s["queue_len"] = len(_auto_queue)
    with _repo_state_lock:
        s["active_repo"] = {
            "kind": _repo_state["kind"],
            "owner": _repo_state["owner"],
            "repo":  _repo_state["repo"],
        }
    return s


def _auto_event(msg: str) -> None:
    with _auto_state_lock:
        _auto_state["last_event"] = msg


async def _process_one_issue(
    supervisor, specialists: dict,
    kind: str, owner: str, repo: str,
    number: int, title: str,
) -> None:
    """Run triage (via the supervisor) against a single issue and record the draft."""
    key = (kind, owner, repo, number)
    if key in _auto_seen:
        return
    _auto_seen.add(key)

    thread_id = f"auto-{uuid.uuid4().hex[:10]}"
    # Tools are registered identically on both specialists, so a single snapshot works.
    any_agent = next(iter(specialists.values()))
    known_tool_names: set[str] = {
        t.name for t in (any_agent.tool_provider.tools if hasattr(any_agent.tool_provider, "tools") else [])
    }
    known_tool_names.add("load_skill")
    known_skill_names: set[str] = {s["name"] for s in _list_skills_snapshot()}

    prompt = (
        f"Triage {'sample issue' if kind == 'sample' else 'issue'} #{number} "
        f"from the currently active repo."
    )

    _auto_event(f"Triaging #{number} ({title[:60]})…")
    started = time.time()
    try:
        result = await supervisor.invoke(prompt, thread_id=thread_id)
        answer = getattr(result, "answer", None) or str(result)
        error  = getattr(result, "error", None)
    except Exception as e:
        log.exception("Auto-triage invoke failed for #%d", number)
        with _auto_state_lock:
            _auto_state["errors"]    += 1
            _auto_state["last_error"] = f"#{number}: {e}"
        return

    # Figure out which specialist the supervisor routed to, then read that
    # specialist's graph state for tools/skills/policy detail.
    routed_to = _extract_routing_from_supervisor(supervisor, thread_id)
    spec_agent = specialists.get(routed_to) or any_agent
    spec_thread = f"supervisor_conversational_{routed_to}" if routed_to else thread_id

    used_skills, used_tools, fires, reasoning = _extract_from_graph_state(
        spec_agent, spec_thread, known_tool_names, known_skill_names,
    )

    fired_names = [f["name"] for f in fires if f.get("applied")]
    entry = {
        "id":          uuid.uuid4().hex[:8],
        "kind":        kind,
        "owner":       owner,
        "repo":        repo,
        "number":      number,
        "title":       title,
        "answer":      answer,
        "error":       error,
        "skill":       (used_skills or [""])[0],
        "tools":       [t for t in used_tools if t != "load_skill"],
        "fired":       fired_names,
        "reasoning":   reasoning,
        "duration_s":  round(time.time() - started, 1),
        "at":          datetime.now(timezone.utc).isoformat(),
    }
    _auto_queue.insert(0, entry)
    if len(_auto_queue) > 100:
        _auto_queue.pop()

    with _auto_state_lock:
        _auto_state["processed"] += 1

    # Carry routing info so the UI can show which specialist handled this item
    entry["routed_to"] = routed_to

    fired_summary = f" [{', '.join(fired_names)}]" if fired_names else ""
    log.info("Auto-triage #%d done in %.1fs (routed to %s)%s",
             number, entry["duration_s"], routed_to or "?", fired_summary)


def _sample_inbox() -> list[tuple[int, str]]:
    """Read sample issue files and return (number, title) pairs."""
    out: list[tuple[int, str]] = []
    for p in sorted((_SAMPLE / "issues").glob("*.json")):
        try:
            d = json.loads(p.read_text())
            out.append((int(d["number"]), str(d.get("title", ""))))
        except Exception:
            continue
    return out


async def _live_issue_list(owner: str, repo: str, limit: int = 10) -> list[tuple[int, str]]:
    """Return recent open issues on a live repo (excludes PRs)."""
    try:
        def _fetch():
            return _github_api(
                f"/repos/{owner}/{repo}/issues",
                params={"state": "open", "per_page": limit},
            )
        data = await asyncio.to_thread(_fetch)
        return [
            (int(i["number"]), str(i.get("title", "")))
            for i in data if "pull_request" not in i
        ]
    except Exception as e:
        with _auto_state_lock:
            _auto_state["errors"]    += 1
            _auto_state["last_error"] = f"list: {e}"
        return []


async def _auto_loop(supervisor, specialists: dict) -> None:
    """Outer loop: figure out current mode from repo state and dispatch."""
    global _auto_stop_event
    _auto_stop_event = asyncio.Event()
    try:
        while not _auto_stop_event.is_set():
            with _repo_state_lock:
                kind  = _repo_state["kind"]
                owner = _repo_state["owner"]
                repo  = _repo_state["repo"]

            with _auto_state_lock:
                _auto_state["polls"]        += 1
                _auto_state["last_poll_at"]  = time.time()

            if kind == "sample":
                with _auto_state_lock:
                    _auto_state["mode"] = "sample-burst"
                for number, title in _sample_inbox():
                    if _auto_stop_event.is_set():
                        break
                    await _process_one_issue(supervisor, specialists, "sample", "", "", number, title)
                await _wait_or_stop(30.0)

            elif kind == "live" and owner and repo:
                with _auto_state_lock:
                    _auto_state["mode"] = "live-poll"
                inbox = await _live_issue_list(owner, repo, limit=10)
                for number, title in inbox:
                    if _auto_stop_event.is_set():
                        break
                    await _process_one_issue(supervisor, specialists, "live", owner, repo, number, title)
                # Back off per interval
                with _auto_state_lock:
                    iv = _auto_state["interval_s"]
                await _wait_or_stop(float(iv))

            else:
                # No target yet — idle and re-check shortly
                with _auto_state_lock:
                    _auto_state["mode"] = "idle"
                await _wait_or_stop(5.0)
    finally:
        with _auto_state_lock:
            _auto_state["running"] = False
            _auto_state["mode"]    = "idle"
        _auto_event("Stopped.")
        log.info("Auto-triage loop exited")


async def _wait_or_stop(seconds: float) -> None:
    """Sleep `seconds`, but exit early if a stop is requested."""
    if _auto_stop_event is None:
        await asyncio.sleep(seconds)
        return
    try:
        await asyncio.wait_for(_auto_stop_event.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


def _start_auto(supervisor, specialists: dict) -> dict:
    global _auto_task
    with _auto_state_lock:
        if _auto_state["running"]:
            return {"ok": False, "error": "already running"}
        _auto_state["running"]    = True
        _auto_state["last_error"] = ""
    _auto_event("Starting…")
    _auto_task = asyncio.create_task(_auto_loop(supervisor, specialists))
    return {"ok": True}


def _stop_auto() -> dict:
    with _auto_state_lock:
        if not _auto_state["running"]:
            return {"ok": False, "error": "not running"}
    if _auto_stop_event is not None:
        _auto_stop_event.set()
    _auto_event("Stopping…")
    return {"ok": True}


def _clear_auto_queue() -> dict:
    _auto_queue.clear()
    _auto_seen.clear()
    with _auto_state_lock:
        _auto_state["processed"] = 0
        _auto_state["errors"]    = 0
    return {"ok": True}


def _web(port: int) -> None:
    import uvicorn

    supervisor, specialists = make_agents()

    # Trigger one-shot policy load on every specialist, then disable auto-load
    # so toggles made at runtime aren't silently overwritten.
    import asyncio as _asyncio

    async def _init_all():
        for name, agent in specialists.items():
            await agent.policies._ensure_policy_system()
            agent._auto_load_policies = False
            log.info("Initialized policies for specialist: %s", name)
    _asyncio.run(_init_all())

    # Tools are identical across specialists — snapshot once for transcript scraping.
    any_agent = next(iter(specialists.values()))
    known_tool_names: set[str] = {
        t.name for t in (any_agent.tool_provider.tools if hasattr(any_agent.tool_provider, "tools") else [])
    }
    known_tool_names.add("load_skill")

    app = FastAPI(title="Repo Steward")
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    @app.on_event("startup")
    async def _start_watchers():
        asyncio.create_task(_policy_watcher_loop(specialists))

    @app.post("/ask")
    async def api_ask(req: AskReq):
        try:
            # Snapshot skill names so we can match them in the transcript later.
            skills_before: set[str] = {s["name"] for s in _list_skills_snapshot()}

            # Fresh thread_id per turn: clean policy evaluation, no cross-turn bleed.
            thread_id = f"turn-{uuid.uuid4().hex[:10]}"
            result = await supervisor.invoke(req.question, thread_id=thread_id)
            answer = getattr(result, "answer", None) or str(result)

            # Which specialist did the supervisor route to?
            routed_to = _extract_routing_from_supervisor(supervisor, thread_id)
            spec_agent = specialists.get(routed_to) or any_agent
            # The specialist runs inside the supervisor's dispatch with a
            # deterministic thread id keyed on the agent name.
            spec_thread = f"supervisor_conversational_{routed_to}" if routed_to else thread_id

            used_skills, used_tools, fired_policies, reasoning = _extract_from_graph_state(
                spec_agent, spec_thread, known_tool_names, known_skill_names=skills_before,
            )

            # Fallback: answer text mentions the skill by name
            if not used_skills:
                answer_lower = (answer or "").lower()
                for name in skills_before:
                    if name.lower() in answer_lower:
                        used_skills.append(name)

            # Snapshot policies across every specialist, then mark those that
            # fired on the routed one.
            policies_snapshot = await _list_policies_snapshot(specialists)
            policy_events = []
            for p in policies_snapshot:
                fire = None
                if p["specialist"] == routed_to:
                    fire = next(
                        (f for f in fired_policies if f.get("id") == p["raw_id"]),
                        None,
                    )
                if fire:
                    verdict = "fired-applied" if fire["applied"] else "fired"
                elif not p["enabled"]:
                    verdict = "disabled"
                else:
                    verdict = "passed"
                policy_events.append({
                    "id":         p["id"],
                    "specialist": p["specialist"],
                    "name":       p["name"],
                    "type":       p["type"],
                    "enabled":    p["enabled"],
                    "verdict":    verdict,
                    "reasoning":  (fire or {}).get("reasoning", ""),
                })

            entry = _record_turn(
                req.question, answer,
                {"skills": used_skills, "policies": policy_events,
                 "tools": used_tools, "fires": fired_policies,
                 "reasoning": reasoning, "routed_to": routed_to,
                 "sources": []},
            )
            return {"answer": answer, "turn": entry}
        except Exception as exc:
            log.exception("ask failed")
            return JSONResponse({"error": str(exc)}, status_code=500)

    @app.get("/skills")
    async def api_skills():
        return _list_skills_snapshot()

    @app.get("/policies")
    async def api_policies():
        return {
            "policies":       await _list_policies_snapshot(specialists),
            "last_reload_at": _last_reload_at,
        }

    @app.post("/policies/toggle")
    async def api_toggle_policy(req: TogglePolicyReq):
        ok = await _set_policy_enabled(specialists, req.policy_id, req.enabled)
        return {"ok": ok}

    @app.post("/policies/reload")
    async def api_policies_reload():
        return await _reload_all_policies_preserving_toggles(specialists)

    @app.get("/specialists")
    async def api_specialists():
        return [
            {
                "name":        name,
                "description": getattr(agent, "description", ""),
                "policy_dir":  str(_SPECIALIST_DIRS[name]),
            }
            for name, agent in specialists.items()
        ]

    @app.get("/turns")
    async def api_turns():
        return _turn_log

    @app.get("/repo")
    async def api_repo_get():
        with _repo_state_lock:
            return dict(_repo_state)

    @app.post("/repo")
    async def api_repo_set(req: SetRepoReq):
        return _switch_repo(req.owner, req.repo, req.ref)

    @app.post("/repo/reset")
    async def api_repo_reset():
        return _reset_to_sample()

    @app.get("/auto")
    async def api_auto_status():
        return _auto_snapshot()

    @app.get("/auto/queue")
    async def api_auto_queue():
        return _auto_queue

    @app.post("/auto/start")
    async def api_auto_start():
        return _start_auto(supervisor, specialists)

    @app.post("/auto/stop")
    async def api_auto_stop():
        return _stop_auto()

    @app.post("/auto/clear")
    async def api_auto_clear():
        return _clear_auto_queue()

    @app.get("/", response_class=HTMLResponse)
    async def ui():
        return HTMLResponse(_HTML)

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ---------------------------------------------------------------------------
# HTML UI
# ---------------------------------------------------------------------------

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Repo Steward</title>
<style>
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    background:#0f1117;color:#e2e8f0;min-height:100vh}
  header{background:#1a1a2e;border-bottom:1px solid #2d2d4a;padding:14px 28px;
    display:flex;align-items:center;gap:12px;position:sticky;top:0;z-index:10}
  header h1{font-size:16px;font-weight:700;color:#fff}
  .badge{padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;
    background:#1e3a5f;color:#60a5fa}
  .repo-chip{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;
    border-radius:12px;font-size:11px;font-weight:600;background:#1f2937;
    border:1px solid #374151;color:#c5cae9;cursor:pointer;user-select:none;
    transition:all .15s;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
  .repo-chip:hover{background:#27324a;border-color:#4b5563}
  .repo-chip .repo-dot{width:8px;height:8px;border-radius:50%;background:#6b7280}
  .repo-chip.live .repo-dot{background:#4ade80}
  .repo-chip.cloning .repo-dot{background:#fb923c;animation:pulse 1.1s infinite}
  .repo-chip.error .repo-dot{background:#f87171}
  .repo-chip .repo-edit{opacity:.4;font-size:10px}
  .repo-chip:hover .repo-edit{opacity:1}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
  .repo-form{display:none;align-items:center;gap:6px;margin-left:8px}
  .repo-form.vis{display:inline-flex}
  .repo-form input{width:360px;padding:5px 9px;border-radius:5px;font-size:12px;
    background:#0f1117;border:1px solid #374151;color:#e2e8f0;outline:none;
    font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
  .repo-form input:focus{border-color:#2563eb}
  .repo-status{font-size:11px;color:#9ca3af}
  .spacer{flex:1}
  .hdr-stat{font-size:11px;color:#4b5563}

  .layout{display:grid;grid-template-columns:1fr 380px;gap:20px;
    max-width:1400px;margin:0 auto;padding:20px 24px}

  .card{background:#1a1a2e;border:1px solid #2d2d4a;border-radius:10px;
    overflow:hidden;margin-bottom:16px}
  .card-header{padding:12px 16px 10px;border-bottom:1px solid #2d2d4a;
    display:flex;align-items:center;gap:8px}
  .card-header h2{font-size:13px;font-weight:600;color:#c5cae9}
  .reload-stamp{margin-left:auto;font-size:10px;color:#6b7280}
  .reload-stamp.fresh{color:#4ade80}
  .card-body{padding:14px 16px}

  .chips{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:11px}
  .chip{padding:4px 10px;border-radius:12px;font-size:11px;background:#1f2937;
    border:1px solid #374151;color:#9ca3af;cursor:pointer;transition:all .15s}
  .chip:hover{background:#2563eb;border-color:#2563eb;color:#fff}
  .chat-row{display:flex;gap:8px}
  .chat-input{flex:1;padding:8px 12px;border-radius:7px;font-size:13px;
    background:#0f1117;border:1px solid #374151;color:#e2e8f0;outline:none}
  .chat-input:focus{border-color:#2563eb}
  .chat-send{padding:8px 16px;border-radius:7px;font-size:13px;cursor:pointer;
    border:none;background:#2563eb;color:#fff;white-space:nowrap}
  .chat-send:hover{background:#1d4ed8}
  .chat-send:disabled{background:#374151;color:#6b7280;cursor:default}
  .chat-result{margin-top:12px;padding:14px;border-radius:7px;background:#0f1117;
    border:1px solid #2d2d4a;font-size:13px;line-height:1.55;color:#d1d5db;
    white-space:pre-wrap;display:none}
  .chat-result.vis{display:block}

  .list-item{padding:9px 11px;border:1px solid #2d2d4a;border-radius:7px;
    margin-bottom:7px;font-size:12px}
  .list-item .title{font-size:12px;font-weight:600;color:#e2e8f0;margin-bottom:3px}
  .list-item .desc{font-size:11px;color:#9ca3af;line-height:1.4}
  .list-item .meta{font-size:10px;color:#6b7280;margin-top:4px}
  .list-item.used{border-color:#2563eb;background:#0f1f3a}
  .list-item.disabled{opacity:.55}

  .row{display:flex;align-items:center;gap:8px}
  .pill{font-size:10px;padding:1px 7px;border-radius:8px}
  .pill-guard{background:#451a03;color:#fb923c}
  .pill-formatter{background:#1c2e1c;color:#86efac}
  .pill-playbook{background:#2c1a4a;color:#c4b5fd}
  .pill-tool-guide{background:#1e3a5f;color:#93c5fd}
  .pill-other{background:#1f2937;color:#9ca3af}
  .toggle{margin-left:auto;cursor:pointer}

  .empty-state{font-size:12px;color:#4b5563;text-align:center;padding:18px}

  .turn{padding:10px 12px;border:1px solid #2d2d4a;border-radius:7px;
    margin-bottom:7px;font-size:12px}
  .turn .q{color:#93c5fd;font-weight:500;margin-bottom:4px}
  .turn .used-row{display:flex;gap:4px;flex-wrap:wrap;margin-top:4px}
  .turn details{margin-top:8px;border-top:1px dashed #2d2d4a;padding-top:6px}
  .turn details summary{cursor:pointer;font-size:11px;color:#fb923c;
    user-select:none;list-style:none}
  .turn details summary::before{content:"▸ ";color:#fb923c}
  .turn details[open] summary::before{content:"▾ "}
  .turn details.why summary{color:#93c5fd}
  .turn details.why summary::before{color:#93c5fd}
  .why-table{width:100%;margin-top:8px;border-collapse:collapse;font-size:11px}
  .why-table th{text-align:left;vertical-align:top;padding:4px 10px 4px 0;
    color:#6b7280;font-weight:500;width:64px}
  .why-table td{padding:4px 0;color:#d1d5db;vertical-align:top}
  .why-table td code{background:#0a0e16;border:1px solid #2d2d4a;padding:1px 5px;
    border-radius:3px;font-size:11px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:#c5cae9}
  .why-table td.plan{font-style:italic;color:#9ca3af;line-height:1.45}
  .verdict-fired{color:#fb923c;font-weight:500}
  .verdict-disabled{color:#6b7280}
  .verdict-passed{color:#4ade80}

  .spec-row{padding:9px 11px;border:1px solid #2d2d4a;border-radius:7px;
    margin-bottom:7px}
  .spec-row .spec-title{display:flex;align-items:center;gap:8px;margin-bottom:4px}
  .spec-row .spec-name{font-size:12px;font-weight:600;color:#e2e8f0;
    font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
  .spec-row .spec-count{font-size:10px;color:#6b7280}
  .spec-row .spec-last{font-size:10px;color:#4ade80;margin-left:auto}
  .spec-row .spec-desc{font-size:11px;color:#9ca3af;line-height:1.4}
  .spec-pill{font-size:10px;padding:1px 7px;border-radius:8px;
    background:#1f2937;color:#c5cae9;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
  .spec-pill.maintainer_steward{background:#1e3a5f;color:#60a5fa}
  .spec-pill.contributor_ally{background:#452552;color:#e9a4fa}
  .spec-group{margin-bottom:10px}
  .spec-group-head{display:flex;align-items:center;gap:6px;margin:6px 0 7px 0}

  .auto-state{padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600;
    background:#1f2937;color:#6b7280;text-transform:uppercase;letter-spacing:.04em}
  .auto-state.running{background:#052e16;color:#4ade80}
  .auto-state.running::before{content:"●  ";animation:pulse 1.2s infinite}
  .auto-controls{display:flex;gap:6px;margin-bottom:10px}
  .auto-event{font-size:11px;color:#9ca3af;min-height:14px;margin-bottom:8px}
  .auto-item{padding:9px 12px;border:1px solid #2d2d4a;border-radius:7px;
    margin-bottom:7px;font-size:12px}
  .auto-item .auto-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
  .auto-item .issue-num{color:#93c5fd;font-weight:600;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
  .auto-item .issue-title{color:#e2e8f0;flex:1}
  .auto-item .duration{font-size:10px;color:#6b7280}
  .auto-item .kind{font-size:10px;padding:1px 6px;border-radius:6px;
    background:#1f2937;color:#9ca3af}
  .auto-item .kind.live{background:#052e16;color:#4ade80}
  .auto-item .tags{display:flex;gap:4px;margin-top:4px;flex-wrap:wrap}
  .auto-item details{margin-top:6px;border-top:1px dashed #2d2d4a;padding-top:5px}
  .auto-item details summary{font-size:10px;color:#9ca3af;cursor:pointer;list-style:none}
  .auto-item details summary::before{content:"▸ "}
  .auto-item details[open] summary::before{content:"▾ "}
  .auto-item .draft{background:#0a0e16;border:1px solid #2d2d4a;border-radius:5px;
    padding:8px;margin-top:6px;font-size:11px;line-height:1.45;color:#d1d5db;
    white-space:pre-wrap;max-height:240px;overflow-y:auto}
  .diff-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px}
  .diff-col h5{font-size:10px;text-transform:uppercase;letter-spacing:.05em;
    color:#6b7280;margin-bottom:4px;font-weight:600}
  .diff-col h5.rewritten{color:#4ade80}
  .diff-box{background:#0a0e16;border:1px solid #2d2d4a;border-radius:5px;
    padding:8px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
    font-size:11px;line-height:1.45;color:#d1d5db;white-space:pre-wrap;
    word-break:break-word;max-height:220px;overflow-y:auto}
  .diff-box.original{border-color:#451a03}
  .diff-box.formatted{border-color:#0a3a1a}
  .fire-hdr{font-size:11px;color:#fb923c;margin-bottom:4px}
  .fire-hdr .policy-name{color:#e2e8f0;font-weight:600}
</style>
</head>
<body>

<header>
  <h1>🛡️ Repo Steward</h1>
  <span class="badge">OSS maintainer copilot</span>
  <span class="repo-chip" id="repo-chip" onclick="toggleRepoForm()" title="Click to switch repo">
    <span class="repo-dot" id="repo-dot"></span>
    <span id="repo-label">sample repo</span>
    <span class="repo-edit">✎</span>
  </span>
  <div class="repo-form" id="repo-form">
    <input id="repo-input" type="text" placeholder="owner/repo  or  https://github.com/owner/repo"
      onkeydown="if(event.key==='Enter')submitRepo()">
    <button class="btn btn-sm" onclick="submitRepo()">Switch</button>
    <button class="btn btn-sm btn-ghost" onclick="resetRepo()">Sample</button>
    <span class="repo-status" id="repo-form-status"></span>
  </div>
  <div class="spacer"></div>
  <span class="hdr-stat">Skills + policies visible, live</span>
</header>

<div class="layout">

  <!-- Left: chat + turn log -->
  <div>
    <div class="card">
      <div class="card-header"><h2>💬 Ask the Steward</h2></div>
      <div class="card-body">
        <div class="chips">
          <span class="chip" onclick="ask(this.textContent)">Triage sample issue #101</span>
          <span class="chip" onclick="ask(this.textContent)">Triage sample issue #102</span>
          <span class="chip" onclick="ask(this.textContent)">Triage sample issue #103</span>
          <span class="chip" onclick="ask(this.textContent)">Review sample PR #55</span>
          <span class="chip" onclick="ask(this.textContent)">Review sample PR #56</span>
          <span class="chip" onclick="ask(this.textContent)">Write a welcome comment for the author of PR #55</span>
          <span class="chip" onclick="ask(this.textContent)">How do I contribute to this project?</span>
          <span class="chip" onclick="ask(this.textContent)">Draft a changelog entry for PR #55</span>
          <span class="chip" onclick="ask(this.textContent)">Draft release notes for PRs 55, 56, and 57, targeting version 2.0 shipping next week</span>
          <span class="chip" onclick="ask(this.textContent)">When will 2.0 ship?</span>
          <span class="chip" onclick="ask(this.textContent)">Switch to cuga-project/cuga-agent and list the 5 most recent open issues</span>
        </div>
        <div class="chat-row">
          <input class="chat-input" id="chat-input" type="text"
            placeholder="Ask about an issue, PR, or paste a body…"
            onkeydown="if(event.key==='Enter')ask()">
          <button class="chat-send" id="chat-send" onclick="ask()">Send</button>
        </div>
        <div class="chat-result" id="chat-result"></div>
      </div>
    </div>

    <div class="card">
      <div class="card-header"><h2>📜 Recent Turns</h2></div>
      <div class="card-body" id="turns-body">
        <div class="empty-state">No turns yet.</div>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <h2>⚙️ Auto-Triage</h2>
        <span class="auto-state" id="auto-state">off</span>
        <span class="reload-stamp" id="auto-stats"></span>
      </div>
      <div class="card-body">
        <div class="auto-controls">
          <button class="btn btn-sm" id="auto-start" onclick="startAuto()">▶ Start</button>
          <button class="btn btn-sm btn-ghost" id="auto-stop" onclick="stopAuto()" disabled>■ Stop</button>
          <button class="btn btn-sm btn-ghost" onclick="clearAuto()">Clear queue</button>
        </div>
        <div class="auto-event" id="auto-event"></div>
        <div id="auto-queue-body">
          <div class="empty-state">Not running. Start the loop to auto-triage every issue in the active repo.</div>
        </div>
      </div>
    </div>
  </div>

  <!-- Right: routing + skills + policies -->
  <div>
    <div class="card">
      <div class="card-header">
        <h2>🧭 Routing</h2>
        <span class="badge" id="specialists-count">0</span>
      </div>
      <div class="card-body" id="routing-body">
        <div class="empty-state">Loading specialists…</div>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <h2>✨ Skills</h2>
        <span class="badge" id="skills-count">0</span>
      </div>
      <div class="card-body" id="skills-body">
        <div class="empty-state">Loading…</div>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <h2>🛡️ Policies</h2>
        <span class="badge" id="policies-count">0</span>
        <span class="reload-stamp" id="policies-reload"></span>
      </div>
      <div class="card-body" id="policies-body">
        <div class="empty-state">Loading…</div>
      </div>
    </div>
  </div>

</div>

<script>
let _lastUsedSkills = [];

async function init() {
  await Promise.all([loadRouting(), loadSkills(), loadPolicies(), loadTurns(), loadRepo(), loadAuto()]);
  // Poll repo state while a clone is in flight so the dot transitions to green
  setInterval(() => {
    const chip = document.getElementById('repo-chip');
    if (chip && chip.classList.contains('cloning')) loadRepo();
  }, 2000);
  // Poll policies every 3s so newly-authored files show up, and the
  // "reloaded Ns ago" badge ticks forward.
  setInterval(loadPolicies, 3000);
  // Poll auto-triage state + queue every 2s while running.
  setInterval(loadAuto, 2000);
}

async function loadRepo() {
  try {
    const r = await fetch('/repo').then(x => x.json());
    renderRepo(r);
  } catch(e) { /* ignore */ }
}

function renderRepo(r) {
  const chip = document.getElementById('repo-chip');
  const label = document.getElementById('repo-label');
  chip.classList.remove('live','cloning','error');
  if (r.kind === 'live') {
    const ref = r.ref && r.ref !== 'main' ? ('@' + r.ref) : '';
    label.textContent = `${r.owner}/${r.repo}${ref}`;
    chip.classList.add(r.clone_status === 'cloning' ? 'cloning'
                      : r.clone_status === 'error'  ? 'error' : 'live');
    chip.title = r.clone_status === 'cloning' ? 'Cloning in background…'
               : r.clone_status === 'error'   ? ('Clone failed: ' + (r.clone_error||''))
                                              : 'Live repo active — click to switch';
  } else {
    label.textContent = 'sample repo';
    chip.title = 'Offline sample repo — click to switch to a live repo';
  }
}

function toggleRepoForm() {
  const form = document.getElementById('repo-form');
  form.classList.toggle('vis');
  if (form.classList.contains('vis')) {
    document.getElementById('repo-input').focus();
  }
}

function parseRepoSpec(s) {
  s = (s||'').trim();
  if (!s) return null;
  // Accept github.com URL or owner/repo[@ref]
  const m = s.match(/^(?:https?:\/\/github\.com\/)?([^\/\s]+)\/([^\/\s@#?]+?)(?:\.git)?(?:[@#]([^\s]+))?\/?$/);
  if (!m) return null;
  return { owner: m[1], repo: m[2], ref: m[3] || 'main' };
}

async function submitRepo() {
  const input = document.getElementById('repo-input');
  const status = document.getElementById('repo-form-status');
  const spec = parseRepoSpec(input.value);
  if (!spec) { status.textContent = 'Expected owner/repo or a github.com URL'; return; }
  status.textContent = 'Switching…';
  try {
    const r = await fetch('/repo', { method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(spec) }).then(x => x.json());
    if (r.ok) {
      status.textContent = '';
      input.value = '';
      document.getElementById('repo-form').classList.remove('vis');
    } else {
      status.textContent = 'Error: ' + (r.error || 'unknown');
    }
  } catch(e) { status.textContent = 'Error: ' + e.message; }
  await loadRepo();
}

async function resetRepo() {
  try {
    await fetch('/repo/reset', { method:'POST' });
    document.getElementById('repo-form').classList.remove('vis');
  } catch(e) {}
  await loadRepo();
}

async function loadRouting() {
  try {
    const [specs, turns] = await Promise.all([
      fetch('/specialists').then(r => r.json()),
      fetch('/turns').then(r => r.json()),
    ]);
    document.getElementById('specialists-count').textContent = specs.length;
    // Count per-specialist turn usage
    const counts = {}; const lastAt = {};
    (turns||[]).forEach(t => {
      const r = t.routed_to || '';
      if (!r) return;
      counts[r] = (counts[r] || 0) + 1;
      if (!lastAt[r]) lastAt[r] = t.at;
    });
    const body = document.getElementById('routing-body');
    if (!specs.length) {
      body.innerHTML = '<div class="empty-state">No specialists loaded.</div>';
      return;
    }
    body.innerHTML = specs.map(s => {
      const n = counts[s.name] || 0;
      const last = lastAt[s.name] ? ` · last ${relTime(lastAt[s.name])}` : '';
      return `
        <div class="spec-row">
          <div class="spec-title">
            <span class="spec-pill ${esc(s.name)}">${esc(s.name)}</span>
            <span class="spec-count">${n} turn${n === 1 ? '' : 's'}${last}</span>
          </div>
          <div class="spec-desc">${esc(s.description || '')}</div>
        </div>`;
    }).join('');
  } catch(e) { /* ignore */ }
}

function relTime(iso) {
  const then = new Date(iso).getTime();
  const secs = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (secs < 60)   return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs/60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs/3600)}h ago`;
  return `${Math.floor(secs/86400)}d ago`;
}

async function loadSkills() {
  try {
    const skills = await fetch('/skills').then(r => r.json());
    document.getElementById('skills-count').textContent = skills.length;
    const body = document.getElementById('skills-body');
    if (!skills.length) {
      body.innerHTML = '<div class="empty-state">No SKILL.md found under .agents/skills/.</div>';
      return;
    }
    body.innerHTML = skills.map(s => `
      <div class="list-item ${_lastUsedSkills.includes(s.name) ? 'used' : ''}">
        <div class="title">${esc(s.name)}</div>
        <div class="desc">${esc(s.description)}</div>
        <div class="meta">${esc(s.source)}</div>
      </div>`).join('');
  } catch(e) { /* ignore */ }
}

async function loadPolicies() {
  try {
    const envelope = await fetch('/policies').then(r => r.json());
    const policies = envelope.policies || envelope;  // tolerate old shape
    const lastReload = envelope.last_reload_at || 0;
    document.getElementById('policies-count').textContent = policies.length;
    renderReloadStamp(lastReload);
    const body = document.getElementById('policies-body');
    if (!policies.length) {
      body.innerHTML = '<div class="empty-state">No policies loaded.</div>';
      return;
    }
    // Group by specialist so the UI mirrors the per-agent policy scope.
    const groups = {};
    policies.forEach(p => {
      const s = p.specialist || 'default';
      if (!groups[s]) groups[s] = [];
      groups[s].push(p);
    });
    body.innerHTML = Object.entries(groups).map(([spec, plist]) => `
      <div class="spec-group">
        <div class="spec-group-head">
          <span class="spec-pill ${esc(spec)}">${esc(spec)}</span>
          <span class="desc">${plist.length} polic${plist.length === 1 ? 'y' : 'ies'}</span>
        </div>
        ${plist.map(p => {
          const pill = pillFor(p.type);
          return `
            <div class="list-item ${!p.enabled ? 'disabled' : ''}">
              <div class="row">
                <span class="pill ${pill.cls}">${pill.label}</span>
                <span class="title" style="margin:0">${esc(p.name || p.id)}</span>
                <input class="toggle" type="checkbox" ${p.enabled ? 'checked' : ''}
                  onchange="togglePolicy('${esc(p.id)}', this.checked)">
              </div>
              <div class="desc" style="margin-top:4px">${esc(p.description || '')}</div>
            </div>`;
        }).join('')}
      </div>`).join('');
  } catch(e) { /* ignore */ }
}

function renderReloadStamp(ts) {
  const el = document.getElementById('policies-reload');
  if (!el) return;
  if (!ts) { el.textContent = ''; return; }
  const secs = Math.max(0, Math.floor(Date.now()/1000 - ts));
  let label;
  if (secs < 5)   label = 'reloaded just now';
  else if (secs < 60)  label = `reloaded ${secs}s ago`;
  else if (secs < 3600) label = `reloaded ${Math.floor(secs/60)}m ago`;
  else label = `reloaded ${Math.floor(secs/3600)}h ago`;
  el.textContent = label;
  el.classList.toggle('fresh', secs < 5);
}

function pillFor(type) {
  const t = (type || '').toLowerCase();
  if (t.includes('intent')) return { cls: 'pill-guard', label: 'intent-guard' };
  if (t.includes('format')) return { cls: 'pill-formatter', label: 'formatter' };
  if (t.includes('playbook')) return { cls: 'pill-playbook', label: 'playbook' };
  if (t.includes('tool_guide') || t.includes('tool-guide')) return { cls: 'pill-tool-guide', label: 'tool-guide' };
  return { cls: 'pill-other', label: type || 'policy' };
}

async function togglePolicy(id, enabled) {
  try {
    await fetch('/policies/toggle', { method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ policy_id: id, enabled }) });
    await loadPolicies();
  } catch(e) { /* ignore */ }
}

async function loadTurns() {
  try {
    const turns = await fetch('/turns').then(r => r.json());
    const body = document.getElementById('turns-body');
    if (!turns.length) {
      body.innerHTML = '<div class="empty-state">No turns yet.</div>';
      return;
    }
    body.innerHTML = turns.map(t => {
      const rt = t.routed_to ? `<span class="spec-pill ${esc(t.routed_to)}">→ ${esc(t.routed_to)}</span>` : '';
      const sk = (t.skills||[]).map(s => `<span class="pill pill-playbook">skill:${esc(s)}</span>`).join(' ');
      const tl = (t.tools||[]).map(s => `<span class="pill pill-tool-guide">tool:${esc(s)}</span>`).join(' ');
      const fp = (t.policies||[]).filter(p => p.verdict && p.verdict.startsWith('fired'))
        .map(p => `<span class="pill pill-guard">policy:${esc(p.name)}</span>`).join(' ');
      const diff = (t.fires||[]).filter(f => f.applied && f.original && f.formatted).map(f => `
        <details>
          <summary>What the <span class="policy-name">${esc(f.name)}</span> policy rewrote</summary>
          <div class="fire-hdr">${esc(f.reasoning||'')}</div>
          <div class="diff-grid">
            <div class="diff-col">
              <h5>Original draft (blocked)</h5>
              <div class="diff-box original">${esc(f.original)}</div>
            </div>
            <div class="diff-col">
              <h5 class="rewritten">Final output (rewritten)</h5>
              <div class="diff-box formatted">${esc(f.formatted)}</div>
            </div>
          </div>
        </details>`).join('');
      const why = renderWhy(t);
      return `
        <div class="turn">
          <div class="q">${esc(t.question)}</div>
          <div class="used-row">${[rt,sk,tl,fp].filter(Boolean).join(' ') || '<span class="desc">(nothing loaded)</span>'}</div>
          ${why}
          ${diff}
        </div>`;
    }).join('');
  } catch(e) { /* ignore */ }
}

function renderWhy(t) {
  const skill = (t.skills||[])[0] || '(none)';
  const tools = (t.tools||[]).filter(x => x !== 'load_skill');
  const fired = (t.policies||[]).filter(p => (p.verdict||'').startsWith('fired'));
  const disabled = (t.policies||[]).filter(p => p.verdict === 'disabled');
  const passed = (t.policies||[]).filter(p => p.verdict === 'passed');
  const reasoning = (t.reasoning||'').trim();

  const rows = [];
  if (t.routed_to) {
    rows.push(`<tr><th>Routed to</th><td><span class="spec-pill ${esc(t.routed_to)}">${esc(t.routed_to)}</span></td></tr>`);
  }
  rows.push(`<tr><th>Skill</th><td><code>${esc(skill)}</code></td></tr>`);
  rows.push(`<tr><th>Tools</th><td>${tools.length ? tools.map(x=>`<code>${esc(x)}</code>`).join(', ') : '<span class="desc">none</span>'}</td></tr>`);

  const fpart = [];
  if (fired.length)    fpart.push(`<span class="verdict-fired">${fired.length} fired</span>`);
  if (disabled.length) fpart.push(`<span class="verdict-disabled">${disabled.length} disabled</span>`);
  if (passed.length)   fpart.push(`<span class="verdict-passed">${passed.length} passed</span>`);
  rows.push(`<tr><th>Policies</th><td>${fpart.join(' · ') || '<span class="desc">none</span>'}</td></tr>`);

  if (reasoning) {
    rows.push(`<tr><th>Plan</th><td class="plan">${esc(reasoning)}</td></tr>`);
  }

  return `
    <details class="why">
      <summary>Why this turn</summary>
      <table class="why-table">${rows.join('')}</table>
    </details>`;
}

async function ask(question) {
  const inp = document.getElementById('chat-input');
  const res = document.getElementById('chat-result');
  const btn = document.getElementById('chat-send');
  const q = question || inp.value.trim();
  if (!q) return;
  inp.value = q;
  btn.disabled = true; btn.textContent = 'Thinking…';
  res.className = 'chat-result vis';
  res.textContent = 'Thinking…';
  try {
    const r = await fetch('/ask', { method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ question: q }) });
    const d = await r.json();
    res.textContent = d.answer || d.error || '(no response)';
    _lastUsedSkills = (d.turn && d.turn.skills) || [];
    await Promise.all([loadSkills(), loadTurns(), loadRepo(), loadRouting()]);
  } catch(e) { res.textContent = 'Error: ' + e.message; }
  btn.disabled = false; btn.textContent = 'Send';
}

async function loadAuto() {
  try {
    const [state, queue] = await Promise.all([
      fetch('/auto').then(r => r.json()),
      fetch('/auto/queue').then(r => r.json()),
    ]);
    renderAutoState(state);
    renderAutoQueue(queue);
  } catch(e) { /* ignore */ }
}

function renderAutoState(s) {
  const el = document.getElementById('auto-state');
  const stats = document.getElementById('auto-stats');
  const evt = document.getElementById('auto-event');
  const startBtn = document.getElementById('auto-start');
  const stopBtn  = document.getElementById('auto-stop');
  if (s.running) {
    el.textContent = s.mode || 'running';
    el.classList.add('running');
    startBtn.disabled = true;
    stopBtn.disabled = false;
  } else {
    el.textContent = 'off';
    el.classList.remove('running');
    startBtn.disabled = false;
    stopBtn.disabled = true;
  }
  const errs = s.errors || 0;
  stats.textContent =
    `${s.processed || 0} processed · ${s.queue_len || 0} queued` +
    (errs ? ` · ${errs} error${errs === 1 ? '' : 's'}` : '') +
    (s.polls ? ` · ${s.polls} poll${s.polls === 1 ? '' : 's'}` : '');
  evt.textContent = s.last_event || '';
}

function renderAutoQueue(items) {
  const body = document.getElementById('auto-queue-body');
  if (!items || !items.length) {
    body.innerHTML = '<div class="empty-state">Queue empty. Start the loop to auto-triage every issue in the active repo.</div>';
    return;
  }
  body.innerHTML = items.map(i => {
    const rt = i.routed_to ? `<span class="spec-pill ${esc(i.routed_to)}">→ ${esc(i.routed_to)}</span>` : '';
    const sk = i.skill ? `<span class="pill pill-playbook">skill:${esc(i.skill)}</span>` : '';
    const tl = (i.tools||[]).map(x => `<span class="pill pill-tool-guide">tool:${esc(x)}</span>`).join(' ');
    const fp = (i.fired||[]).map(x => `<span class="pill pill-guard">policy:${esc(x)}</span>`).join(' ');
    const kindPill = `<span class="kind ${i.kind === 'live' ? 'live' : ''}">${esc(i.kind)}</span>`;
    const who = i.kind === 'live' && i.owner && i.repo
      ? `<span class="desc">${esc(i.owner)}/${esc(i.repo)}</span>` : '';
    return `
      <div class="auto-item">
        <div class="auto-head">
          ${kindPill}
          <span class="issue-num">#${esc(i.number)}</span>
          <span class="issue-title">${esc(i.title || '(no title)')}</span>
          <span class="duration">${esc(i.duration_s)}s</span>
        </div>
        ${who}
        <div class="tags">${[rt,sk,tl,fp].filter(Boolean).join(' ') || '<span class="desc">(no capture)</span>'}</div>
        <details>
          <summary>Draft triage</summary>
          <div class="draft">${esc(i.answer || i.error || '(no response)')}</div>
        </details>
      </div>`;
  }).join('');
}

async function startAuto() {
  try { await fetch('/auto/start', { method:'POST' }); } catch(e) {}
  await loadAuto();
}
async function stopAuto() {
  try { await fetch('/auto/stop', { method:'POST' }); } catch(e) {}
  await loadAuto();
}
async function clearAuto() {
  try { await fetch('/auto/clear', { method:'POST' }); } catch(e) {}
  await loadAuto();
}

function esc(s) {
  return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#039;');
}

init();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Repo Steward — OSS maintainer copilot")
    parser.add_argument("--port", type=int, default=28822)
    parser.add_argument("--provider", "-p", default=None,
        choices=["rits", "watsonx", "openai", "anthropic", "litellm", "ollama"])
    parser.add_argument("--model", "-m", default=None)
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    print(f"\n  Repo Steward  →  http://127.0.0.1:{args.port}\n")
    _web(args.port)
