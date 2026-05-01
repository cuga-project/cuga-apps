"""Tests for the activations SQLite store."""

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(_BACKEND))

from acquisition.activations import ActivationStore  # noqa: E402


@pytest.fixture
def store(tmp_path):
    s = ActivationStore(tmp_path / "act.sqlite")
    yield s
    s.close()


def test_starts_empty(store):
    assert store.active_ids() == []


def test_approve_persists(store):
    store.approve("geo")
    assert store.active_ids() == ["geo"]


def test_approve_idempotent(store):
    store.approve("geo")
    store.approve("geo")
    assert store.active_ids() == ["geo"]


def test_disable_removes_from_active(store):
    store.approve("geo")
    store.disable("geo")
    assert store.active_ids() == []


def test_re_approve_after_disable(store):
    store.approve("geo")
    store.disable("geo")
    store.approve("geo")
    assert store.active_ids() == ["geo"]


def test_active_ids_ordered_by_approval(store):
    store.approve("knowledge")
    store.approve("geo")
    store.approve("finance")
    assert store.active_ids() == ["knowledge", "geo", "finance"]
