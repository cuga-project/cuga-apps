"""Tests for the SQLite tool registry."""

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(_BACKEND))

from registry.store import ToolRecord, ToolRegistry  # noqa: E402


@pytest.fixture
def registry(tmp_path):
    db = tmp_path / "test.sqlite"
    r = ToolRegistry(db)
    yield r
    r.close()


def test_upsert_and_all(registry):
    rec = ToolRecord(
        id="mcp_server:web_search",
        name="web_search",
        source="mcp_server",
        description="Search the web.",
        spec={"adapter_url": "http://localhost:8000"},
    )
    registry.upsert(rec)
    items = registry.all()
    assert len(items) == 1
    assert items[0].name == "web_search"
    assert items[0].spec == {"adapter_url": "http://localhost:8000"}
    assert items[0].installed_at  # auto-populated


def test_upsert_replaces_existing(registry):
    rec = ToolRecord(
        id="mcp_server:foo",
        name="foo",
        source="mcp_server",
        description="v1",
        spec={},
    )
    registry.upsert(rec)
    rec.description = "v2"
    registry.upsert(rec)
    items = registry.all()
    assert len(items) == 1
    assert items[0].description == "v2"


def test_replace_source_only_affects_that_source(registry):
    registry.upsert(ToolRecord(id="mcp_server:a", name="a", source="mcp_server", description="", spec={}))
    registry.upsert(ToolRecord(id="acquired:b", name="b", source="acquired_openapi", description="", spec={}))

    registry.replace_source("mcp_server", [
        ToolRecord(id="mcp_server:c", name="c", source="mcp_server", description="", spec={}),
    ])

    items = {r.id for r in registry.all()}
    assert items == {"mcp_server:c", "acquired:b"}
