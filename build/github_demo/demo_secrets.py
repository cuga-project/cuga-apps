"""Secrets and database for build/github_demo. Never prints a secret value.

  prepare      read the source secrets (another CE project), create database DB_NAME on their
               Postgres, and write the demo's three secrets into the CURRENT CE project:
                 <prefix>-core-secrets    CUGA: LLM, gateway, database
                 <prefix>-events-secrets  events service: the same + channel tokens + webhook secret
                 <prefix>-tools-secrets   the tools only (mounted as files): GITHUB_TOKEN
               Fresh values are generated for GATEWAY_TOKEN, GITHUB_WEBHOOK_SECRET, EVENTS_WEBHOOK_KEY.
               Create-only: an existing demo secret is kept unless --force.
  local-env PATH   write the values the local steps need (EVENTS_DB, EVENTS_DB_CA_B64,
               DISCORD_BOT_TOKEN, GITHUB_WEBHOOK_SECRET, GATEWAY_TOKEN) to PATH, mode 600
  keys NAME    list a secret's key names in the current project

Env: SRC_PROJECT (ce-project-routing) SRC_REGION (us-east) SRC_RG (routing)
     SRC_CORE (oncall-core-secrets) SRC_EVENTS (oncall-events-secrets) SRC_TOOLS (ce-oncall-tools-secrets)
     DST_PROJECT (ce-cugaplusplus) DST_REGION (eu-gb) DST_RG (cugaplusplus) PREFIX (demo) DB_NAME (cuga_demo)
Values move through memory and mode-600 temp files only. The CLI target is restored to DST at the end.
"""
from __future__ import annotations

import base64
import json
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

E = os.environ.get
SRC = (E("SRC_PROJECT", "ce-project-routing"), E("SRC_REGION", "us-east"), E("SRC_RG", "routing"))
DST = (E("DST_PROJECT", "ce-cugaplusplus"), E("DST_REGION", "eu-gb"), E("DST_RG", "cugaplusplus"))
PREFIX = E("PREFIX", "demo")
DB_NAME = E("DB_NAME", "cuga_demo")

CORE_KEYS = ["AGENT_SETTING_CONFIG", "CUGA_SECRET_KEY", "LLM_MODEL", "LLM_PROVIDER", "WATSONX_APIKEY",
             "WATSONX_PROJECT_ID", "WATSONX_SPACE_ID", "WATSONX_URL", "EVENTS_DB_CA_B64"]
CHANNEL_KEYS = ["DISCORD_BOT_TOKEN", "SLACK_BOT_TOKEN", "SLACK_SIGNING_SECRET", "TELEGRAM_BOT_TOKEN",
                "EVENTS_TELEGRAM_BOT_USERNAME", "WHATSAPP_APP_SECRET", "WHATSAPP_PHONE_NUMBER_ID",
                "WHATSAPP_TOKEN", "WHATSAPP_VERIFY_TOKEN"]


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), capture_output=True, text=True)


def _use(project: str, region: str, rg: str) -> None:
    if _run("ibmcloud", "target", "-r", region, "-g", rg, "-q").returncode != 0:
        raise SystemExit(f"cannot target {region}/{rg}")
    if _run("ibmcloud", "ce", "project", "select", "--name", project).returncode != 0:
        raise SystemExit(f"cannot select project {project}")


def _secret_data(name: str) -> dict[str, str]:
    r = _run("ibmcloud", "ce", "secret", "get", "--name", name, "-o", "json")
    if r.returncode != 0:
        raise SystemExit(f"cannot read secret {name}")
    # `-o json` returns values in the clear (the text form base64-encodes them); never print them
    return dict(json.loads(r.stdout).get("data") or {})


def _exists(name: str) -> bool:
    return _run("ibmcloud", "ce", "secret", "get", "--name", name).returncode == 0


def _write_secret(name: str, data: dict[str, str], force: bool) -> None:
    exists = _exists(name)
    if exists and not force:
        print(f"secret {name}: exists, kept (use --force to replace)")
        return
    fd, path = tempfile.mkstemp(prefix="demo-secret-")
    try:
        os.chmod(path, 0o600)
        with os.fdopen(fd, "w") as f:
            for k, v in data.items():
                if "\n" in v:
                    raise SystemExit(f"value for {k} is multi-line; store it base64-encoded")
                f.write(f"{k}={v}\n")
        verb = "update" if exists else "create"
        r = _run("ibmcloud", "ce", "secret", verb, "--name", name, "--from-env-file", path)
        if r.returncode != 0:
            raise SystemExit(f"secret {verb} {name} failed: {r.stderr.strip()[-300:]}")
        print(f"secret {name}: {verb}d with keys {sorted(data)}")
    finally:
        Path(path).unlink(missing_ok=True)


def _with_db(dsn: str, dbname: str) -> str:
    u = urlsplit(dsn)
    return urlunsplit((u.scheme, u.netloc, "/" + dbname, u.query, u.fragment))


def _ensure_db(dsn: str, ca_b64: str | None, dbname: str) -> None:
    import psycopg

    kwargs = {}
    tmp = Path(tempfile.mkdtemp(prefix="demo-db-"))
    try:
        if ca_b64:
            ca = tmp / "ca.crt"
            ca.write_bytes(base64.b64decode(ca_b64))
            kwargs["sslrootcert"] = str(ca)
        with psycopg.connect(dsn, autocommit=True, connect_timeout=15, **kwargs) as conn:
            if conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)).fetchone():
                print(f"database {dbname}: already exists")
            else:
                conn.execute(f'CREATE DATABASE "{dbname}"')
                print(f"database {dbname}: created")
    finally:
        for f in tmp.iterdir():
            f.unlink()
        tmp.rmdir()


def _pick(src: dict[str, str], keys: list[str]) -> dict[str, str]:
    return {k: src[k] for k in keys if src.get(k)}


def cmd_prepare(*flags: str) -> None:
    force = "--force" in flags
    try:
        _use(*SRC)
        ev, core, tools = (_secret_data(E("SRC_EVENTS", "oncall-events-secrets")),
                           _secret_data(E("SRC_CORE", "oncall-core-secrets")),
                           _secret_data(E("SRC_TOOLS", "ce-oncall-tools-secrets")))
        _ensure_db(ev["EVENTS_DB"], ev.get("EVENTS_DB_CA_B64"), DB_NAME)
        db = {"EVENTS_DB": _with_db(ev["EVENTS_DB"], DB_NAME),
              "DYNACONF_STORAGE__POSTGRES_URL": _with_db(ev.get("DYNACONF_STORAGE__POSTGRES_URL") or ev["EVENTS_DB"], DB_NAME)}
        _use(*DST)
        gateway = _secret_data(f"{PREFIX}-core-secrets").get("GATEWAY_TOKEN") if _exists(f"{PREFIX}-core-secrets") and not force else None
        gateway = gateway or secrets.token_urlsafe(32)
        core_data = {**_pick(core, CORE_KEYS), **_pick(ev, ["EVENTS_DB_CA_B64"]), **db, "GATEWAY_TOKEN": gateway}
        events_data = {**core_data, **_pick(ev, CHANNEL_KEYS),
                       "GITHUB_WEBHOOK_SECRET": secrets.token_urlsafe(32),
                       "EVENTS_WEBHOOK_KEY": secrets.token_urlsafe(32)}
        if not tools.get("GITHUB_TOKEN"):
            raise SystemExit("source tools secret has no GITHUB_TOKEN")
        _write_secret(f"{PREFIX}-core-secrets", core_data, force)
        _write_secret(f"{PREFIX}-events-secrets", events_data, force)
        _write_secret(f"{PREFIX}-tools-secrets", {"GITHUB_TOKEN": tools["GITHUB_TOKEN"]}, force)
    finally:
        _use(*DST)


def cmd_local_env(path: str) -> None:
    _use(*DST)
    ev = _secret_data(f"{PREFIX}-events-secrets")
    keys = ["EVENTS_DB", "EVENTS_DB_CA_B64", "DISCORD_BOT_TOKEN", "GITHUB_WEBHOOK_SECRET", "GATEWAY_TOKEN"]
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        for k in keys:
            if ev.get(k):
                f.write(f"{k}={ev[k]}\n")
    print(f"wrote {', '.join(k for k in keys if ev.get(k))} to {path} (mode 600)")


def cmd_keys(name: str) -> None:
    print(" ".join(sorted(_secret_data(name))))


if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["-h"]
    fns = {"prepare": cmd_prepare, "local-env": cmd_local_env, "keys": cmd_keys}
    if cmd not in fns:
        print(__doc__)
        sys.exit(2)
    fns[cmd](*args)
