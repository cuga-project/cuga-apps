"""Tests for the catalog loader + matcher."""

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(_BACKEND))

from acquisition.catalog import Catalog  # noqa: E402


@pytest.fixture
def catalog():
    return Catalog()


def test_catalog_loads_entries(catalog):
    ids = {e.id for e in catalog.entries}
    assert "geo" in ids
    assert "knowledge" in ids
    assert "finance" in ids
    assert "text" in ids


def test_catalog_by_id_returns_entry(catalog):
    geo = catalog.by_id("geo")
    assert geo is not None
    assert geo.kind == "mcp_local"
    assert geo.target == "geo"


def test_catalog_by_id_unknown_returns_none(catalog):
    assert catalog.by_id("does-not-exist") is None


def test_match_weather_picks_geo(catalog):
    proposals = catalog.match({"capability": "weather lookup", "expected_output": "current weather"})
    assert len(proposals) > 0
    assert proposals[0].entry.id == "geo"


def test_match_wikipedia_picks_knowledge(catalog):
    proposals = catalog.match({"capability": "wikipedia search"})
    assert len(proposals) > 0
    assert proposals[0].entry.id == "knowledge"


def test_match_stock_picks_finance(catalog):
    proposals = catalog.match({"capability": "stock quote"})
    assert len(proposals) > 0
    assert proposals[0].entry.id == "finance"


def test_match_empty_gap_returns_no_proposals(catalog):
    assert catalog.match({}) == []


def test_match_unrelated_returns_empty_or_low(catalog):
    proposals = catalog.match({"capability": "blockchain mining quantum xyzzy"})
    # No matches expected, but if any leak through they should be very low.
    for p in proposals:
        assert p.score < 0.5
