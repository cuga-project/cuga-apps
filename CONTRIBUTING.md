# Contributing to cuga-apps

Thanks for your interest in contributing! cuga-apps is a collection of small,
self-contained agent demos built on [CUGA](https://github.com/cuga-project/cuga-agent),
plus a set of shared MCP tool servers and an umbrella UI. The bar for a good
contribution is simple: **it should run, be self-contained, and read like the
apps already here.**

## Ways to contribute

- **A new app.** The fastest path is to copy the pattern in
  [`cuga-apps/docs/cuga_app_builder_spec.md`](cuga-apps/docs/cuga_app_builder_spec.md)
  (and the standalone external spec at [`cuga_external_app_spec.md`](cuga_external_app_spec.md)).
  An app is a single folder with `main.py` (FastAPI + `CugaAgent` + tools),
  `ui.py` (exports `_HTML`), and copies of the shared `_llm.py` / `_mcp_bridge.py`
  helpers. Wire it into [`cuga-apps/apps/launch.py`](cuga-apps/apps/launch.py),
  [`cuga-apps/apps/_ports.py`](cuga-apps/apps/_ports.py), and the umbrella UI
  registry (`cuga-apps/ui/src/data/usecases.ts`).
- **A new shared tool / MCP server.** See
  [`cuga-apps/mcp_servers/README.md`](cuga-apps/mcp_servers/README.md). Tools
  must return the `{"ok": bool, "data"|"error": ...}` envelope.
- **Fixes and polish.** Bug fixes, docs, accessibility, and UI consistency
  improvements are all welcome.

## Ground rules

1. **Keep apps self-contained.** No app should depend on another app's internals.
   Shared helpers live at `cuga-apps/apps/_*.py`.
2. **Read config from the environment.** Never hardcode a provider, model, API
   key, file path, or hostname. Use `os.getenv(...)`. A missing optional key
   should degrade gracefully (the tool returns `{"ok": false, "code": "missing_key"}`),
   not crash the app.
3. **No secrets, ever.** Real keys live only in local `.env` files (gitignored)
   and Code Engine secrets. Commit `.env.example` updates, never `.env`.
4. **Follow the tool envelope.** Every inline `@tool` returns
   `json.dumps({"ok": ..., ...})` — never a raw dict.
5. **Match the surrounding style.** Mirror the comment density, naming, and
   idioms of the existing code. UI is vanilla JS + the shared Carbon foundation
   (`cuga-apps/apps/_carbon.py`); no new frameworks.
6. **Keep the system prompt static.** Define `_SYSTEM` at module scope; don't
   compose it per request.

## Before you open a PR

- [ ] `python3 -m py_compile` passes on every file you touched.
- [ ] The app boots: `python main.py --port <port>` → `GET /health` returns
      `{"ok": true}`, `POST /ask` returns a real answer, the UI loads.
- [ ] If you touched the umbrella UI: `cd cuga-apps/ui && npm run build` is clean.
- [ ] No secrets, personal paths, or internal hostnames in the diff.
- [ ] New app registered in `launch.py`, `_ports.py`, and `usecases.ts` (and
      given an honest stage: ship-ready / for-later / exploratory).
- [ ] Docs/counts updated if your change affects them.

## Running locally

See [`cuga-apps/README.md`](cuga-apps/README.md) for the full setup. Quickstart:

```bash
# from the repo's cuga-apps/ dir, with the venv that has `cuga` installed
python apps/launch.py start --ship-ready    # MCP servers + the ship-ready apps
```

Or build the all-in-one container (apps + MCP + UI on one port) — see
[`build/README.md`](build/README.md).

## Developer Certificate of Origin

By contributing, you certify that your contribution is your own work (or you
have the right to submit it) and that you license it under the project's
[Apache License 2.0](LICENSE). Sign your commits with `git commit -s` to add a
`Signed-off-by` trailer.

## License

By contributing, you agree that your contributions will be licensed under the
[Apache License 2.0](LICENSE).
