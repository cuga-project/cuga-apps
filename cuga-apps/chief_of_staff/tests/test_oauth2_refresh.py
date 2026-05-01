"""Tests for the adapter's OAuth2 refresh-on-401 path."""

import asyncio
import sys
import types
from pathlib import Path

import httpx
import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "adapters" / "cuga"))

# Stub heavy imports the adapter pulls in at module load.
for mod in ("_mcp_bridge", "_llm"):
    if mod not in sys.modules:
        sys.modules[mod] = types.ModuleType(mod)

from server import (  # noqa: E402
    _build_extra_tool, _State, set_secret_lookup, _auth_meta,
    _refresh_oauth2_token,
)


def _spec_with_oauth():
    return {
        "id": "openapi__gmail_send_message",
        "tool_name": "gmail_send_message",
        "description": "Send via Gmail.",
        "invoke_params": {"raw": {"type": "string", "required": True}},
        "requires_secrets": [
            "gmail_access_token",
            "gmail_refresh_token",
            "google_oauth_client_id",
            "google_oauth_client_secret",
        ],
        "code": (
            "async def gmail_send_message(raw, gmail_access_token, gmail_refresh_token, "
            "google_oauth_client_id, google_oauth_client_secret):\n"
            "    import httpx\n"
            "    headers = {'Authorization': 'Bearer ' + gmail_access_token}\n"
            "    async with httpx.AsyncClient() as c:\n"
            "        r = await c.post('https://gmail.googleapis.com/gmail/v1/users/me/messages/send',\n"
            "                          headers=headers, json={'raw': raw})\n"
            "        r.raise_for_status()\n"
            "        return r.json()\n"
        ),
        "entry_point_function": "gmail_send_message",
        "auth": {
            "type": "oauth2_token",
            "secret_key": "gmail_access_token",
            "header": "Authorization",
            "prefix": "Bearer ",
            "refresh_secret_key": "gmail_refresh_token",
            "token_url": "https://oauth2.googleapis.com/token",
            "client_id_key": "google_oauth_client_id",
            "client_secret_key": "google_oauth_client_secret",
        },
    }


@pytest.fixture
def oauth_setup(monkeypatch):
    """Wire _State + _auth_meta as if /agent/reload had been called with the OAuth spec."""
    aid = "openapi__gmail_send_message"
    _State.secrets[aid] = {
        "gmail_access_token": "old_access",
        "gmail_refresh_token": "refresh_xyz",
        "google_oauth_client_id": "client123",
        "google_oauth_client_secret": "secret456",
    }
    _auth_meta[aid] = _spec_with_oauth()["auth"]
    set_secret_lookup(lambda tool_id, key: _State.secrets.get(tool_id, {}).get(key))
    yield aid
    _State.secrets.pop(aid, None)
    _auth_meta.pop(aid, None)


@pytest.mark.asyncio
async def test_refresh_oauth2_token_persists_new_access(monkeypatch, oauth_setup):
    aid = oauth_setup

    class _R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"access_token": "new_access", "expires_in": 3600}

    class _Client:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, url, data=None): return _R()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    new = await _refresh_oauth2_token(aid, _auth_meta[aid])
    assert new == "new_access"
    assert _State.secrets[aid]["gmail_access_token"] == "new_access"


@pytest.mark.asyncio
async def test_refresh_returns_none_when_token_url_missing(oauth_setup):
    aid = oauth_setup
    auth = dict(_auth_meta[aid])
    auth.pop("token_url")
    new = await _refresh_oauth2_token(aid, auth)
    assert new is None


@pytest.mark.asyncio
async def test_refresh_returns_none_when_refresh_response_lacks_access_token(monkeypatch, oauth_setup):
    aid = oauth_setup

    class _R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"error": "invalid_grant"}

    class _Client:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, url, data=None): return _R()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    new = await _refresh_oauth2_token(aid, _auth_meta[aid])
    assert new is None


@pytest.mark.asyncio
async def test_invoke_retries_on_401_after_refresh(monkeypatch, oauth_setup):
    aid = oauth_setup

    # Spec uses a custom code body that we control: it raises 401 if the
    # token hasn't been refreshed, then returns success on retry.
    spec = _spec_with_oauth()
    spec["code"] = (
        "import httpx\n"
        "async def gmail_send_message(raw, gmail_access_token, gmail_refresh_token, "
        "google_oauth_client_id, google_oauth_client_secret):\n"
        "    if gmail_access_token == 'old_access':\n"
        "        raise httpx.HTTPStatusError('401', request=None, response=httpx.Response(401))\n"
        "    return {'sent': True, 'token_seen': gmail_access_token}\n"
    )

    class _R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"access_token": "new_access"}
    class _Client:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, url, data=None): return _R()
    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    tool = _build_extra_tool(spec)
    result = await tool.coroutine(raw="hi")
    assert result == {"sent": True, "token_seen": "new_access"}
