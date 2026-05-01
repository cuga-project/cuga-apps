"""
Code Engine Deployer — conversational deployment assistant for IBM Cloud Code Engine.
====================================================================================

Reads a docker-compose.yml, classifies each service for Code Engine readiness
(CE-ready / needs-work / won't-fit), explains the architectural mismatches, and
walks the user through building, pushing, and deploying. On failures, fetches
CE logs/events and proposes a next step instead of retrying blindly.

The agent does no shell work itself — every CLI invocation is wrapped in a
strictly validated tool in ce_ops.py. The LLM picks tools and arguments; the
tools enforce shape and refuse anything that doesn't match an allowlist regex.

Run:
    python main.py
    python main.py --port 28818
    python main.py --provider anthropic

Then open: http://127.0.0.1:28818

Environment variables:
    LLM_PROVIDER         rits | anthropic | openai | watsonx | litellm | ollama
    LLM_MODEL            model name override
    AGENT_SETTING_CONFIG path to a CUGA settings TOML

Host requirements (the deployer SHELLS OUT to these):
    ibmcloud CLI + plugins  code-engine, container-registry
    docker CLI              with a working daemon
    Authenticated session   `ibmcloud login` + `ibmcloud target -r <region> -g <rg>`
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from pathlib import Path

# ── Path bootstrap — required, see cuga_app_builder_spec.md ──────────────
_DIR = Path(__file__).parent
_DEMOS_DIR = _DIR.parent
for _p in (str(_DIR), str(_DEMOS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Tools ─────────────────────────────────────────────────────────────────


def _make_tools():
    """All tools are inline — this is a new domain (Code Engine ops) that
    doesn't fit any existing MCP server, and a new MCP server is unjustified
    for a single consumer."""
    from langchain_core.tools import tool

    import ce_ops
    import compose_parser

    def _envelope(value) -> str:
        """Return either a tool_result-style JSON envelope or the string."""
        try:
            return json.dumps(value, default=str)
        except (TypeError, ValueError):
            return json.dumps({"ok": False, "error": "non-serialisable result"})

    # ── Compose parsing + classification ────────────────────────────────

    @tool
    def parse_compose_file(path: str) -> str:
        """Parse a docker-compose.yml and return its services in normalised form.

        The result is structured: project_name, compose_path, and a list of
        services with image / build / ports / bind mounts / volumes / command /
        depends_on / mem_limit. Use this BEFORE deciding what to deploy.

        Args:
            path: Absolute or user-relative path to a docker-compose.yml file.
        """
        try:
            data = compose_parser.parse_compose(path)
            return _envelope({"ok": True, "data": data})
        except Exception as exc:
            return _envelope({"ok": False, "error": str(exc)})

    @tool
    def classify_compose_services(path: str) -> str:
        """Parse the compose file at `path` AND classify every service for
        Code Engine readiness in one shot. Returns each service's verdict
        (ce_ready | needs_work | wont_fit), reasons, blockers, and todos.

        Use this to triage what the user can deploy right now versus what
        needs architectural decisions first.

        Args:
            path: Path to docker-compose.yml.
        """
        try:
            data = compose_parser.parse_compose(path)
            verdicts = compose_parser.classify_all(data)
            ready = [v for v in verdicts if v["verdict"] == "ce_ready"]
            needs = [v for v in verdicts if v["verdict"] == "needs_work"]
            wont = [v for v in verdicts if v["verdict"] == "wont_fit"]
            return _envelope(
                {
                    "ok": True,
                    "data": {
                        "project_name": data["project_name"],
                        "compose_path": data["compose_path"],
                        "summary": {
                            "ce_ready": [v["service_name"] for v in ready],
                            "needs_work": [v["service_name"] for v in needs],
                            "wont_fit": [v["service_name"] for v in wont],
                        },
                        "verdicts": verdicts,
                    },
                }
            )
        except Exception as exc:
            return _envelope({"ok": False, "error": str(exc)})

    # ── Prereq + project ────────────────────────────────────────────────

    @tool
    def check_prereqs() -> str:
        """Check that ibmcloud + docker CLIs are installed, the user is logged
        in, and the required CE plugins are present. Run this once at the
        start of a deployment session.
        """
        return _envelope({"ok": True, "data": ce_ops.check_prereqs()})

    @tool
    def list_ce_projects() -> str:
        """List all Code Engine projects in the current account/region."""
        try:
            return _envelope(ce_ops.list_ce_projects())
        except ce_ops.ValidationError as exc:
            return _envelope({"ok": False, "error": str(exc)})

    @tool
    def target_ce_project(name: str) -> str:
        """Select a Code Engine project as the active target.

        Args:
            name: Project name. Must already exist (create via the IBM Cloud console).
        """
        try:
            return _envelope(ce_ops.target_ce_project(name))
        except ce_ops.ValidationError as exc:
            return _envelope({"ok": False, "error": str(exc)})

    # ── App lifecycle ───────────────────────────────────────────────────

    @tool
    def list_ce_apps() -> str:
        """List Code Engine apps in the currently targeted project."""
        try:
            return _envelope(ce_ops.list_ce_apps())
        except ce_ops.ValidationError as exc:
            return _envelope({"ok": False, "error": str(exc)})

    @tool
    def get_ce_app(name: str) -> str:
        """Return the full details (image, port, scale, status) for a CE app.

        Args:
            name: CE app name.
        """
        try:
            return _envelope(ce_ops.get_ce_app(name))
        except ce_ops.ValidationError as exc:
            return _envelope({"ok": False, "error": str(exc)})

    @tool
    def get_ce_app_logs(name: str, lines: int = 200) -> str:
        """Tail the logs for a CE app. Use this when an app crashes or returns
        unexpected output to diagnose the failure.

        Args:
            name: CE app name.
            lines: Number of trailing log lines (1..5000, default 200).
        """
        try:
            return _envelope(ce_ops.get_ce_app_logs(name, lines))
        except ce_ops.ValidationError as exc:
            return _envelope({"ok": False, "error": str(exc)})

    @tool
    def get_ce_app_events(name: str) -> str:
        """Fetch the Kubernetes-style events for a CE app — the right place
        to read for ImagePullBackOff, OOM, scheduling failures.

        Args:
            name: CE app name.
        """
        try:
            return _envelope(ce_ops.get_ce_app_events(name))
        except ce_ops.ValidationError as exc:
            return _envelope({"ok": False, "error": str(exc)})

    @tool
    def delete_ce_app(name: str, force: bool = False) -> str:
        """Delete a CE app. Destructive — only call after the user has
        explicitly confirmed by name. Pass force=True to actually delete.

        Args:
            name: CE app name.
            force: Must be True to actually execute. Defaults to False so
                   the agent must confirm with the user first.
        """
        try:
            return _envelope(ce_ops.delete_ce_app(name, force=force))
        except ce_ops.ValidationError as exc:
            return _envelope({"ok": False, "error": str(exc)})

    # ── Secrets + registry access ───────────────────────────────────────

    @tool
    def create_ce_secret_from_env_file(name: str, env_file_path: str) -> str:
        """Create a Code Engine secret from a local .env file. The resulting
        secret is mountable into apps as files (typical pattern for replacing
        a docker-compose `volumes: - .env:/run/secrets/app.env:ro` mount).

        Args:
            name: Secret name (lowercase DNS-safe).
            env_file_path: Path to a KEY=VALUE .env file on this machine.
        """
        try:
            return _envelope(ce_ops.create_ce_secret_from_env_file(name, env_file_path))
        except ce_ops.ValidationError as exc:
            return _envelope({"ok": False, "error": str(exc)})

    @tool
    def create_ce_registry_secret(name: str, server: str, username: str, password: str) -> str:
        """Create a registry-access secret so CE can pull from a private
        registry (e.g. IBM Container Registry).

        Args:
            name: Secret name.
            server: Registry hostname, e.g. us.icr.io.
            username: Registry username (for ICR: 'iamapikey').
            password: Registry password (for ICR: an IBM Cloud API key).
        """
        try:
            return _envelope(ce_ops.create_ce_registry_secret(name, server, username, password))
        except ce_ops.ValidationError as exc:
            return _envelope({"ok": False, "error": str(exc)})

    # ── Build + push ────────────────────────────────────────────────────

    @tool
    def docker_build(context_dir: str, dockerfile: str, tag: str, platform: str = "linux/amd64") -> str:
        """Build a docker image. Always builds for linux/amd64 by default
        (Code Engine runs on amd64; Apple Silicon hosts otherwise produce
        unrunnable arm64 images).

        Args:
            context_dir: Build context directory (the path you'd pass to `docker build .`).
            dockerfile: Path to the Dockerfile, absolute or relative to context_dir.
            tag: Full image tag, e.g. us.icr.io/myns/mcp-web:latest.
            platform: Build platform. Default linux/amd64.
        """
        try:
            return _envelope(ce_ops.docker_build(context_dir, dockerfile, tag, platform))
        except ce_ops.ValidationError as exc:
            return _envelope({"ok": False, "error": str(exc)})

    @tool
    def docker_push(tag: str) -> str:
        """Push a previously-built image to its registry. Requires the user
        to have already authenticated with the registry (e.g. `ibmcloud cr login`).

        Args:
            tag: Full image tag to push.
        """
        try:
            return _envelope(ce_ops.docker_push(tag))
        except ce_ops.ValidationError as exc:
            return _envelope({"ok": False, "error": str(exc)})

    # ── ICR helpers ─────────────────────────────────────────────────────

    @tool
    def cr_login() -> str:
        """Run `ibmcloud cr login` so the local docker daemon can push to
        IBM Container Registry."""
        try:
            return _envelope(ce_ops.cr_login())
        except ce_ops.ValidationError as exc:
            return _envelope({"ok": False, "error": str(exc)})

    @tool
    def cr_region_set(region: str) -> str:
        """Set the active IBM Container Registry region.

        Args:
            region: e.g. us-south, eu-de.
        """
        try:
            return _envelope(ce_ops.cr_region_set(region))
        except ce_ops.ValidationError as exc:
            return _envelope({"ok": False, "error": str(exc)})

    @tool
    def cr_namespace_add(namespace: str) -> str:
        """Create an ICR namespace (idempotent on the user's plan).

        Args:
            namespace: Lowercase namespace name.
        """
        try:
            return _envelope(ce_ops.cr_namespace_add(namespace))
        except ce_ops.ValidationError as exc:
            return _envelope({"ok": False, "error": str(exc)})

    # ── Deploy ──────────────────────────────────────────────────────────

    @tool
    def deploy_ce_app(
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
    ) -> str:
        """Create a Code Engine app from a pushed image.

        Args:
            name: CE app name (lowercase DNS-safe, max 63 chars).
            image: Full image tag (e.g. us.icr.io/myns/mcp-web:latest).
            port: HTTP port the container listens on. CE routes ONE port per app.
            command: Container entrypoint override as a list, e.g. ["python"].
            arguments: Container args as a list, e.g. ["-m", "mcp_servers.web.server"].
            env_secret: Name of a CE Secret (created via create_ce_secret_from_env_file)
                        to mount as files at secret_mount_path.
            secret_mount_path: Mount path for env_secret (default /run/secrets).
            registry_secret: Name of a CE Secret holding registry pull credentials.
            cpu: CPU request, e.g. "0.5", "1", "2".
            memory: Memory request, e.g. "512M", "2G", "8G".
            min_scale: Minimum number of running instances (1 = always-warm, 0 = scale-to-zero).
            max_scale: Maximum number of running instances.
        """
        try:
            return _envelope(
                ce_ops.deploy_ce_app(
                    name=name, image=image, port=port,
                    command=command, arguments=arguments,
                    env_secret=env_secret, secret_mount_path=secret_mount_path,
                    registry_secret=registry_secret,
                    cpu=cpu, memory=memory,
                    min_scale=min_scale, max_scale=max_scale,
                )
            )
        except ce_ops.ValidationError as exc:
            return _envelope({"ok": False, "error": str(exc)})

    @tool
    def update_ce_app(
        name: str,
        image: str | None = None,
        cpu: str | None = None,
        memory: str | None = None,
        min_scale: int | None = None,
        max_scale: int | None = None,
    ) -> str:
        """Update an existing CE app's image or scale parameters.

        Args:
            name: CE app name.
            image: New image tag. Set this to roll a new build.
            cpu: New CPU request.
            memory: New memory request.
            min_scale: New min instance count.
            max_scale: New max instance count.
        """
        try:
            return _envelope(
                ce_ops.update_ce_app(
                    name=name, image=image, cpu=cpu, memory=memory,
                    min_scale=min_scale, max_scale=max_scale,
                )
            )
        except ce_ops.ValidationError as exc:
            return _envelope({"ok": False, "error": str(exc)})

    return [
        parse_compose_file,
        classify_compose_services,
        check_prereqs,
        list_ce_projects,
        target_ce_project,
        list_ce_apps,
        get_ce_app,
        get_ce_app_logs,
        get_ce_app_events,
        delete_ce_app,
        create_ce_secret_from_env_file,
        create_ce_registry_secret,
        docker_build,
        docker_push,
        cr_login,
        cr_region_set,
        cr_namespace_add,
        deploy_ce_app,
        update_ce_app,
    ]


# ── System prompt ─────────────────────────────────────────────────────────

_SYSTEM = """\
# Code Engine Deployer

You are a deployment assistant for IBM Cloud Code Engine. The user gives you
a docker-compose.yml and asks you to deploy some or all of its services to CE.
Your job is conversational triage + execution: read the compose file, explain
what fits cleanly versus what needs architectural decisions, walk the user
through those decisions, then run the deploy with confirmation gates.

You do NOT do shell work directly. You call tools. The tools validate inputs
and refuse anything malformed; if a tool returns an error, READ IT and either
fix the call or surface it to the user with a proposed next step.

## Workflow

1. **Triage.** When the user names a compose file (or you can find one),
   call `classify_compose_services(path)`. Show the user a short table:
   which services are CE-ready, which need work, which won't fit, and WHY.
   Quote the reasons from the verdicts — don't paraphrase.

2. **Scope.** Ask the user which services to deploy. Default suggestion:
   start with the CE-ready set, plus needs-work services after you've talked
   through their todos. Do not start deploying without confirmation.

3. **Prereq check.** Before the first deploy in a session, call `check_prereqs`.
   If `ibmcloud` or `docker` is missing, tell the user where they need to run
   the deployer (workstation with both CLIs installed). If they're not logged
   in, ask them to run `ibmcloud login` themselves — never attempt a login on
   their behalf.

4. **Project.** If they don't have an active CE project targeted, list
   options with `list_ce_projects` and ask which to use, then call
   `target_ce_project`.

5. **Registry + secrets (one-time).** If they're pushing to ICR for the
   first time in this project, walk them through:
   - `cr_region_set` + `cr_namespace_add` if needed
   - `cr_login` so the local docker daemon can push
   - `create_ce_registry_secret` so CE can pull
   - `create_ce_secret_from_env_file` to translate any `.env` bind mounts
   Confirm each one before running.

6. **Deploy each service.** Per service:
   a. Show the planned `docker_build`, `docker_push`, and `deploy_ce_app`
      calls in plain English BEFORE executing.
   b. Wait for confirmation.
   c. Build, push, deploy in that order.
   d. After `deploy_ce_app`, call `get_ce_app` to verify status.

7. **Diagnose failures.** If any tool returns ok=false:
   - For deploy failures, call `get_ce_app_events` and `get_ce_app_logs`.
   - Read the actual error. Common patterns:
     * `ImagePullBackOff` → registry-secret misconfigured or wrong image tag
     * exits immediately → entrypoint issue or missing env var
     * port mismatch → app inside container is listening on a different port
   - Propose ONE specific fix. Do not retry blindly.

## Hard rules

- **Single port per CE app.** If a service has >1 port mapping, do NOT deploy
  it to a single CE app. Tell the user the options: split into multiple CE
  apps from the same image with different `--port` and `--argument`, or front
  with a router. Ask which they want.
- **Bind mounts.** Bake read-only data into the image OR migrate to COS.
  For writable mounts, refuse to deploy without a PVC or COS plan.
- **Never bypass validation.** If `deploy_ce_app` returns a ValidationError,
  the inputs are wrong — fix them, don't paper over.
- **Destructive actions need explicit user confirmation by name.** For
  `delete_ce_app` always confirm the exact app name first; only set force=True
  after the user has typed the name back.
- **No secrets in chat.** If the user pastes an API key into the chat, use
  it for the call but do not echo it back in your response.

## Output format

Be concise but specific:
- For triage, render a markdown table of services with verdict + headline reason.
- For each tool call, briefly state what you're about to do (one line).
- After execution, show: ✅ success with the key field (image tag, app URL, status),
  or ❌ with the exact error and a proposed next step.

Cite app URLs as clickable markdown links once a deployment succeeds.
"""


# ── Agent factory ─────────────────────────────────────────────────────────


def make_agent():
    from cuga.sdk import CugaAgent
    from _llm import create_llm

    _provider_toml = {
        "rits":      "settings.rits.toml",
        "watsonx":   "settings.watsonx.toml",
        "openai":    "settings.openai.toml",
        "anthropic": "settings.openai.toml",
        "litellm":   "settings.litellm.toml",
        "ollama":    "settings.openai.toml",
    }
    provider = (os.getenv("LLM_PROVIDER") or "").lower()
    os.environ.setdefault(
        "AGENT_SETTING_CONFIG",
        _provider_toml.get(provider, "settings.rits.toml"),
    )

    return CugaAgent(
        model=create_llm(
            provider=os.getenv("LLM_PROVIDER"),
            model=os.getenv("LLM_MODEL"),
        ),
        tools=_make_tools(),
        special_instructions=_SYSTEM,
        cuga_folder=str(_DIR / ".cuga"),
    )


# ── Request models ────────────────────────────────────────────────────────

from pydantic import BaseModel  # noqa: E402


class AskReq(BaseModel):
    question: str
    thread_id: str = "default"


class ClassifyReq(BaseModel):
    path: str


# ── Web app ───────────────────────────────────────────────────────────────


def _web(port: int) -> None:
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, JSONResponse

    from ui import _HTML

    app = FastAPI(title="Code Engine Deployer", docs_url=None, redoc_url=None)
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"],
        allow_methods=["*"], allow_headers=["*"],
    )

    agent = make_agent()

    @app.post("/ask")
    async def api_ask(req: AskReq):
        question = req.question.strip()
        if not question:
            return JSONResponse({"error": "Empty question"}, status_code=400)
        try:
            result = await agent.invoke(question, thread_id=req.thread_id)
            return {"answer": result.answer}
        except Exception as exc:
            log.exception("Agent error")
            return JSONResponse({"error": str(exc)}, status_code=500)

    @app.post("/classify")
    async def api_classify(req: ClassifyReq):
        """Pure non-LLM endpoint — parse + classify a compose file. Useful for
        the UI to render the table without burning an LLM call."""
        import compose_parser
        try:
            data = compose_parser.parse_compose(req.path)
            verdicts = compose_parser.classify_all(data)
            return {
                "project_name": data["project_name"],
                "compose_path": data["compose_path"],
                "verdicts": verdicts,
            }
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(_HTML)

    print(f"\n  Code Engine Deployer  →  http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ── CLI entry point ───────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Code Engine Deployer")
    parser.add_argument("--port", type=int, default=28818)
    parser.add_argument(
        "--provider", "-p", default=None,
        choices=["rits", "watsonx", "openai", "anthropic", "litellm", "ollama"],
    )
    parser.add_argument("--model", "-m", default=None)
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    _web(args.port)


if __name__ == "__main__":
    main()
