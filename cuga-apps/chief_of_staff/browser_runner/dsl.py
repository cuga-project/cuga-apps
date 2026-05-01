"""Browser task DSL — the small, declarative language for browser tools.

A browser task is a YAML/JSON document with a `steps` list. Each step is a
dict with one of a fixed set of action keys. The executor walks them in
order, threading inputs and accumulating extracted outputs.

This is intentionally narrow. Phase 4 v1 supports the 9 actions below,
which cover ~80% of consumer-website automation. Harder things (canvas
interactions, file uploads, multi-tab flows) wait until they're needed.

The DSL is also persistable: the executor takes a list[dict] directly,
so there's no Python-side compile step. Coder-generated browser tasks
land as YAML in the artifact's tool.py-equivalent (we use steps.yaml).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Recognized step actions. Adding new ones is an executor change + a
# small validation update.
ACTIONS = {
    "go_to",            # navigate to a URL              {go_to: <url>}
    "click_text",       # click element matching text    {click_text: <text>}
    "click_selector",   # click element by CSS           {click_selector: <selector>}
    "fill_field",       # type into an input             {fill_field: {selector, value}}
    "wait_for_text",    # wait for text to appear        {wait_for_text: <text>, timeout_ms?}
    "wait_for_selector",# wait for element               {wait_for_selector: <css>, timeout_ms?}
    "extract_text",     # extract text → output dict     {extract_text: {selector, as}}
    "screenshot",       # capture page                   {screenshot: <name>}
    "ensure_logged_in", # require an active session      {ensure_logged_in: <provider>}
    "user_confirm",     # human-in-the-loop pause        {user_confirm: <prompt>}
    "sleep",            # delay                          {sleep: <ms>}
}


@dataclass
class StepResult:
    action: str
    ok: bool
    detail: str = ""
    extracted: dict = field(default_factory=dict)


def validate_steps(steps: list[dict]) -> list[str]:
    """Return a list of error strings; empty if the document is valid."""
    errs: list[str] = []
    for i, step in enumerate(steps or []):
        if not isinstance(step, dict) or len(step) == 0:
            errs.append(f"step {i}: must be a non-empty dict")
            continue
        keys = [k for k in step if k in ACTIONS]
        if len(keys) == 0:
            errs.append(f"step {i}: no recognized action; got keys {list(step)}")
            continue
        if len(keys) > 1:
            errs.append(f"step {i}: multiple actions in one step: {keys}")
    return errs


def required_providers(steps: list[dict]) -> list[str]:
    """Which auth providers does this task need an active session for?
    Used to decide which secrets must be in the vault before exec/probe."""
    out: list[str] = []
    for step in steps or []:
        if "ensure_logged_in" in step:
            p = step["ensure_logged_in"]
            if p and p not in out:
                out.append(p)
    return out


def needs_user_confirm(steps: list[dict]) -> bool:
    return any("user_confirm" in s for s in (steps or []))
