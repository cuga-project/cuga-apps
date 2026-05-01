"""Credentials vault — phase 3.6.

Two backends:
  - keyring   (preferred) — OS-level secret store via the `keyring` package
                            (macOS Keychain, Linux Secret Service, Windows
                            Credential Manager). Used when VAULT_BACKEND=keyring
                            and the package + a working backend are available.
  - sqlite    (default)   — SQLite + base64-XOR. Process-local obfuscation,
                            NOT real encryption — fine for local dev and CI.

Both backends expose the same API. Switch via env: VAULT_BACKEND=keyring|sqlite.
"""

from __future__ import annotations

import base64
import logging
import os
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "vault.sqlite"
_KEYRING_NAMESPACE = "chief-of-staff"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS secrets (
    tool_id     TEXT NOT NULL,
    secret_key  TEXT NOT NULL,
    value_b64   TEXT NOT NULL,
    PRIMARY KEY (tool_id, secret_key)
);
CREATE TABLE IF NOT EXISTS secret_keys (
    tool_id    TEXT NOT NULL,
    secret_key TEXT NOT NULL,
    PRIMARY KEY (tool_id, secret_key)
);
"""


class _KeyringBackend:
    """OS keyring delegate. Falls back to raising RuntimeError if the
    keyring package is unavailable or has no working backend."""

    def __init__(self):
        try:
            import keyring  # type: ignore[import-not-found]
            # Probe to fail fast on misconfigured backends.
            keyring.get_password(_KEYRING_NAMESPACE, "_probe_")
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"keyring backend unavailable: {exc}") from exc
        import keyring  # noqa: F811
        self._kr = keyring

    @staticmethod
    def _slot(tool_id: str, secret_key: str) -> str:
        return f"{tool_id}::{secret_key}"

    def put(self, tool_id, secret_key, value):
        self._kr.set_password(_KEYRING_NAMESPACE, self._slot(tool_id, secret_key), value)

    def get(self, tool_id, secret_key):
        return self._kr.get_password(_KEYRING_NAMESPACE, self._slot(tool_id, secret_key))

    def delete(self, tool_id, secret_key):
        try:
            self._kr.delete_password(_KEYRING_NAMESPACE, self._slot(tool_id, secret_key))
        except self._kr.errors.PasswordDeleteError:
            pass

    def name(self) -> str:
        return "keyring"


class Vault:
    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        # SQLite obfuscation key — used only when the keyring backend isn't.
        self._key = (os.environ.get("VAULT_KEY") or "chief-of-staff-vault").encode()
        # Pick a backend.
        self._kr_backend = self._pick_keyring_backend()

    @staticmethod
    def _pick_keyring_backend():
        if os.environ.get("VAULT_BACKEND", "sqlite").lower() != "keyring":
            return None
        try:
            return _KeyringBackend()
        except RuntimeError as exc:
            log.warning("Falling back to sqlite vault — %s", exc)
            return None

    @property
    def backend_name(self) -> str:
        return self._kr_backend.name() if self._kr_backend else "sqlite"

    def put(self, tool_id: str, secret_key: str, value: str) -> None:
        # Always record that this (tool, key) exists so has_all / list_keys
        # work the same regardless of backend.
        self._conn.execute(
            "INSERT OR IGNORE INTO secret_keys (tool_id, secret_key) VALUES (?, ?)",
            (tool_id, secret_key),
        )
        if self._kr_backend is not None:
            self._kr_backend.put(tool_id, secret_key, value)
        else:
            encoded = base64.b64encode(self._xor(value.encode())).decode()
            self._conn.execute(
                """
                INSERT INTO secrets (tool_id, secret_key, value_b64) VALUES (?, ?, ?)
                ON CONFLICT(tool_id, secret_key) DO UPDATE SET value_b64 = excluded.value_b64
                """,
                (tool_id, secret_key, encoded),
            )
        self._conn.commit()

    def get(self, tool_id: str, secret_key: str) -> str | None:
        if self._kr_backend is not None:
            return self._kr_backend.get(tool_id, secret_key)
        row = self._conn.execute(
            "SELECT value_b64 FROM secrets WHERE tool_id = ? AND secret_key = ?",
            (tool_id, secret_key),
        ).fetchone()
        if row is None:
            return None
        return self._xor(base64.b64decode(row["value_b64"])).decode()

    def has(self, tool_id: str, secret_key: str) -> bool:
        return self.get(tool_id, secret_key) is not None

    def has_all(self, tool_id: str, required: list[str]) -> bool:
        if not required:
            return True
        return all(self.has(tool_id, k) for k in required)

    def missing(self, tool_id: str, required: list[str]) -> list[str]:
        return [k for k in required if not self.has(tool_id, k)]

    def list_keys(self, tool_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT secret_key FROM secret_keys WHERE tool_id = ? ORDER BY secret_key",
            (tool_id,),
        ).fetchall()
        return [r["secret_key"] for r in rows]

    def all_secrets_for(self, tool_id: str) -> dict[str, str]:
        """Return every secret value for a tool. Used by the orchestrator
        when assembling the adapter's reload payload."""
        out: dict[str, str] = {}
        for key in self.list_keys(tool_id):
            val = self.get(tool_id, key)
            if val is not None:
                out[key] = val
        return out

    def delete(self, tool_id: str, secret_key: str | None = None) -> None:
        if secret_key is None:
            keys = self.list_keys(tool_id)
            if self._kr_backend is not None:
                for k in keys:
                    self._kr_backend.delete(tool_id, k)
            self._conn.execute("DELETE FROM secrets WHERE tool_id = ?", (tool_id,))
            self._conn.execute("DELETE FROM secret_keys WHERE tool_id = ?", (tool_id,))
        else:
            if self._kr_backend is not None:
                self._kr_backend.delete(tool_id, secret_key)
            self._conn.execute(
                "DELETE FROM secrets WHERE tool_id = ? AND secret_key = ?",
                (tool_id, secret_key),
            )
            self._conn.execute(
                "DELETE FROM secret_keys WHERE tool_id = ? AND secret_key = ?",
                (tool_id, secret_key),
            )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def _xor(self, data: bytes) -> bytes:
        out = bytearray(len(data))
        klen = len(self._key)
        for i, b in enumerate(data):
            out[i] = b ^ self._key[i % klen]
        return bytes(out)
