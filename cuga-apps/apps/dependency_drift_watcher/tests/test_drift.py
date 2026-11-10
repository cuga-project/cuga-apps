"""
Offline tests for dependency_drift_watcher/drift.py.

No LLM, no network, no API keys: GitHub and PyPI are replaced by fakes, so
these check the app's own logic — repo parsing, safe unpacking of a snapshot,
the two inventories, version specs against PyPI, the Tavily guards and the
findings parser.
"""
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest

_APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_APP_DIR))

import drift  # noqa: E402


# ── parse_repo ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    ("cuga-project/cuga-apps", ("cuga-project/cuga-apps", None)),
    ("psf/requests@v2.32.0", ("psf/requests", "v2.32.0")),
    ("https://github.com/psf/requests", ("psf/requests", None)),
    ("https://github.com/psf/requests.git", ("psf/requests", None)),
    ("github.com/cuga-project/cuga-apps/tree/release/1.0", ("cuga-project/cuga-apps", "release/1.0")),
    ("", (drift.DEFAULT_REPO, None)),
])
def test_parse_repo_accepts(text, expected):
    assert drift.parse_repo(text) == expected


@pytest.mark.parametrize("text", [
    "not a repo", "https://gitlab.com/a/b", "https://github.com/onlyowner",
    "a/b@../etc", "owner/repo@bad ref", "../../etc/passwd",
])
def test_parse_repo_rejects(text):
    with pytest.raises(drift.RepoError):
        drift.parse_repo(text)


# ── fetch_repo: safe unpacking ─────────────────────────────────────────────

def _tarball(members: dict, links: dict | None = None) -> bytes:
    """A gzip tarball with a top folder, like GitHub's codeload archives."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        for name, target in (links or {}).items():
            info = tarfile.TarInfo(name)
            info.type = tarfile.SYMTYPE
            info.linkname = target
            tar.addfile(info)
    return buf.getvalue()


class _FakeStream:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def iter_bytes(self):
        for i in range(0, len(self._body), 4096):
            yield self._body[i:i + 4096]


@pytest.fixture
def fake_github(monkeypatch, tmp_path):
    import httpx
    responses = {}
    monkeypatch.setattr(drift, "_CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(httpx, "stream",
                        lambda method, url, **kw: _FakeStream(*responses.get(url, (404, b""))))
    return responses


def test_fetch_repo_keeps_only_inventory_files_and_never_escapes(fake_github, tmp_path):
    url = "https://codeload.github.com/acme/app/tar.gz/HEAD"
    fake_github[url] = (200, _tarball({
        "app-main/requirements.txt": b"fastapi>=0.110\nmcp>=1.0,<2\n",
        "app-main/pyproject.toml": b'[project]\ndependencies = ["httpx>=0.27"]\n',
        "app-main/src/app.py": b'MODEL = "gpt-4o-mini"\n',
        "app-main/README.md": b"not kept",
        "app-main/node_modules/x/requirements.txt": b"skipped dir\n",
        "app-main/../../escape.py": b"must not be written",
        "/abs/evil.py": b"must not be written",
    }, links={"app-main/link.py": "/etc/passwd"}))

    snap = drift.fetch_repo("acme/app")
    root = Path(snap["root"])
    kept = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
    assert kept == ["pyproject.toml", "requirements.txt", "src/app.py"]
    assert not (tmp_path / "escape.py").exists()
    assert not any(p.is_symlink() for p in root.rglob("*"))
    assert snap["repo"] == "acme/app" and not snap["cached"]
    assert drift.fetch_repo("acme/app")["cached"]          # second call comes from the cache


def test_fetch_repo_missing_or_private(fake_github):
    with pytest.raises(drift.RepoError, match="not found, or it is private"):
        drift.fetch_repo("acme/missing")


def test_fetch_repo_too_big(fake_github, monkeypatch):
    monkeypatch.setattr(drift, "_MAX_MB", 0.001)
    fake_github["https://codeload.github.com/acme/big/tar.gz/HEAD"] = (200, b"x" * 50_000)
    with pytest.raises(drift.RepoError, match="too big"):
        drift.fetch_repo("acme/big")


# ── inventories ───────────────────────────────────────────────────────────

def _write(root: Path, files: dict) -> Path:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return root


def test_inventory_packages_reads_requirements_and_pyproject(tmp_path):
    root = _write(tmp_path, {
        "requirements.txt": "FastAPI>=0.110  # web\nmcp>=1.0,<2\n-r other.txt\ngit+https://x/y\n",
        "apps/a/requirements.txt": "mcp>=1.0\nlangchain_core>=0.3\n",
        "pyproject.toml": ('[project]\ndependencies = ["httpx>=0.27", "pydantic==2.9.0"]\n'
                           '[project.optional-dependencies]\ndev = ["pytest"]\n'),
    })
    inv = drift.inventory_packages(root)
    pkgs = {p["package"]: p for p in inv["packages"]}
    assert set(pkgs) == {"fastapi", "mcp", "langchain-core", "httpx", "pydantic", "pytest"}
    assert pkgs["mcp"]["specs"] == [">=1.0", ">=1.0,<2"] and pkgs["mcp"]["file_count"] == 2
    assert pkgs["pydantic"]["pinned"] and not pkgs["fastapi"]["pinned"]
    assert inv["dependency_files"] == 3
    assert set(drift.inventory_packages(root, only=["MCP"])["packages"][0]["package"].split()) == {"mcp"}


def test_inventory_models_finds_ids_with_locations(tmp_path):
    root = _write(tmp_path, {
        "apps/_llm.py": 'DEFAULT = "openai/gpt-oss-120b"\n',
        "apps/foo/main.py": 'm = "claude-sonnet-4"\nx = "gpt-4o"\n',
    })
    models = {m["model"]: m for m in drift.inventory_models(root)["models"]}
    assert models["openai/gpt-oss-120b"]["shared"] is True
    assert models["claude-sonnet-4"]["apps"] == ["foo"]
    assert models["claude-sonnet-4"]["locations"] == ["apps/foo/main.py:1"]
    assert models["gpt-4o"]["provider"] == "openai"


# ── PyPI ──────────────────────────────────────────────────────────────────

class _FakeResp:
    def __init__(self, status, data=None):
        self.status_code, self._data = status, data or {}

    def json(self):
        return self._data


class _FakeClient:
    def __init__(self, *a, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url):
        name = url.split("/pypi/")[1].split("/")[0]
        if name == "mcp":
            return _FakeResp(200, {"info": {"version": "2.3.0", "project_urls": {"Repository": "https://github.com/x/y"}},
                                   "urls": [{"upload_time_iso_8601": "2026-10-02T00:00:00Z"}]})
        if name == "fastapi":
            return _FakeResp(200, {"info": {"version": "0.162.0"},
                                   "urls": [{"upload_time_iso_8601": "2026-10-23T00:00:00Z"}]})
        return _FakeResp(404)


def test_pypi_latest_flags_blocking_specs(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx, "Client", _FakeClient)
    rows = {r["package"]: r for r in drift.pypi_latest(
        ["mcp", "fastapi", "nope-zz", "Bad Name!"],
        {"mcp": [">=1.0", ">=1.0,<2"], "fastapi": [">=0.110"]})}
    assert rows["mcp"]["latest"] == "2.3.0" and rows["mcp"]["latest_allowed"] is False
    assert rows["mcp"]["blocked_by"] == [">=1.0,<2"]
    assert rows["mcp"]["links"] == {"Repository": "https://github.com/x/y"}
    assert rows["fastapi"]["latest_allowed"] is True and rows["fastapi"]["released"] == "2026-10-23"
    assert rows["nope-zz"]["error"] == "not on PyPI"
    assert rows["Bad Name!"]["error"] == "not a valid package name"


# ── guards and findings ───────────────────────────────────────────────────

def test_egress_guard_blocks_secrets_and_internal_names():
    assert "Tavily key" in drift.egress_violations({"query": "why does tvly-abcdef123 fail"})
    assert "private IP address" in drift.egress_violations({"query": "server 10.1.2.3 down"})
    assert drift.egress_violations({"query": "mcp python sdk 2.0 breaking changes"}) == []


def test_domain_guard_limits_urls_to_pack_domains():
    domains = ["pypi.org", "github.com"]
    assert drift.domain_violation("tavily_extract", {"urls": ["https://evil.example/x"]}, domains)
    assert drift.domain_violation("tavily_extract", {"urls": ["https://docs.github.com/x"]}, domains) is None
    assert drift.domain_violation("tavily_search", {"include_domains": ["reddit.com"]}, domains)


def test_split_findings_parses_and_strips_block():
    answer = ('One package drifted.\n\n```json\n'
              + json.dumps({"findings": [{"dependency": "mcp", "severity": "REVIEW", "kind": "new_version"},
                                         {"severity": "fyi"}]})
              + '\n```')
    clean, findings = drift.split_findings(answer)
    assert clean == "One package drifted."
    assert [(f["dependency"], f["severity"]) for f in findings] == [("mcp", "review")]


# ── grounding ─────────────────────────────────────────────────────────────

def _models_repo(tmp_path):
    return _write(tmp_path, {
        "apps/_llm.py": 'A = "meta-llama/llama-4-scout-17b"\nB = "gpt-4o"\n',
    })


def test_inventory_brief_lists_the_repo_as_fact(tmp_path):
    brief = drift.inventory_brief("models", _models_repo(tmp_path))
    assert set(brief["known"]) == {"meta-llama/llama-4-scout-17b", "gpt-4o"}
    assert "authoritative" in brief["text"] and "apps/_llm.py:1" in brief["text"]


def test_verify_drops_the_fabricated_staging_answer(tmp_path):
    """The real failure on staging: an answer from memory, citing files, models
    and pages the check never touched. None of it may survive."""
    known = drift.inventory_brief("models", _models_repo(tmp_path))["known"]
    fabricated = [
        {"dependency": "claude-3-opus-20240229", "severity": "critical", "source_url": "https://docs.anthropic.com/x",
         "locations": ["apps/assistant.py:22"]},
        {"dependency": "gpt-4o", "severity": "review", "source_url": "https://openai.com/pricing",
         "locations": ["apps/chatbot.py:45"]},
        {"dependency": "llama-2-70b-chat", "severity": "fyi", "source_url": "https://llama.com/x"},
    ]
    kept, dropped = drift.verify_findings(fabricated, known, "models", sources_read=[], pypi_checked=[])
    assert kept == []
    assert [d["reason"] for d in dropped] == ["not a dependency of this repo",
                                             "its source was not read in this check",
                                             "not a dependency of this repo"]


def test_verify_keeps_grounded_findings(tmp_path):
    known = drift.inventory_brief("models", _models_repo(tmp_path))["known"]
    read = ["https://www.ibm.com/docs/en/watsonx/w-and-w/2.3.x?topic=solutions-supported-foundation-models"]
    found = [{"dependency": "meta-llama/llama-4-scout-17b", "severity": "review",
              "source_url": "https://www.ibm.com/docs/en/watsonx/w-and-w/2.3.x?topic=solutions-supported-foundation-models",
              "locations": []},
             {"dependency": "gpt-4o", "severity": "none", "source_url": ""}]
    kept, dropped = drift.verify_findings(found, known, "models", read, [])
    assert [k["dependency"] for k in kept] == ["meta-llama/llama-4-scout-17b", "gpt-4o"] and not dropped
    assert kept[0]["locations"] == ["apps/_llm.py:1"]          # filled from the inventory


def test_verify_accepts_pypi_for_packages_it_looked_up(tmp_path):
    root = _write(tmp_path, {"requirements.txt": "mcp>=1.0,<2\nfastapi\n"})
    known = drift.inventory_brief("packages", root)["known"]
    found = [{"dependency": "mcp (>=1.0,<2)", "severity": "review", "source_url": "https://pypi.org/project/mcp/"},
             {"dependency": "fastapi", "severity": "review", "source_url": "https://pypi.org/project/fastapi/"}]
    kept, dropped = drift.verify_findings(found, known, "packages", sources_read=[], pypi_checked=["mcp"])
    assert [k["dependency"] for k in kept] == ["mcp"]
    assert dropped[0]["dependency"] == "fastapi"                # PyPI not checked for it in this run


def test_render_findings_uses_only_verified_rows():
    text = drift.render_findings([{"dependency": "mcp", "severity": "review", "quote": "2.3.0",
                                   "source_url": "https://pypi.org/project/mcp/", "locations": ["requirements.txt"]},
                                  {"dependency": "fastapi", "severity": "none"}])
    assert "mcp" in text and "fastapi" not in text
    assert drift.render_findings([]).startswith("No verified drift")


def test_pypi_findings_come_from_data_not_the_model(tmp_path):
    root = _write(tmp_path, {"requirements.txt": "mcp>=1.0,<2\nfastapi>=0.110\n"})
    known = drift.inventory_brief("packages", root)["known"]
    rows = [{"package": "mcp", "latest": "2.3.0", "released": "2026-10-02", "blocked_by": [">=1.0,<2"]},
            {"package": "fastapi", "latest": "0.162.0", "latest_allowed": True},
            {"package": "oldlib", "latest": "1.0", "inactive": True}]          # not in the repo
    found = drift.pypi_findings(rows, known)
    assert [(f["dependency"], f["severity"]) for f in found] == [("mcp", "review")]
    assert found[0]["source_url"] == "https://pypi.org/project/mcp/"
    assert found[0]["locations"] == ["requirements.txt"]


def test_no_duplicate_findings(tmp_path):
    root = _write(tmp_path, {"requirements.txt": "httpx\nmcp<2\n"})
    known = drift.inventory_brief("packages", root)["known"]
    row = {"package": "httpx", "latest": "0.28.1", "released": "2024-12-06", "inactive": True}
    assert len(drift.pypi_findings([row, dict(row)], known)) == 1          # PyPI checked twice
    merged = drift.dedupe_findings([{"dependency": "mcp", "severity": "fyi", "kind": "new_version"},
                                    {"dependency": "mcp", "severity": "review", "kind": "breaking"}])
    assert [(f["dependency"], f["severity"]) for f in merged] == [("mcp", "review")]


# ── quotes must be on the cited page ──────────────────────────────────────

_ANTHROPIC_PAGE = """## Model status
| Retirement date | Deprecated model | Recommended replacement |
| October 28, 2025 | `claude-3-5-sonnet-20241022` | `claude-sonnet-5-5` |
| January 5, 2026 | `claude-3-opus-20240229` | `claude-opus-5-1` |"""

_IBM_PAGE = """Foundation model lifecycle. The following models are deprecated and will be withdrawn:
llama-3-2-11b-vision-instruct, withdrawal date 2026-02-01."""


def test_quote_supported_accepts_real_table_quotes():
    # the model's own rendering of a table row: pipes, curly quotes, a non-breaking hyphen
    assert drift.quote_supported("“October 28, 2025 | claude-3-5-sonnet-20241022 | claude‑sonnet‑5‑5”",
                                 _ANTHROPIC_PAGE)


def test_quote_supported_rejects_invented_quotes():
    # the real fabrication from a local run: right page, words not on it
    assert not drift.quote_supported(
        "The gpt-oss-120b model will be retired on 2025-12-01. Please migrate to gpt-oss-130b.", _IBM_PAGE)
    # a real sentence with a changed date is still rejected
    assert not drift.quote_supported("October 28, 2026 | claude-3-5-sonnet-20241022 | claude-sonnet-5-5",
                                     _ANTHROPIC_PAGE)


def test_verify_drops_findings_whose_quote_is_not_on_the_page(tmp_path):
    root = _write(tmp_path, {"apps/a.py": 'A = "claude-3-5-sonnet-20241022"\nB = "openai/gpt-oss-120b"\n'})
    known = drift.inventory_brief("models", root)["known"]
    anth = "https://docs.anthropic.com/en/docs/about-claude/model-deprecations"
    ibm = "https://dataplatform.cloud.ibm.com/docs/content/wsj/analyze-data/fm-model-lifecycle.html"
    found = [{"dependency": "claude-3-5-sonnet-20241022", "severity": "critical", "source_url": anth,
              "quote": "October 28, 2025 | claude-3-5-sonnet-20241022 | claude-sonnet-5-5"},
             {"dependency": "openai/gpt-oss-120b", "severity": "review", "source_url": ibm,
              "quote": "The gpt-oss-120b model will be retired on 2025-12-01. Please migrate to gpt-oss-130b."}]
    kept, dropped = drift.verify_findings(found, known, "models", [anth, ibm], [],
                                          pages={anth: _ANTHROPIC_PAGE, ibm: _IBM_PAGE})
    assert [k["dependency"] for k in kept] == ["claude-3-5-sonnet-20241022"]
    assert dropped[0]["reason"] == "its quote is not on the cited page"


def test_typographic_ids_and_quotes_still_match(tmp_path):
    """The real case from a run: non-breaking hyphens, narrow no-break spaces,
    an arrow instead of a table pipe, and a "(provider)" suffix."""
    root = _write(tmp_path, {"apps/a.py": 'A = "claude-3-5-sonnet-20241022"\n'})
    known = drift.inventory_brief("models", root)["known"]
    url = "https://docs.anthropic.com/en/docs/about-claude/model-deprecations"
    found = [{"dependency": "claude‑3‑5‑sonnet‑20241022 (anthropic)", "severity": "review",
              "source_url": url,
              "quote": "“| October 28, 2025 | claude‑3‑5‑sonnet‑20241022 → claude‑sonnet‑5‑5”"}]
    kept, dropped = drift.verify_findings(found, known, "models", [url], [], pages={url: _ANTHROPIC_PAGE})
    assert [k["dependency"] for k in kept] == ["claude-3-5-sonnet-20241022"] and not dropped


def test_line_mentioning_finds_the_real_row_but_not_replacements():
    url = "https://docs.anthropic.com/x"
    pages = {url: _ANTHROPIC_PAGE + "\n| gpt-4o-mini | 2026-01-01 |"}
    assert drift.line_mentioning("claude-3-5-sonnet-20241022", pages) == (
        url, "| October 28, 2025 | `claude-3-5-sonnet-20241022` | `claude-sonnet-5-5` |")
    assert drift.line_mentioning("claude-sonnet-5-5", pages) is None      # only ever the replacement
    assert drift.line_mentioning("gpt-4o", pages) is None                 # gpt-4o-mini is another model


def test_retyped_quote_is_replaced_by_the_page_line(tmp_path):
    """Real run: the model merged two sentences into a quote that isn't on the page."""
    root = _write(tmp_path, {"apps/a.py": 'A = "claude-3-5-sonnet-20241022"\n'})
    known = drift.inventory_brief("models", root)["known"]
    url = "https://docs.anthropic.com/en/docs/about-claude/model-deprecations"
    found = [{"dependency": "claude-3-5-sonnet-20241022", "severity": "critical", "source_url": url,
              "quote": "On October 28, 2025, Anthropic notified developers using Claude 3-5 Sonnet-20241022"}]
    kept, dropped = drift.verify_findings(found, known, "models", [url], [], pages={url: _ANTHROPIC_PAGE})
    assert not dropped and kept[0]["quote_from"] == "page"
    assert "October 28, 2025" in kept[0]["quote"] and "claude-3-5-sonnet-20241022" in kept[0]["quote"]


def test_severity_comes_from_the_date_in_the_evidence():
    from datetime import date
    today = date(2026, 11, 4)
    row = {"kind": "retirement", "severity": "fyi", "quote_from": "page",
           "quote": "| October 28, 2025 | claude-3-5-sonnet-20241022 | claude-sonnet-5-5 |"}
    assert drift.severity_from_dates(row, today) == "critical"                    # already retired
    soon = {**row, "quote": "withdrawal date 2027-03-01"}
    assert drift.severity_from_dates(soon, today) == "review"                     # within 180 days
    later = {**row, "quote": "Retirement: Dec 1, 2027"}
    assert drift.severity_from_dates(later, today) == "fyi"
    price = {"kind": "price", "severity": "review", "quote": "from January 1, 2026 prices change"}
    assert drift.severity_from_dates(price, today) == "review"                    # not a retirement: unchanged
