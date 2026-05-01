"""BrowserSource — phase 4 plugin that proposes browser-driven tools.

Sibling of OpenAPISource. Reads a curated YAML of browser task templates,
matches gaps via token overlap, returns proposals whose realize() emits
a browser_task spec ready for the cuga adapter to mount via the
browser-runner.

Phase 4 v1 ships only the curated path. Phase 4.5+ would add a
BrowserScriptCoder that generates new templates on the fly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .base import Proposal, RealizedTool

DEFAULT_TASKS_PATH = Path(__file__).resolve().parent / "browser_tasks.yaml"

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


@dataclass
class _BrowserTask:
    id: str
    name: str
    description: str
    capabilities: list[str]
    parameters: dict
    secrets: list[str]
    steps: list[dict]


class BrowserSource:
    name = "browser"

    def __init__(self, path: Path | str = DEFAULT_TASKS_PATH):
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        self._tasks: list[_BrowserTask] = [
            _BrowserTask(
                id=t["id"], name=t["name"], description=t["description"],
                capabilities=list(t.get("capabilities", [])),
                parameters=dict(t.get("parameters", {}) or {}),
                secrets=list(t.get("secrets", []) or []),
                steps=list(t.get("steps", []) or []),
            )
            for t in data.get("tasks", [])
        ]

    def by_id(self, task_id: str) -> _BrowserTask | None:
        return next((t for t in self._tasks if t.id == task_id), None)

    async def propose(self, gap: dict, top_k: int = 3) -> list[Proposal]:
        gap_tokens = _tokenize(
            " ".join([
                gap.get("capability", ""),
                gap.get("expected_output", ""),
                " ".join(gap.get("inputs", []) or []),
            ])
        )
        if not gap_tokens:
            return []

        scored: list[tuple[_BrowserTask, float]] = []
        for task in self._tasks:
            tokens = _tokenize(" ".join([task.name, task.description] + task.capabilities))
            overlap = gap_tokens & tokens
            if not overlap:
                continue
            score = len(overlap) / max(len(gap_tokens), 1)
            scored.append((task, score))

        scored.sort(key=lambda t: t[1], reverse=True)
        out: list[Proposal] = []
        for task, score in scored[:top_k]:
            spec = {
                "task_id": task.id,
                "needs_user_confirm": any("user_confirm" in s for s in task.steps),
                "step_count": len(task.steps),
            }
            out.append(Proposal(
                id=f"browser:{task.id}", name=task.name, description=task.description,
                capabilities=list(task.capabilities), source=self.name,
                score=round(score, 3), auth=list(task.secrets), spec=spec,
            ))
        return out

    async def realize(self, proposal: Proposal) -> RealizedTool:
        task_id = proposal.spec["task_id"]
        task = self.by_id(task_id)
        if task is None:
            raise ValueError(f"unknown browser task id: {task_id!r}")
        return RealizedTool(
            proposal_id=proposal.id,
            tool_name=task.id,
            description=task.description,
            invoke_url=None,
            invoke_method="POST",
            invoke_params=task.parameters,
            sample_input=_build_sample_input(task),
            requires_secrets=list(task.secrets),
        )


def _build_sample_input(task: _BrowserTask) -> dict:
    """Phase 4 v1 — synthesize a probe input from parameter defaults
    + lightweight heuristics. Tests can override."""
    out: dict = {}
    for name, info in task.parameters.items():
        info = info or {}
        if "default" in info:
            out[name] = info["default"]
        elif info.get("type") == "string":
            out[name] = "test"
        elif info.get("type") == "integer":
            out[name] = 1
        elif info.get("type") == "number":
            out[name] = 1.0
        elif info.get("type") == "boolean":
            out[name] = True
    return out
