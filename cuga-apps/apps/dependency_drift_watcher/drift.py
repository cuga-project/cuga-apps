"""
drift.py — the app-specific logic behind Dependency Drift Watcher.

Pure functions (no CUGA, no network) so they are easy to test:

  * inventory_models / inventory_packages — scan the repo for the models and
    packages our apps depend on (the "our side" half of the drift).
  * egress_violations / domain_violation — the guards wrapped around every
    outbound Tavily call: no secrets or internal names leave, and searches stay
    on the active pack's official domains.
  * load_packs — the watch packs (packs/*.yaml).
  * split_findings — pull the agent's ```json findings block out of its answer.
"""
from __future__ import annotations

import json
import os
import re
from importlib import metadata
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

_DIR = Path(__file__).resolve().parent

# Repo root to inventory. In the all-in-one image the app runs from /app/apps,
# so the parent of apps/ (/app) holds apps/, mcp_servers/ and requirements files.
# Locally that is the cuga-apps/ directory of the checkout.
REPO_ROOT = Path(os.getenv("DDW_REPO_PATH") or _DIR.parent.parent).resolve()

_SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "ui", "dist",
    ".cuga", "tests", _DIR.name,
}


def _walk(root: Path, patterns: tuple[str, ...]):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if any(Path(fn).match(p) for p in patterns):
                yield Path(dirpath) / fn


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _app_of(rel_path: str) -> str | None:
    parts = rel_path.split("/")
    if len(parts) > 2 and parts[0] == "apps" and not parts[1].startswith("_"):
        return parts[1]
    return None


# ── Models ────────────────────────────────────────────────────────────────

_MODEL_ID = re.compile(
    r"""["'](
        gpt-oss-[\w\-]+ | openai/gpt-oss-[\w\-]+ |
        gpt-[\w.\-]+ | o[134](?:-[\w\-]+)? |
        claude-[\w.\-]+ |
        meta-llama/[\w.\-]+ | llama-\d[\w.\-]*-instruct | llama\d[\w.]*:[\w\-]+ |
        ibm/granite[\w.\-]* | ibm-granite/[\w.\-]+ | granite[\w.\-]*:[\w\-]+ |
        mistralai/[\w.\-]+
    )["']""",
    re.VERBOSE,
)


def _provider_for(model: str) -> str:
    m = model.lower()
    if m.startswith("claude"):
        return "anthropic"
    if ":" in m:
        return "ollama"
    if m.startswith(("meta-llama/", "ibm/", "ibm-granite/", "mistralai/", "openai/gpt-oss", "llama-")):
        return "watsonx"
    if m.startswith("gpt-oss"):
        return "watsonx"
    return "openai"


def inventory_models(root: Path | None = None) -> dict[str, Any]:
    """Every model id referenced in code and config, with where it appears."""
    root = root or REPO_ROOT
    found: dict[str, dict[str, Any]] = {}
    for path in _walk(root, ("*.py", "*.toml", ".env.example", "*.env.example")):
        try:
            lines = path.read_text(errors="ignore").splitlines()
        except OSError:
            continue
        rel = _rel(path)
        for i, line in enumerate(lines, 1):
            for match in _MODEL_ID.finditer(line):
                model = match.group(1)
                entry = found.setdefault(model, {
                    "model": model, "provider": _provider_for(model),
                    "locations": [], "apps": set(), "shared": False,
                })
                if len(entry["locations"]) < 8:
                    entry["locations"].append(f"{rel}:{i}")
                app = _app_of(rel)
                if app:
                    entry["apps"].add(app)
                # apps/_llm.py, apps/settings.*.toml … are shared by every app.
                if rel.startswith("apps/_") or rel.startswith("apps/settings"):
                    entry["shared"] = True
    models = []
    for entry in found.values():
        entry["apps"] = sorted(entry["apps"])
        models.append(entry)
    models.sort(key=lambda e: (-len(e["locations"]), e["model"]))
    return {
        "repo_root": str(root),
        "in_use_now": {"provider": os.getenv("LLM_PROVIDER"), "model": os.getenv("LLM_MODEL")},
        "models": models,
        "note": ("provider is inferred from the model id; locations are capped at 8 per model; "
                 "shared=true means a shared default (apps/_llm.py or apps/settings.*.toml) "
                 "that every app can fall back to"),
    }


# ── Packages ──────────────────────────────────────────────────────────────

_REQ_LINE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.\-]*)(\[[^\]]*\])?\s*(.*)$")


def _installed(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def inventory_packages(root: Path | None = None, only: list[str] | None = None) -> dict[str, Any]:
    """Every package in requirements*.txt, its version specs, and the version
    installed in this running environment (the one actually deployed)."""
    root = root or REPO_ROOT
    wanted = {o.lower().replace("_", "-") for o in (only or [])}
    found: dict[str, dict[str, Any]] = {}
    files = 0
    for path in _walk(root, ("requirements*.txt",)):
        files += 1
        rel = _rel(path)
        for raw in path.read_text(errors="ignore").splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line or line.startswith(("-", "git+", "http")):
                continue
            match = _REQ_LINE.match(line)
            if not match:
                continue
            name = match.group(1).lower().replace("_", "-")
            if wanted and name not in wanted:
                continue
            spec = match.group(3).split(";", 1)[0].replace(" ", "")
            entry = found.setdefault(name, {"package": name, "specs": set(), "files": []})
            if spec:
                entry["specs"].add(spec)
            if rel not in entry["files"]:
                entry["files"].append(rel)
    packages = []
    for entry in found.values():
        specs = sorted(entry["specs"])
        packages.append({
            "package": entry["package"],
            "specs": specs,
            "pinned": any(s.startswith("==") for s in specs),
            "installed": _installed(entry["package"]),
            "files": entry["files"][:6],
            "file_count": len(entry["files"]),
        })
    packages.sort(key=lambda p: (-p["file_count"], p["package"]))
    return {
        "repo_root": str(root),
        "requirements_files": files,
        "packages": packages,
        "unpinned": sum(1 for p in packages if not p["pinned"]),
    }


# ── Packs ─────────────────────────────────────────────────────────────────

def load_packs() -> dict[str, dict[str, Any]]:
    packs = {}
    for path in sorted((_DIR / "packs").glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        packs[data["id"]] = data
    return packs


# ── Guards ────────────────────────────────────────────────────────────────

_SECRET_PATTERNS = [
    ("OpenAI-style key", re.compile(r"\bsk-(?:ant-|proj-|live-)?[A-Za-z0-9_\-]{8,}")),
    ("Tavily key", re.compile(r"\btvly-[A-Za-z0-9_\-]{6,}")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{10,}|\bgithub_pat_[A-Za-z0-9_]{10,}")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("credential assignment", re.compile(r"(?i)\b(?:api[_-]?key|token|secret|password)\s*[:=]\s*\S{8,}")),
]
_INTERNAL_PATTERNS = [
    ("internal host name", re.compile(r"(?i)\b[a-z0-9][\w\-.]*\.(?:internal|local|corp|lan|intranet)\b")),
    ("private IP address", re.compile(
        r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b|\b127\.0\.0\.1\b|\blocalhost\b")),
]


def _extra_internal_terms() -> list[str]:
    raw = os.getenv("DDW_INTERNAL_TERMS", "")
    terms = [t.strip() for t in raw.split(",") if t.strip()]
    for env in ("CE_SUBDOMAIN", "CE_PROJECT_HASH"):
        if os.getenv(env):
            terms.append(os.environ[env])
    return terms


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, (list, tuple, set)):
        for v in value:
            yield from _strings(v)


def egress_violations(args: Any) -> list[str]:
    """Reasons this outbound call must not leave: secrets or internal names in its arguments."""
    reasons: list[str] = []
    extra = [t.lower() for t in _extra_internal_terms()]
    for text in _strings(args):
        for label, pattern in _SECRET_PATTERNS + _INTERNAL_PATTERNS:
            if pattern.search(text) and label not in reasons:
                reasons.append(label)
        low = text.lower()
        for term in extra:
            if term in low and "internal term" not in reasons:
                reasons.append("internal term")
    return reasons


def _host(url: str) -> str:
    try:
        return (urlparse(url if "://" in url else f"https://{url}").hostname or "").lower()
    except ValueError:
        return ""


def _allowed(host: str, domains: list[str]) -> bool:
    host = host.lower().lstrip(".")
    return any(host == d or host.endswith("." + d) for d in (x.lower().lstrip(".") for x in domains))


def domain_violation(tool: str, kwargs: dict[str, Any], domains: list[str]) -> str | None:
    """Return why a Tavily call breaks the pack's source list, or None.

    tavily_search without include_domains is not a violation: the caller
    injects the pack's domains instead (see main._guard_tavily).
    """
    if not domains:
        return None
    if tool == "tavily_search":
        bad = [d for d in kwargs.get("include_domains") or [] if not _allowed(_host(d), domains)]
        return f"include_domains outside the pack: {', '.join(bad)}" if bad else None
    urls: list[str] = []
    if tool == "tavily_extract":
        urls = list(kwargs.get("urls") or [])
    elif tool in ("tavily_crawl", "tavily_map"):
        urls = [kwargs.get("url") or ""]
    bad = [u for u in urls if not _allowed(_host(u), domains)]
    return f"URL outside the pack's sources: {', '.join(bad)}" if bad else None


# ── Findings ──────────────────────────────────────────────────────────────

_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
_SEVERITIES = {"critical", "review", "fyi", "none"}


def split_findings(answer: str) -> tuple[str, list[dict[str, Any]]]:
    """Return (answer without the findings block, parsed findings)."""
    matches = list(_JSON_BLOCK.finditer(answer or ""))
    if not matches:
        return answer, []
    block = matches[-1]
    try:
        data = json.loads(block.group(1))
    except json.JSONDecodeError:
        return answer, []
    raw = data.get("findings") if isinstance(data, dict) else None
    findings = []
    for item in raw or []:
        if not isinstance(item, dict) or not item.get("dependency"):
            continue
        sev = str(item.get("severity", "fyi")).lower()
        findings.append({
            "pack": str(item.get("pack", "")),
            "dependency": str(item["dependency"]),
            "kind": str(item.get("kind", "")),
            "severity": sev if sev in _SEVERITIES else "fyi",
            "summary": str(item.get("summary", "")),
            "quote": str(item.get("quote", "")),
            "source_url": str(item.get("source_url", "")),
            "effective_date": item.get("effective_date"),
            "locations": [str(x) for x in item.get("locations") or []][:8],
            "recommendation": str(item.get("recommendation", "")),
        })
    clean = (answer[:block.start()] + answer[block.end():]).strip()
    return clean, findings


_URL = re.compile(r"https?://[^\s\"'<>)\]]+")


def urls_in(text: Any, limit: int = 12) -> list[str]:
    out: list[str] = []
    for s in _strings(text):
        for u in _URL.findall(s):
            u = u.rstrip(".,;")
            if u not in out:
                out.append(u)
            if len(out) >= limit:
                return out
    return out
