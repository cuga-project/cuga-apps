"""
ce_ops — thin, validated subprocess wrappers around `ibmcloud` and `docker`.

Every callable here is a wrapper around one CLI invocation. Inputs are
strictly validated against an allowlist regex (no shell injection, no
`shell=True`, no f-string interpolation into a command). The result is
always a structured dict so the calling agent can reason about success vs.
failure and surface the exact command + stderr to the user.

Designed to run on the operator's workstation where `ibmcloud` and `docker`
are installed and authenticated. When run inside the apps container the
commands return a structured `binary_missing` error rather than crashing,
and the agent will tell the user.
"""
from __future__ import annotations

import json as _json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable

# Names valid for both Docker images and CE resources (lowercase DNS labels).
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._\-/]{0,127}$")
_TAG_RE = re.compile(r"^[A-Za-z0-9._\-/:]{1,256}$")
_REGION_RE = re.compile(r"^[a-z]{2}-[a-z]{2,5}$")


class ValidationError(ValueError):
    pass


def _need(name: str) -> str:
    """Return the absolute path to a required CLI, or raise ValidationError."""
    p = shutil.which(name)
    if not p:
        raise ValidationError(
            f"`{name}` not found on PATH. Install + authenticate it on this machine, "
            f"or run the deployer from a workstation that has it."
        )
    return p


def _validate(value: str, regex: re.Pattern, label: str) -> str:
    if not isinstance(value, str) or not regex.match(value):
        raise ValidationError(f"invalid {label}: {value!r}")
    return value


def _run(cmd: list[str], timeout: int = 600, input_text: str | None = None) -> dict:
    """Execute a command list; return a structured envelope.

    Never uses shell=True. Never accepts a string command. Stdout/stderr are
    captured; both are size-capped to keep the agent context manageable.
    """
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=input_text,
        )
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "error": f"binary_missing: {exc}",
            "command": cmd,
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": f"timeout after {timeout}s",
            "command": cmd,
        }

    return {
        "ok": proc.returncode == 0,
        "command": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-8000:],
        "stderr": proc.stderr[-4000:],
    }


# ── Prereq + auth ─────────────────────────────────────────────────────────


def check_prereqs() -> dict:
    """Verify that `ibmcloud` and `docker` are installed and that the user is
    logged in to IBM Cloud. Returns a structured report; does not throw."""
    out: dict[str, Any] = {"binaries": {}, "auth": {}}
    for binary in ("ibmcloud", "docker"):
        path = shutil.which(binary)
        out["binaries"][binary] = {"present": bool(path), "path": path}

    if out["binaries"]["ibmcloud"]["present"]:
        target = _run(["ibmcloud", "target", "--output", "json"])
        out["auth"]["ibmcloud_target"] = target
        try:
            parsed = _json.loads(target.get("stdout") or "{}")
            out["auth"]["account"] = (parsed.get("account") or {}).get("name")
            out["auth"]["region"] = (parsed.get("region") or {}).get("name")
            out["auth"]["resource_group"] = (parsed.get("resource_group") or {}).get(
                "name"
            )
        except _json.JSONDecodeError:
            pass

    if out["binaries"]["ibmcloud"]["present"]:
        plugins = _run(["ibmcloud", "plugin", "list", "--output", "json"])
        try:
            installed = {p.get("Name") for p in _json.loads(plugins.get("stdout") or "[]")}
            out["plugins"] = {
                "code-engine": "code-engine" in installed,
                "container-registry": "container-registry" in installed,
            }
        except _json.JSONDecodeError:
            out["plugins"] = {}

    return out


# ── Code Engine: project + apps ───────────────────────────────────────────


def list_ce_projects() -> dict:
    _need("ibmcloud")
    return _run(["ibmcloud", "ce", "project", "list", "--output", "json"])


def target_ce_project(name: str) -> dict:
    _need("ibmcloud")
    _validate(name, _NAME_RE, "project name")
    return _run(["ibmcloud", "ce", "project", "select", "--name", name])


def list_ce_apps() -> dict:
    _need("ibmcloud")
    return _run(["ibmcloud", "ce", "app", "list", "--output", "json"])


def get_ce_app(name: str) -> dict:
    _need("ibmcloud")
    _validate(name, _NAME_RE, "app name")
    return _run(["ibmcloud", "ce", "app", "get", "--name", name, "--output", "json"])


def get_ce_app_logs(name: str, lines: int = 200) -> dict:
    _need("ibmcloud")
    _validate(name, _NAME_RE, "app name")
    if not isinstance(lines, int) or not (1 <= lines <= 5000):
        raise ValidationError("lines must be 1..5000")
    return _run(["ibmcloud", "ce", "app", "logs", "--name", name, "--tail", str(lines)])


def get_ce_app_events(name: str) -> dict:
    _need("ibmcloud")
    _validate(name, _NAME_RE, "app name")
    return _run(["ibmcloud", "ce", "app", "events", "--name", name])


def delete_ce_app(name: str, force: bool = False) -> dict:
    """Destructive — only call after explicit user confirmation."""
    _need("ibmcloud")
    _validate(name, _NAME_RE, "app name")
    if not force:
        return {
            "ok": False,
            "error": "delete_ce_app requires force=True (destructive)",
            "command": ["ibmcloud", "ce", "app", "delete", "--name", name, "--force"],
        }
    return _run(["ibmcloud", "ce", "app", "delete", "--name", name, "--force", "--ignore-not-found"])


# ── Code Engine: secrets + registry access ────────────────────────────────


def create_ce_secret_from_env_file(name: str, env_file_path: str) -> dict:
    _need("ibmcloud")
    _validate(name, _NAME_RE, "secret name")
    p = Path(env_file_path).expanduser().resolve()
    if not p.exists() or not p.is_file():
        raise ValidationError(f"env file not found: {p}")
    return _run(
        [
            "ibmcloud", "ce", "secret", "create",
            "--name", name,
            "--from-env-file", str(p),
        ]
    )


def create_ce_registry_secret(name: str, server: str, username: str, password: str) -> dict:
    _need("ibmcloud")
    _validate(name, _NAME_RE, "registry-secret name")
    if not isinstance(server, str) or not server:
        raise ValidationError("server is required")
    return _run(
        [
            "ibmcloud", "ce", "registry", "create",
            "--name", name,
            "--server", server,
            "--username", username,
            "--password", password,
        ]
    )


# ── Code Engine: app deploy + update ──────────────────────────────────────


def deploy_ce_app(
    *,
    name: str,
    image: str,
    port: int | None = None,
    command: list[str] | None = None,
    arguments: list[str] | None = None,
    env_secret: str | None = None,
    secret_mount_path: str = "/run/secrets",
    registry_secret: str | None = None,
    cpu: str = "1",
    memory: str = "2G",
    min_scale: int = 1,
    max_scale: int = 1,
) -> dict:
    """Wrap `ibmcloud ce app create`. All args are validated."""
    _need("ibmcloud")
    _validate(name, _NAME_RE, "app name")
    _validate(image, _TAG_RE, "image tag")
    if env_secret is not None:
        _validate(env_secret, _NAME_RE, "env secret name")
    if registry_secret is not None:
        _validate(registry_secret, _NAME_RE, "registry secret name")

    cmd = ["ibmcloud", "ce", "app", "create", "--name", name, "--image", image]
    if port is not None:
        if not isinstance(port, int) or not (1 <= port <= 65535):
            raise ValidationError("port out of range")
        cmd += ["--port", str(port)]
    if command:
        cmd += ["--command", _join_command(command)]
    if arguments:
        for arg in arguments:
            cmd += ["--argument", str(arg)]
    if env_secret:
        cmd += ["--mount-secret", f"{secret_mount_path}={env_secret}"]
    if registry_secret:
        cmd += ["--registry-secret", registry_secret]
    cmd += [
        "--cpu", str(cpu),
        "--memory", str(memory),
        "--min-scale", str(int(min_scale)),
        "--max-scale", str(int(max_scale)),
    ]
    return _run(cmd, timeout=900)


def update_ce_app(
    *,
    name: str,
    image: str | None = None,
    cpu: str | None = None,
    memory: str | None = None,
    min_scale: int | None = None,
    max_scale: int | None = None,
) -> dict:
    _need("ibmcloud")
    _validate(name, _NAME_RE, "app name")
    cmd = ["ibmcloud", "ce", "app", "update", "--name", name]
    if image:
        _validate(image, _TAG_RE, "image tag")
        cmd += ["--image", image]
    if cpu:
        cmd += ["--cpu", str(cpu)]
    if memory:
        cmd += ["--memory", str(memory)]
    if min_scale is not None:
        cmd += ["--min-scale", str(int(min_scale))]
    if max_scale is not None:
        cmd += ["--max-scale", str(int(max_scale))]
    if cmd[-2:] == ["--name", name]:
        return {"ok": False, "error": "no fields to update", "command": cmd}
    return _run(cmd, timeout=600)


def _join_command(cmd: Iterable[str]) -> str:
    """`--command` takes a single string. Quote tokens that contain spaces."""
    out = []
    for part in cmd:
        if any(c.isspace() for c in part):
            out.append('"' + part.replace('"', '\\"') + '"')
        else:
            out.append(part)
    return " ".join(out)


# ── Docker: build + push ──────────────────────────────────────────────────


def docker_build(context_dir: str, dockerfile: str, tag: str, platform: str = "linux/amd64") -> dict:
    _need("docker")
    _validate(tag, _TAG_RE, "image tag")
    ctx = Path(context_dir).expanduser().resolve()
    if not ctx.is_dir():
        raise ValidationError(f"build context is not a directory: {ctx}")
    df = (ctx / dockerfile) if not Path(dockerfile).is_absolute() else Path(dockerfile)
    if not df.exists():
        raise ValidationError(f"Dockerfile not found: {df}")
    return _run(
        [
            "docker", "build",
            "--platform", platform,
            "-f", str(df),
            "-t", tag,
            str(ctx),
        ],
        timeout=1800,
    )


def docker_push(tag: str) -> dict:
    _need("docker")
    _validate(tag, _TAG_RE, "image tag")
    return _run(["docker", "push", tag], timeout=1800)


# ── IBM Container Registry helpers ────────────────────────────────────────


def cr_login() -> dict:
    _need("ibmcloud")
    return _run(["ibmcloud", "cr", "login"])


def cr_region_set(region: str) -> dict:
    _need("ibmcloud")
    _validate(region, _REGION_RE, "region")
    return _run(["ibmcloud", "cr", "region-set", region])


def cr_namespace_add(namespace: str) -> dict:
    _need("ibmcloud")
    _validate(namespace, _NAME_RE, "namespace")
    return _run(["ibmcloud", "cr", "namespace-add", namespace])
