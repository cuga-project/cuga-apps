"""
drift.py — the app-specific logic behind Dependency Drift Watcher.

No CUGA here, so it is easy to test:

  * fetch_repo — download a public GitHub repo snapshot (no token) and unpack
    only the files the inventory reads, safely, into a per-repo cache.
  * inventory_models / inventory_packages — scan that snapshot for the models
    and packages it depends on (the "our side" half of the drift).
  * pypi_latest — the latest release of each package on PyPI, and whether the
    repo's version spec still admits it.
  * egress_violations / domain_violation — the guards wrapped around every
    outbound Tavily call: no secrets or internal names leave, and searches stay
    on the active pack's official domains.
  * load_packs — the watch packs (packs/*.yaml).
  * split_findings — pull the agent's ```json findings block out of its answer.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import tarfile
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

import yaml

_DIR = Path(__file__).resolve().parent

DEFAULT_REPO = os.getenv("DDW_DEFAULT_REPO", "cuga-project/cuga-apps")
_CACHE_DIR = Path(os.getenv("DDW_CACHE_DIR") or (_DIR / ".repos"))
_MAX_MB = float(os.getenv("DDW_REPO_MAX_MB", "60"))        # compressed download cap
_MAX_FILES = 4000                                          # files kept after filtering
_MAX_FILE_BYTES = 1_000_000                                # skip anything bigger
_CACHE_TTL_S = 3600                                        # re-download after an hour

_SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist",
    ".cuga", "tests", "test", "site-packages",
}
# Only these files are unpacked: what the two inventories read.
_KEEP = ("*.py", "*.toml", "*.env.example", ".env.example", "requirements*.txt")


# ── Repo snapshots ────────────────────────────────────────────────────────

_REPO_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")
_REF_RE = re.compile(r"^[A-Za-z0-9._/-]{1,100}$")


class RepoError(ValueError):
    """The repo can't be scanned; the message is safe to show the user."""


def parse_repo(text: str) -> tuple[str, str | None]:
    """'owner/repo', 'owner/repo@ref' or a github.com URL → (owner/repo, ref or None)."""
    t = (text or "").strip()
    if not t:
        t = DEFAULT_REPO
    ref = None
    if t.startswith(("http://", "https://", "github.com/", "www.github.com/")):
        u = urlparse(t if "://" in t else "https://" + t)
        if (u.hostname or "").lower() not in ("github.com", "www.github.com"):
            raise RepoError("Only public github.com repositories are supported.")
        parts = [p for p in u.path.split("/") if p]
        if len(parts) < 2:
            raise RepoError("Give the repo as owner/repo or a github.com/owner/repo URL.")
        t = f"{parts[0]}/{parts[1]}"
        if len(parts) >= 4 and parts[2] == "tree":
            ref = "/".join(parts[3:])
    elif "@" in t:
        t, ref = t.split("@", 1)
    t = t.removesuffix(".git")
    if not _REPO_RE.match(t):
        raise RepoError(f"'{text}' is not a GitHub repo. Use owner/repo, e.g. {DEFAULT_REPO}.")
    if ref is not None and (not _REF_RE.match(ref) or ".." in ref):
        raise RepoError("That branch or tag name isn't valid.")
    return t, ref


def _keep(name: str) -> bool:
    path = PurePosixPath(name)
    if any(part in _SKIP_DIRS or (part.startswith(".") and part != ".env.example")
           for part in path.parts[:-1]):
        return False
    return any(path.match(p) for p in _KEEP)


def fetch_repo(text: str) -> dict[str, Any]:
    """Download a public repo snapshot (GitHub's codeload tarball — no token,
    not counted against the API rate limit) and unpack the inventory's files.

    Returns {repo, ref, root, files, fetched_at, cached}. Raises RepoError with
    a message for the user (not found / private, too big, network).
    """
    import httpx

    repo, ref = parse_repo(text)
    key = repo.replace("/", "__") + ("@" + re.sub(r"[^A-Za-z0-9._-]", "_", ref) if ref else "")
    dest = _CACHE_DIR / key
    meta_path = dest / ".ddw.json"
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text())
        if time.time() - meta.get("fetched_ts", 0) < _CACHE_TTL_S:
            return {**meta, "root": str(dest / "src"), "cached": True}

    url = f"https://codeload.github.com/{repo}/tar.gz/{ref or 'HEAD'}"
    limit = int(_MAX_MB * 1024 * 1024)
    buf = io.BytesIO()
    try:
        with httpx.stream("GET", url, timeout=httpx.Timeout(30.0, connect=10.0),
                          follow_redirects=True) as r:
            if r.status_code == 404:
                raise RepoError(f"{repo}{'@' + ref if ref else ''} was not found, or it is private. "
                                "Only public repositories can be scanned.")
            if r.status_code != 200:
                raise RepoError(f"GitHub returned HTTP {r.status_code} for {repo}.")
            for chunk in r.iter_bytes():
                buf.write(chunk)
                if buf.tell() > limit:
                    raise RepoError(f"{repo} is larger than {int(_MAX_MB)} MB; it is too big to scan.")
    except httpx.HTTPError as exc:
        raise RepoError(f"Could not download {repo}: {type(exc).__name__}") from exc

    tmp = dest.with_name(dest.name + f".tmp{os.getpid()}")
    shutil.rmtree(tmp, ignore_errors=True)
    src = tmp / "src"
    src.mkdir(parents=True)
    kept = 0
    buf.seek(0)
    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        for m in tar:
            # Only plain files; drop the top folder (repo-<ref>/); never follow links,
            # never write outside src/.
            if not m.isfile() or m.size > _MAX_FILE_BYTES:
                continue
            if PurePosixPath(m.name).is_absolute():
                continue
            parts = PurePosixPath(m.name).parts[1:]
            if not parts or any(p in ("", "..") or p.startswith("/") for p in parts):
                continue
            rel = "/".join(parts)
            if not _keep(rel):
                continue
            out = (src / rel).resolve()
            if src.resolve() not in out.parents:
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            fh = tar.extractfile(m)
            if fh is None:
                continue
            out.write_bytes(fh.read())
            kept += 1
            if kept >= _MAX_FILES:
                break
    meta = {"repo": repo, "ref": ref or "default branch", "files": kept,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "fetched_ts": time.time(), "url": f"https://github.com/{repo}"}
    (tmp / ".ddw.json").write_text(json.dumps(meta))
    shutil.rmtree(dest, ignore_errors=True)
    tmp.rename(dest)
    return {**meta, "root": str(dest / "src"), "cached": False}


def _walk(root: Path, patterns: tuple[str, ...]):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if any(Path(fn).match(p) for p in patterns):
                yield Path(dirpath) / fn


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _app_of(rel_path: str) -> str | None:
    """The app a file belongs to, for repos laid out as .../apps/<app>/... (cuga-apps)."""
    parts = rel_path.split("/")
    if "apps" in parts[:-2]:
        i = parts.index("apps")
        if not parts[i + 1].startswith("_"):
            return parts[i + 1]
    return None


def _shared(rel_path: str) -> bool:
    """A shared default every app falls back to (cuga-apps: apps/_llm.py, apps/settings.*)."""
    parts = rel_path.split("/")
    return "apps" in parts[:-1] and parts[-2] == "apps" and parts[-1].startswith(("_", "settings"))


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


def inventory_models(root: Path) -> dict[str, Any]:
    """Every model id referenced in code and config, with where it appears."""
    root = Path(root)
    found: dict[str, dict[str, Any]] = {}
    for path in _walk(root, ("*.py", "*.toml", ".env.example", "*.env.example")):
        try:
            lines = path.read_text(errors="ignore").splitlines()
        except OSError:
            continue
        rel = _rel(path, root)
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
                if _shared(rel):
                    entry["shared"] = True
    models = []
    for entry in found.values():
        entry["apps"] = sorted(entry["apps"])
        models.append(entry)
    models.sort(key=lambda e: (-len(e["locations"]), e["model"]))
    return {
        "models": models[:60],
        "note": ("provider is inferred from the model id; locations are capped at 8 per model; "
                 "shared=true means a shared default (e.g. apps/_llm.py or apps/settings.*.toml) "
                 "that every app can fall back to"),
    }


# ── Packages ──────────────────────────────────────────────────────────────

_REQ_LINE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.\-]*)(\[[^\]]*\])?\s*(.*)$")


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _parse_req(line: str) -> tuple[str, str] | None:
    line = line.split("#", 1)[0].strip()
    if not line or line.startswith(("-", "git+", "http://", "https://", "file:")):
        return None
    match = _REQ_LINE.match(line)
    if not match:
        return None
    spec = match.group(3).split(";", 1)[0].replace(" ", "")
    return _norm(match.group(1)), spec


def _pyproject_reqs(path: Path) -> list[str]:
    try:
        data = tomllib.loads(path.read_text(errors="ignore"))
    except (tomllib.TOMLDecodeError, OSError):
        return []
    project = data.get("project") or {}
    reqs = list(project.get("dependencies") or [])
    for extra in (project.get("optional-dependencies") or {}).values():
        reqs.extend(extra or [])
    for group in (data.get("dependency-groups") or {}).values():
        reqs.extend(r for r in group or [] if isinstance(r, str))
    return [r for r in reqs if isinstance(r, str)]


def inventory_packages(root: Path, only: list[str] | None = None) -> dict[str, Any]:
    """Every package in requirements*.txt and pyproject.toml, with its version specs."""
    root = Path(root)
    wanted = {_norm(o) for o in (only or [])}
    found: dict[str, dict[str, Any]] = {}
    files = 0
    for path in _walk(root, ("requirements*.txt", "pyproject.toml")):
        files += 1
        rel = _rel(path, root)
        lines = (_pyproject_reqs(path) if path.name == "pyproject.toml"
                 else path.read_text(errors="ignore").splitlines())
        for raw in lines:
            parsed = _parse_req(raw)
            if not parsed:
                continue
            name, spec = parsed
            if wanted and name not in wanted:
                continue
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
            "files": entry["files"][:6],
            "file_count": len(entry["files"]),
        })
    packages.sort(key=lambda p: (-p["file_count"], p["package"]))
    return {
        "dependency_files": files,
        "packages": packages[:150],
        "total_packages": len(packages),
        "unpinned": sum(1 for p in packages if not p["pinned"]),
    }


# ── PyPI ──────────────────────────────────────────────────────────────────

def pypi_latest(packages: list[str], specs: dict[str, list[str]] | None = None) -> list[dict[str, Any]]:
    """Latest release of each package on PyPI (public JSON API, no token).

    For each: latest version and its upload date, whether every spec the repo
    uses still admits it (False = a pin or cap blocks the upgrade), whether the
    project looks inactive (no release in 18 months) and its changelog/source links.
    """
    import httpx
    from packaging.specifiers import InvalidSpecifier, SpecifierSet
    from packaging.version import InvalidVersion, Version

    specs = {_norm(k): v for k, v in (specs or {}).items()}
    out: list[dict[str, Any]] = []
    with httpx.Client(timeout=8.0, headers={"User-Agent": "cuga-dependency-drift-watcher"}) as client:
        for raw in list(dict.fromkeys(packages))[:40]:
            name = _norm(raw)
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,99}", name):
                out.append({"package": raw, "error": "not a valid package name"})
                continue
            try:
                r = client.get(f"https://pypi.org/pypi/{name}/json")
            except httpx.HTTPError as exc:
                out.append({"package": name, "error": type(exc).__name__})
                continue
            if r.status_code == 404:
                out.append({"package": name, "error": "not on PyPI"})
                continue
            if r.status_code != 200:
                out.append({"package": name, "error": f"HTTP {r.status_code}"})
                continue
            info = r.json().get("info") or {}
            latest = info.get("version") or ""
            files = (r.json().get("urls") or [])
            uploaded = min((f.get("upload_time_iso_8601") or "" for f in files), default="") or None
            row: dict[str, Any] = {"package": name, "latest": latest, "released": (uploaded or "")[:10] or None,
                                   "yanked": bool(info.get("yanked")),
                                   "requires_python": info.get("requires_python")}
            if uploaded:
                try:
                    age = datetime.now(timezone.utc) - datetime.fromisoformat(uploaded.replace("Z", "+00:00"))
                    row["inactive"] = age.days > 548
                except ValueError:
                    pass
            urls = info.get("project_urls") or {}
            links = {k: v for k, v in urls.items()
                     if re.search(r"change|release|history|news|source|repo|github", k, re.I)}
            row["links"] = dict(list(links.items())[:4])
            ours = specs.get(name) or []
            if ours and latest:
                try:
                    v = Version(latest)
                    blocking = [s for s in ours if s and not SpecifierSet(s).contains(v, prereleases=True)]
                    row["our_specs"] = ours
                    row["latest_allowed"] = not blocking
                    if blocking:
                        row["blocked_by"] = blocking
                except (InvalidSpecifier, InvalidVersion):
                    row["our_specs"] = ours
            out.append(row)
    return out


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
