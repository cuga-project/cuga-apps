"""ToolArtifact + ArtifactStore roundtrip."""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from toolsmith.artifact import (  # noqa: E402
    ArtifactStore, ToolArtifact, ToolManifest, is_valid_id, make_id_from,
)


@pytest.fixture
def store(tmp_path):
    return ArtifactStore(tmp_path / "tools")


def _sample_artifact(id_="openapi__get_country") -> ToolArtifact:
    return ToolArtifact(
        manifest=ToolManifest(
            id=id_,
            name="get_country_by_name",
            description="Look up a country by name.",
            parameters_schema={"name": {"type": "string", "required": True}},
            requires_secrets=[],
            provenance={"source": "openapi", "spec_id": "countries"},
        ),
        code="async def get_country_by_name(name):\n    return {'name': name}\n",
        last_probe={"ok": True, "status_code": 200, "response": {"name": "France"}},
    )


def test_save_creates_files(store):
    artifact = _sample_artifact()
    out_dir = store.save(artifact)
    assert (out_dir / "manifest.yaml").exists()
    assert (out_dir / "tool.py").exists()
    assert (out_dir / "probe.json").exists()


def test_load_roundtrip(store):
    original = _sample_artifact()
    store.save(original)

    loaded = store.load(original.manifest.id)
    assert loaded is not None
    assert loaded.manifest.name == original.manifest.name
    assert loaded.manifest.parameters_schema == original.manifest.parameters_schema
    assert loaded.code == original.code
    assert loaded.last_probe["ok"] is True


def test_load_unknown_returns_none(store):
    assert store.load("does-not-exist") is None


def test_list_all(store):
    store.save(_sample_artifact("a"))
    store.save(_sample_artifact("b"))
    items = store.list_all()
    ids = sorted(a.manifest.id for a in items)
    assert ids == ["a", "b"]


def test_remove(store):
    store.save(_sample_artifact())
    assert store.remove("openapi__get_country") is True
    assert store.load("openapi__get_country") is None
    assert store.remove("openapi__get_country") is False


def test_to_summary_omits_code(store):
    artifact = _sample_artifact()
    summary = artifact.to_summary()
    assert "code" not in summary
    assert summary["id"] == "openapi__get_country"
    assert summary["last_probe_ok"] is True


def test_to_mcp_tool_spec_includes_code():
    artifact = _sample_artifact()
    spec = artifact.to_mcp_tool_spec()
    assert spec["tool_name"] == "get_country_by_name"
    assert "code" in spec
    assert spec["entry_point_function"] == "get_country_by_name"


def test_make_id_from_is_filesystem_safe():
    assert make_id_from("Get Country By Name", source="openapi") == "openapi__get_country_by_name"
    assert is_valid_id(make_id_from("Some-Tool!@#", source="cat"))


def test_save_rejects_invalid_id(store):
    bad = ToolArtifact(
        manifest=ToolManifest(id="bad id with spaces", name="x", description="", parameters_schema={}),
        code="",
    )
    with pytest.raises(ValueError):
        store.save(bad)
