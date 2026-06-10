---
name: deploy-cuga
description: Ship cuga-apps changes to the running deployments — refresh the LOCAL all-in-one container (docker compose on :8080), build+push the CODE ENGINE image and roll the `cuga-agent-apps` service, and rebuild+publish the HUGGING FACE Space. Use when the user wants to deploy, ship, release, or "push live" changes to the gallery / CE / HF, or to update the local container to reflect current code. Builds compile from the current working tree (no commit required).
---

# Deploy cuga-apps (local + Code Engine + Hugging Face)

This skill ships the current working tree to three targets via the bundled
orchestrator `deploy.sh`. Each target is independent; CE always runs before HF
because the HF static build bakes in the CE service URL.

| Target | What it does | Result |
|---|---|---|
| `local` | `build/docker-compose.yml` → rebuild + run the all-in-one container | http://localhost:8080 |
| `ce` | `build/ce/build_and_push.sh` → push image to ICR, then `build/ce/deploy.sh` → roll `cuga-agent-apps` | the CE gallery URL |
| `hf` | `build/hf/build.sh` → static UI (bakes CE URL), then clone the HF Space, copy `dist/`, commit + push | `https://<owner>-<space>.hf.space/` |

The all-in-one image bundles the UI + ship-ready apps + the 5 internal MCP
servers + the stats collector — so CE/local pick up app, MCP, collector, AND UI
changes in one image. (The standalone `cuga-apps-mcp-*` servers in
`build/mcp_servers/` are a SEPARATE deploy — not part of this skill.)

## Steps to follow

1. **Scope.** Default to all three (`local ce hf`). If the user named specific
   targets (e.g. "just CE", "CE and HF"), use only those.

2. **Show the plan first.** Run a dry-run so the user sees exactly what will
   happen, then proceed (invoking this skill is the go-ahead to deploy):
   ```bash
   .claude/skills/deploy-cuga/deploy.sh --dry-run <targets>
   ```

3. **Check prerequisites** for the chosen targets and surface anything missing
   *before* the real run (don't half-deploy):
   - `local` / `ce` build: `docker` running.
   - `ce`: `ibmcloud` logged in, a CE project selected
     (`ibmcloud ce project current`), and `ibmcloud cr login` done (registry
     push). The script checks the project; registry auth fails loudly if absent.
   - `hf`: push auth — either `HF_TOKEN` (a write token) exported, or working
     git credentials / SSH for `huggingface.co`. Without either, the clone/push
     fails with a clear message. The Space defaults to `anupamamurthi/cuga-agent-apps`
     (override with `HF_SPACE`).

4. **Run it** for the chosen targets:
   ```bash
   .claude/skills/deploy-cuga/deploy.sh <targets>
   ```
   The script prints a per-target succeeded/failed summary and exits non-zero
   if any target failed. The builds are heavy (the all-in-one image pre-pulls
   model weights) — expect several minutes; don't abort early.

5. **Verify** each target that ran, and report the live URL:
   - `local`: `curl -sf -o /dev/null -w "%{http_code}\n" http://localhost:8080/`
     (expect 200). `docker compose -f build/docker-compose.yml ps` to confirm up.
   - `ce`: `deploy.sh` prints the service URL; hit `<url>/` (expect 200). The
     gallery host is the `cuga-agent-apps.…codeengine.appdomain.cloud` URL.
   - `hf`: confirm the push landed; the Space rebuilds automatically at
     `https://<owner>-<space>.hf.space/` (give it a minute).

6. **Report** the outcome plainly: which targets succeeded, the live URLs, and
   any failure with the script's error output. If a target failed, do NOT
   claim the deploy is live.

## Notes & overrides

- Useful env overrides (pass inline): `IMAGE_TAG`, `NAMESPACE`, `APP_NAME` (CE);
  `HF_SPACE`, `HF_USER`, `HF_TOKEN`, `ALLINONE_BASE` (HF). See `deploy.sh -h`.
- These deploys are **outward-facing**. If the user invoked the skill with no
  clear scope or seems unsure, confirm scope before the real run; otherwise the
  invocation is sufficient authorization.
- Builds use the working tree directly — no `git commit`/`pull` is required
  first (matches `build/DEPLOYMENT.md`).
- Secrets live in `build/.env` (gitignored) and the CE `app-env` secret — never
  commit them and never echo their values.
