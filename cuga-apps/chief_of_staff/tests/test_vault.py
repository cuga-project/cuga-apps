"""Tests for the credentials vault skeleton."""

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(_BACKEND))

from acquisition.vault import Vault  # noqa: E402


@pytest.fixture
def vault(tmp_path):
    v = Vault(tmp_path / "vault.sqlite")
    yield v
    v.close()


def test_put_and_get_round_trip(vault):
    vault.put("stripe", "api_key", "sk_test_xyz")
    assert vault.get("stripe", "api_key") == "sk_test_xyz"


def test_put_overwrites(vault):
    vault.put("stripe", "api_key", "old")
    vault.put("stripe", "api_key", "new")
    assert vault.get("stripe", "api_key") == "new"


def test_get_unknown_returns_none(vault):
    assert vault.get("stripe", "api_key") is None


def test_has_all(vault):
    assert vault.has_all("x", []) is True
    vault.put("x", "a", "1")
    assert vault.has_all("x", ["a"]) is True
    assert vault.has_all("x", ["a", "b"]) is False
    vault.put("x", "b", "2")
    assert vault.has_all("x", ["a", "b"]) is True


def test_delete_specific_key(vault):
    vault.put("x", "a", "1")
    vault.put("x", "b", "2")
    vault.delete("x", "a")
    assert vault.get("x", "a") is None
    assert vault.get("x", "b") == "2"


def test_delete_all_for_tool(vault):
    vault.put("x", "a", "1")
    vault.put("x", "b", "2")
    vault.delete("x")
    assert vault.get("x", "a") is None
    assert vault.get("x", "b") is None


def test_obfuscation_roundtrip_via_db(tmp_path):
    """Stored value should not be plaintext on disk (smoke check, not real
    encryption — phase 3.5 will swap to OS keyring)."""
    import sqlite3
    db = tmp_path / "v.sqlite"
    v = Vault(db)
    v.put("stripe", "api_key", "sk_test_obvious_value")
    v.close()

    raw = sqlite3.connect(db).execute("SELECT value_b64 FROM secrets").fetchone()[0]
    assert "sk_test_obvious_value" not in raw
