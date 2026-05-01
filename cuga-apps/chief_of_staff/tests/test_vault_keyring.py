"""Tests for the keyring backend in the vault."""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "backend"))

from acquisition.vault import Vault  # noqa: E402


@pytest.fixture
def vault(tmp_path):
    v = Vault(tmp_path / "vault.sqlite")
    yield v
    v.close()


def test_default_backend_is_sqlite(vault):
    assert vault.backend_name == "sqlite"


def test_list_keys_empty(vault):
    assert vault.list_keys("foo") == []


def test_list_keys_after_put(vault):
    vault.put("github", "github_token", "ghp_x")
    vault.put("github", "user_name", "octocat")
    assert vault.list_keys("github") == ["github_token", "user_name"]


def test_missing(vault):
    vault.put("openweather", "openweather_api_key", "k")
    assert vault.missing("openweather", ["openweather_api_key"]) == []
    assert vault.missing("openweather", ["openweather_api_key", "extra"]) == ["extra"]
    assert vault.missing("nothing", ["x"]) == ["x"]


def test_all_secrets_for(vault):
    vault.put("a", "k1", "v1")
    vault.put("a", "k2", "v2")
    assert vault.all_secrets_for("a") == {"k1": "v1", "k2": "v2"}


def test_delete_specific_clears_index(vault):
    vault.put("a", "k1", "v1")
    vault.put("a", "k2", "v2")
    vault.delete("a", "k1")
    assert vault.list_keys("a") == ["k2"]
    assert vault.get("a", "k1") is None


def test_delete_all_clears_index(vault):
    vault.put("a", "k1", "v1")
    vault.put("a", "k2", "v2")
    vault.delete("a")
    assert vault.list_keys("a") == []


def test_keyring_unavailable_falls_back_to_sqlite(monkeypatch, tmp_path):
    """If VAULT_BACKEND=keyring but the package can't init, the vault falls
    back gracefully and still works via SQLite."""
    monkeypatch.setenv("VAULT_BACKEND", "keyring")
    # Mock the keyring import to fail.
    import builtins
    real_import = builtins.__import__
    def _fake_import(name, *args, **kwargs):
        if name == "keyring":
            raise ImportError("not installed for this test")
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", _fake_import)

    v = Vault(tmp_path / "v2.sqlite")
    try:
        assert v.backend_name == "sqlite"
        v.put("x", "k", "v")
        assert v.get("x", "k") == "v"
    finally:
        v.close()
