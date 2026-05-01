"""Tests for the OpenAPI source plugin."""

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(_BACKEND))

from acquisition.sources.openapi_source import OpenAPISource  # noqa: E402


@pytest.fixture
def source():
    return OpenAPISource()


@pytest.mark.asyncio
async def test_loads_spec_index(source):
    ids = {e.id for e in source._entries}
    assert "countries" in ids
    assert "open_meteo" in ids
    assert "jokes" in ids


@pytest.mark.asyncio
async def test_propose_country_query(source):
    proposals = await source.propose({"capability": "country information", "expected_output": "country details"})
    assert len(proposals) > 0
    assert proposals[0].id == "openapi:countries"
    assert proposals[0].source == "openapi"


@pytest.mark.asyncio
async def test_propose_weather_query(source):
    proposals = await source.propose({"capability": "weather forecast"})
    ids = [p.id for p in proposals]
    assert "openapi:open_meteo" in ids


@pytest.mark.asyncio
async def test_propose_unrelated_returns_empty(source):
    proposals = await source.propose({"capability": "blockchain xyzzy quantum gibberish"})
    assert all(p.score < 0.5 for p in proposals)


@pytest.mark.asyncio
async def test_realize_returns_complete_spec(source):
    proposals = await source.propose({"capability": "country information"})
    realized = await source.realize(proposals[0])
    assert realized.tool_name == "get_country_by_name"
    assert realized.invoke_method == "GET"
    assert realized.invoke_url.startswith("https://restcountries.com")
    assert "{name}" in realized.invoke_url
    assert realized.sample_input == {"name": "France"}


@pytest.mark.asyncio
async def test_realize_unknown_id_raises(source):
    from acquisition.sources.base import Proposal
    fake = Proposal(
        id="openapi:nope", name="x", description="", capabilities=[],
        source="openapi", score=0.0, spec={"spec_id": "nope", "base_url": "", "preview_endpoint": None},
    )
    with pytest.raises(ValueError):
        await source.realize(fake)
