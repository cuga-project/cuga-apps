"""ToolArtifact — the canonical, format-agnostic tool format.

Every tool Toolsmith creates is one ToolArtifact, persisted to disk as a
small bundle:

  data/tools/<id>/
    manifest.yaml   identity + parameters + provenance + auth requirements
    tool.py         single async function the manifest declares as entrypoint
    probe.json      last successful probe (or last failure)

The same artifact compiles to multiple bindings:

  to_langchain_tool()  → cuga consumes this
  to_mcp_tool_spec()   → for /agent/reload's extra_tools list
  to_openapi_path()    → for documentation
  export_zip()         → for sharing across instances

Reusability lives here: artifacts are durable, exportable, and
re-loadable. A backend restart re-mounts every approved artifact.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

log = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass
class ToolManifest:
    id: str
    name: str
    description: str
    parameters_schema: dict
    entry_point: str = "tool.py"
    requires_secrets: list[str] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)
    version: int = 1
    auth: dict | None = None
    # Phase 4 — kind selects the runtime path:
    #   "code"          → adapter exec()s tool.py (default; phase 3.6+)
    #   "browser_task"  → adapter dispatches to browser-runner with steps
    #   "catalog_mount" → adapter loads an MCP server (legacy phase 2)
    kind: str = "code"
    # For browser_task: list of DSL step dicts. Persisted as YAML next to
    # the manifest. None for non-browser tools.
    steps: list[dict] | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ToolManifest":
        return cls(
            id=d["id"],
            name=d["name"],
            description=d.get("description", ""),
            parameters_schema=dict(d.get("parameters_schema") or {}),
            entry_point=d.get("entry_point", "tool.py"),
            requires_secrets=list(d.get("requires_secrets") or []),
            provenance=dict(d.get("provenance") or {}),
            version=int(d.get("version", 1)),
            auth=d.get("auth"),
            kind=d.get("kind", "code"),
            steps=d.get("steps"),
        )


@dataclass
class ToolArtifact:
    manifest: ToolManifest
    code: str
    last_probe: Optional[dict] = None

    def to_summary(self) -> dict:
        """Lightweight view for /tools listing — no code body."""
        return {
            "id": self.manifest.id,
            "name": self.manifest.name,
            "description": self.manifest.description,
            "parameters": self.manifest.parameters_schema,
            "requires_secrets": self.manifest.requires_secrets,
            "provenance": self.manifest.provenance,
            "version": self.manifest.version,
            "last_probe_ok": (self.last_probe or {}).get("ok"),
            "last_probe_at": (self.last_probe or {}).get("at"),
        }

    def to_mcp_tool_spec(self) -> dict:
        """The shape the cuga adapter's _build_extra_tool() consumes."""
        return {
            "id": self.manifest.id,
            "tool_name": self.manifest.name,
            "description": self.manifest.description,
            "invoke_params": self.manifest.parameters_schema,
            "code": self.code,
            "entry_point_function": self.manifest.name,
            "requires_secrets": list(self.manifest.requires_secrets),
            "auth": self.manifest.auth,
            "kind": self.manifest.kind,
            "steps": self.manifest.steps,
        }


def is_valid_id(s: str) -> bool:
    return bool(_NAME_RE.match(s))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Disk persistence
# ---------------------------------------------------------------------------

DEFAULT_TOOLS_DIR = Path(__file__).resolve().parent.parent / "data" / "tools"


class ArtifactStore:
    def __init__(self, root: Path | str = DEFAULT_TOOLS_DIR):
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def save(self, artifact: ToolArtifact) -> Path:
        if not is_valid_id(artifact.manifest.id):
            raise ValueError(f"Invalid artifact id: {artifact.manifest.id!r}")
        dir_ = self._root / artifact.manifest.id
        dir_.mkdir(parents=True, exist_ok=True)
        (dir_ / "manifest.yaml").write_text(yaml.safe_dump(artifact.manifest.to_dict(), sort_keys=False))
        # Phase 4 — browser tasks store DSL steps in steps.yaml; tool.py
        # is just an informational comment. Code-kind artifacts keep using
        # tool.py as the executable.
        if artifact.manifest.kind == "browser_task":
            (dir_ / "steps.yaml").write_text(
                yaml.safe_dump(artifact.manifest.steps or [], sort_keys=False)
            )
            (dir_ / "tool.py").write_text(
                f"# Browser task — see steps.yaml for the DSL. Executed by browser-runner.\n"
                f"# Tool: {artifact.manifest.name}\n"
            )
        else:
            (dir_ / "tool.py").write_text(artifact.code)
        if artifact.last_probe is not None:
            (dir_ / "probe.json").write_text(json.dumps(artifact.last_probe, indent=2))
        return dir_

    def load(self, artifact_id: str) -> Optional[ToolArtifact]:
        dir_ = self._root / artifact_id
        manifest_path = dir_ / "manifest.yaml"
        code_path = dir_ / "tool.py"
        if not manifest_path.exists() or not code_path.exists():
            return None
        manifest = ToolManifest.from_dict(yaml.safe_load(manifest_path.read_text()) or {})
        code = code_path.read_text()
        probe_path = dir_ / "probe.json"
        last_probe = None
        if probe_path.exists():
            try:
                last_probe = json.loads(probe_path.read_text())
            except json.JSONDecodeError:
                pass
        return ToolArtifact(manifest=manifest, code=code, last_probe=last_probe)

    def list_all(self) -> list[ToolArtifact]:
        out: list[ToolArtifact] = []
        for d in sorted(self._root.iterdir()) if self._root.exists() else []:
            if not d.is_dir():
                continue
            artifact = self.load(d.name)
            if artifact is not None:
                out.append(artifact)
        return out

    def remove(self, artifact_id: str) -> bool:
        dir_ = self._root / artifact_id
        if not dir_.exists():
            return False
        for child in dir_.iterdir():
            child.unlink()
        dir_.rmdir()
        return True

    def update_probe(self, artifact_id: str, probe: dict) -> None:
        artifact = self.load(artifact_id)
        if artifact is None:
            return
        probe = {**probe, "at": probe.get("at") or now_iso()}
        artifact.last_probe = probe
        self.save(artifact)


def make_id_from(name: str, source: str = "openapi") -> str:
    """Deterministic id from source + function name."""
    safe = re.sub(r"[^a-z0-9_]", "_", name.lower()).strip("_")
    if not safe:
        safe = "tool"
    return f"{source}__{safe}"
