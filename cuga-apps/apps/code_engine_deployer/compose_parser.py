"""
compose_parser — pure-function compose-file ingestion + CE-readiness classifier.

No subprocess, no network. Given a docker-compose.yml path it returns a
normalised list of services and a per-service classification (CE-ready,
needs-work, won't-fit) with reasons. The agent uses this to triage what
the user is about to deploy.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


# Code Engine app names: lowercase DNS labels, max 63 chars, no leading/trailing
# hyphen. Compose names are slightly looser (underscores allowed) so we
# normalise underscore→hyphen and validate.
_CE_NAME_RE = re.compile(r"^[a-z]([a-z0-9-]{0,61}[a-z0-9])?$")


def _ce_safe_name(compose_service_name: str, project_name: str | None = None) -> str:
    """Compose service name → suggested CE app name. Prefixes the project name
    so two stacks deploying `apps` don't collide."""
    base = compose_service_name.replace("_", "-").lower()
    if project_name:
        prefix = project_name.replace("_", "-").lower()
        if not base.startswith(prefix):
            base = f"{prefix}-{base}"
    base = base.strip("-")[:63]
    return base


def parse_compose(path: str | Path) -> dict:
    """Parse a docker-compose.yml. Returns a dict with `project_name` and
    `services` (list of normalised service dicts)."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"docker-compose file not found: {p}")
    raw = yaml.safe_load(p.read_text())
    if not isinstance(raw, dict):
        raise ValueError("docker-compose.yml is not a mapping at the top level")

    project_name = raw.get("name") or p.parent.name
    services_raw: dict[str, dict] = raw.get("services") or {}

    services = []
    for svc_name, svc in services_raw.items():
        services.append(_normalise_service(svc_name, svc, project_name, p))

    return {
        "project_name": project_name,
        "compose_path": str(p),
        "services": services,
    }


def _normalise_service(name: str, svc: dict, project_name: str, compose_path: Path) -> dict:
    image = svc.get("image")
    build = svc.get("build")
    if isinstance(build, str):
        build = {"context": build, "dockerfile": "Dockerfile"}
    elif isinstance(build, dict):
        build = {
            "context": build.get("context", "."),
            "dockerfile": build.get("dockerfile", "Dockerfile"),
        }

    ports_raw = svc.get("ports") or []
    ports: list[dict] = []
    for entry in ports_raw:
        # supports "29100:29100", "29100", or {published, target}
        if isinstance(entry, str):
            parts = entry.split(":")
            if len(parts) == 2:
                ports.append({"published": int(parts[0]), "target": int(parts[1])})
            elif len(parts) == 1:
                ports.append({"published": int(parts[0]), "target": int(parts[0])})
        elif isinstance(entry, int):
            ports.append({"published": entry, "target": entry})
        elif isinstance(entry, dict):
            ports.append(
                {
                    "published": int(entry.get("published") or entry.get("target")),
                    "target": int(entry.get("target")),
                }
            )

    cmd = svc.get("command")
    if isinstance(cmd, str):
        cmd_list = cmd.split()
    elif isinstance(cmd, list):
        cmd_list = [str(x) for x in cmd]
    else:
        cmd_list = []

    volumes_raw = svc.get("volumes") or []
    bind_mounts: list[dict] = []
    named_volumes: list[str] = []
    for vol in volumes_raw:
        if isinstance(vol, str):
            parts = vol.split(":")
            if len(parts) >= 2 and (parts[0].startswith(("/", ".", "~")) or "${" in parts[0]):
                bind_mounts.append(
                    {
                        "host": parts[0],
                        "container": parts[1],
                        "mode": parts[2] if len(parts) > 2 else "rw",
                    }
                )
            else:
                named_volumes.append(parts[0])
        elif isinstance(vol, dict):
            if vol.get("type") == "bind":
                bind_mounts.append(
                    {
                        "host": vol.get("source"),
                        "container": vol.get("target"),
                        "mode": "ro" if vol.get("read_only") else "rw",
                    }
                )
            else:
                named_volumes.append(vol.get("source") or "")

    mem_limit = svc.get("mem_limit") or svc.get("deploy", {}).get("resources", {}).get(
        "limits", {}
    ).get("memory")

    return {
        "service_name": name,
        "ce_name": _ce_safe_name(name, project_name),
        "image": image,
        "build": build,
        "command": cmd_list,
        "ports": ports,
        "bind_mounts": bind_mounts,
        "named_volumes": named_volumes,
        "environment": svc.get("environment") or {},
        "depends_on": list((svc.get("depends_on") or {})) if isinstance(svc.get("depends_on"), dict)
                      else (svc.get("depends_on") or []),
        "mem_limit": mem_limit,
        "container_name": svc.get("container_name"),
        "restart": svc.get("restart"),
    }


def classify_service(service: dict) -> dict:
    """Classify a normalised service for Code Engine readiness.

    Returns a dict with:
      verdict: "ce_ready" | "needs_work" | "wont_fit"
      reasons: list[str] — short human-readable findings
      blockers: list[str] — issues that prevent deploy as-is
      todos:    list[str] — things to do before deploy (secrets, etc.)
    """
    reasons: list[str] = []
    blockers: list[str] = []
    todos: list[str] = []

    # 1. Image source: must be buildable or pullable.
    if not service["image"] and not service["build"]:
        blockers.append("no `image` or `build` — nothing to deploy")
    elif service["build"] and not service["image"]:
        reasons.append("Will build image locally; needs an image tag for the registry")
        todos.append("decide image tag (e.g. us.icr.io/<ns>/<name>:latest)")

    # 2. Port count: CE apps route a single HTTP port.
    public_ports = [p for p in service["ports"] if p.get("target")]
    if len(public_ports) == 0:
        reasons.append("No ports — deploy as a CE Job rather than App")
    elif len(public_ports) == 1:
        reasons.append(f"Single port {public_ports[0]['target']} — fits CE App model")
    else:
        blockers.append(
            f"{len(public_ports)} ports — CE Apps route only one HTTP port. "
            "Split into multiple CE apps from the same image, or front with a router."
        )

    # 3. Bind mounts: not supported on CE; need translation.
    bind_secrets = [b for b in service["bind_mounts"] if "secret" in (b.get("container") or "")
                    or (b.get("host") or "").endswith(".env")]
    bind_data = [b for b in service["bind_mounts"] if b not in bind_secrets]

    if bind_secrets:
        reasons.append(
            f"{len(bind_secrets)} env-secret bind mount(s) — translate to CE Secret"
        )
        todos.append("create CE Secret from .env file (`ibmcloud ce secret create --from-env-file`)")
    if bind_data:
        # Distinguish RO from RW.
        ro = [b for b in bind_data if b.get("mode") == "ro"]
        rw = [b for b in bind_data if b.get("mode") != "ro"]
        if ro:
            reasons.append(
                f"{len(ro)} read-only data mount(s) — bake into image, or stage in COS"
            )
            todos.append("bake read-only data into the image OR migrate to IBM COS")
        if rw:
            blockers.append(
                f"{len(rw)} writable bind mount(s) — CE has no host bind mounts. "
                "Use IBM Cloud Object Storage (COS) or Code Engine PVC."
            )

    # 4. Named volumes: CE supports persistent volumes via PVC, but only with
    # extra setup. Flag as todo, not blocker, for stateless caches.
    if service["named_volumes"]:
        todos.append(
            f"named volume(s) {service['named_volumes']} — provision a CE PVC "
            "or accept ephemeral storage if cache-only"
        )

    # 5. Memory limit ceilings.
    mem = service.get("mem_limit")
    if isinstance(mem, str):
        m = re.match(r"^(\d+)([kmgKMG])?$", mem)
        if m:
            n, unit = int(m.group(1)), (m.group(2) or "").lower()
            mb = n * {"": 1, "k": 1 / 1024, "m": 1, "g": 1024}[unit] if unit != "" else n / (1024 * 1024)
            if mb >= 32 * 1024:
                reasons.append(
                    f"mem_limit={mem} is at CE per-instance ceiling — split before deploy"
                )

    # 6. depends_on: no equivalent on CE; inform retry behaviour.
    if service["depends_on"]:
        reasons.append(
            f"depends_on={service['depends_on']} — CE apps start independently; "
            "ensure clients tolerate startup races"
        )

    # 7. Verdict.
    if blockers:
        verdict = "wont_fit"
    elif todos:
        verdict = "needs_work"
    else:
        verdict = "ce_ready"

    return {
        "service_name": service["service_name"],
        "ce_name": service["ce_name"],
        "verdict": verdict,
        "reasons": reasons,
        "blockers": blockers,
        "todos": todos,
    }


def classify_all(parsed: dict) -> list[dict]:
    return [classify_service(s) for s in parsed["services"]]


def is_valid_ce_name(name: str) -> bool:
    return bool(_CE_NAME_RE.match(name)) and len(name) <= 63
