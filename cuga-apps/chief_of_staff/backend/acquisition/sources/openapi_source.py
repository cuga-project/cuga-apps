"""OpenAPI source — the phase-3 headline.

Reads a curated spec index, scores each indexed API against the gap, and
returns proposals whose realize() emits a generated tool spec ready for
the adapter to mount. Probe harness gates the registration.

Phase 3 v1 ships with a hardcoded YAML index of no-auth public APIs —
enough to demonstrate the loop end-to-end. Phase 3.5 will swap in
Smithery / openapi-directory search and add credential support.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .base import Proposal, RealizedTool

DEFAULT_INDEX_PATH = Path(__file__).resolve().parent / "spec_index.yaml"

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


@dataclass
class _Endpoint:
    tool_name: str
    description: str
    method: str
    path: str
    params: dict
    probe_input: dict


@dataclass
class _AuthSpec:
    """
    Auth schemes (phase 3.6 + 3.7):
      bearer_token   — single static token, header injection
      api_key_header — single static value in a custom header
      api_key_query  — single static value in a query param
      oauth2_token   — bearer token PLUS optional refresh_token + token_url;
                       adapter refreshes on 401 and persists the new token
    """
    type: str
    secret_key: str                 # primary vault key (access_token for OAuth2)
    header: str | None = None
    param: str | None = None
    prefix: str = ""
    help: str = ""
    # OAuth2-specific:
    refresh_secret_key: str | None = None   # vault key for the refresh token
    token_url: str | None = None            # POST endpoint to refresh
    client_id_key: str | None = None        # vault key for client_id (if needed)
    client_secret_key: str | None = None    # vault key for client_secret (if needed)

    def to_dict(self) -> dict:
        return {
            "type": self.type, "secret_key": self.secret_key,
            "header": self.header, "param": self.param,
            "prefix": self.prefix, "help": self.help,
            "refresh_secret_key": self.refresh_secret_key,
            "token_url": self.token_url,
            "client_id_key": self.client_id_key,
            "client_secret_key": self.client_secret_key,
        }


@dataclass
class _SpecEntry:
    id: str
    name: str
    description: str
    capabilities: list[str]
    base_url: str
    endpoints: list[_Endpoint]
    auth: _AuthSpec | None = None


class OpenAPISource:
    name = "openapi"

    def __init__(self, index_path: Path | str = DEFAULT_INDEX_PATH):
        with open(index_path) as f:
            data = yaml.safe_load(f) or {}
        self._entries: list[_SpecEntry] = []
        for e in data.get("apis", []):
            auth = None
            if e.get("auth"):
                a = e["auth"]
                auth = _AuthSpec(
                    type=a["type"], secret_key=a["secret_key"],
                    header=a.get("header"), param=a.get("param"),
                    prefix=a.get("prefix", ""), help=a.get("help", ""),
                    refresh_secret_key=a.get("refresh_secret_key"),
                    token_url=a.get("token_url"),
                    client_id_key=a.get("client_id_key"),
                    client_secret_key=a.get("client_secret_key"),
                )
            self._entries.append(_SpecEntry(
                id=e["id"], name=e["name"], description=e["description"],
                capabilities=list(e.get("capabilities", [])),
                base_url=e["base_url"],
                endpoints=[
                    _Endpoint(
                        tool_name=ep["tool_name"],
                        description=ep["description"],
                        method=ep.get("method", "GET").upper(),
                        path=ep["path"],
                        params=dict(ep.get("params", {}) or {}),
                        probe_input=dict(ep.get("probe_input", {}) or {}),
                    )
                    for ep in e.get("endpoints", []) or []
                ],
                auth=auth,
            ))

    def by_id(self, entry_id: str) -> _SpecEntry | None:
        return next((e for e in self._entries if e.id == entry_id), None)

    async def propose(self, gap: dict, top_k: int = 3) -> list[Proposal]:
        gap_tokens = _tokenize(
            " ".join([
                gap.get("capability", ""),
                gap.get("expected_output", ""),
                " ".join(gap.get("inputs", []) or []),
            ])
        )
        if not gap_tokens:
            return []

        scored: list[tuple[_SpecEntry, float]] = []
        for entry in self._entries:
            entry_tokens = _tokenize(
                " ".join([entry.name, entry.description] + entry.capabilities)
            )
            overlap = gap_tokens & entry_tokens
            if not overlap:
                continue
            score = len(overlap) / max(len(gap_tokens), 1)
            scored.append((entry, score))

        scored.sort(key=lambda t: t[1], reverse=True)

        proposals: list[Proposal] = []
        for entry, score in scored[:top_k]:
            ep = entry.endpoints[0] if entry.endpoints else None
            spec = {
                "spec_id": entry.id,
                "base_url": entry.base_url,
                "preview_endpoint": ep.tool_name if ep else None,
            }
            if entry.auth is not None:
                spec["auth"] = entry.auth.to_dict()
            proposals.append(
                Proposal(
                    id=f"openapi:{entry.id}",
                    name=entry.name,
                    description=entry.description,
                    capabilities=list(entry.capabilities),
                    source=self.name,
                    score=round(score, 3),
                    auth=[entry.auth.secret_key] if entry.auth else [],
                    spec=spec,
                )
            )
        return proposals

    async def realize(self, proposal: Proposal) -> RealizedTool:
        spec_id = proposal.spec["spec_id"]
        entry = self.by_id(spec_id)
        if entry is None or not entry.endpoints:
            raise ValueError(f"OpenAPI entry {spec_id!r} has no endpoints")
        ep = entry.endpoints[0]

        secrets: list[str] = []
        if entry.auth:
            secrets.append(entry.auth.secret_key)
            # OAuth2 stores refresh + client creds alongside the access token
            # so the adapter can refresh autonomously when the access token
            # expires. UI prompts for all required keys at install time.
            for extra in (entry.auth.refresh_secret_key,
                          entry.auth.client_id_key, entry.auth.client_secret_key):
                if extra:
                    secrets.append(extra)

        return RealizedTool(
            proposal_id=proposal.id,
            tool_name=ep.tool_name,
            description=ep.description,
            invoke_url=f"{entry.base_url.rstrip('/')}{ep.path}",
            invoke_method=ep.method,
            invoke_params=ep.params,
            sample_input=ep.probe_input,
            requires_secrets=secrets,
        )
