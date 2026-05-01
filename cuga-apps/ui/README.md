# cuga-apps

## Dashboard UI

`ui/` is a React/Vite planning and overview dashboard — use cases, feature
coverage, roadmap, comparison with OpenClaw, and similar reference material.
It is separate from the runtime: you don't need it to run agents or demo apps.

### Start the dashboard

```bash
cd ui
npm install        # first time only
npm run dev
```

Open **http://localhost:5173**

### Build for static hosting

```bash
cd ui
npm run build      # outputs to ui/dist/
npm run preview    # preview the build locally
```

---

## Development

### Repo layout

```
cuga-plusplus/
  packages/
    cuga-channels/      # channels, runtime host, client, planner, gateway
    cuga-runtime/       # LangGraph ReAct runtime + plugin registry
    cuga-skills/        # markdown skill loader
    cuga-plugin-sdk/    # shared types + plugin protocol
    cuga-checkpointer/  # SQLite conversation history
    cuga-triggers/      # standalone cron + webhook triggers
    cuga-watcher/       # in-process pub-sub watcher
    cuga-mcp/           # MCP server connector
  ui/                   # React/Vite planning dashboard (separate from runtime)
```

### Working on a package

Each package is a standalone Python project with its own `pyproject.toml`.
Install it editable into your shared venv:

```bash
# from repo root, with .venv active
pip install -e packages/cuga-channels
pip install -e packages/cuga-runtime
# etc.
```

All packages are installed editable (`-e`), so changes take effect immediately
without reinstalling.

### Keeping venvs lean

Each package directory may contain its own `.venv` from isolated installs.
For day-to-day development, use a single shared `.venv` at the repo root and
install all packages into it. The per-package `.venvs` can be deleted to save
disk space:

```bash
# remove per-package venvs (safe if you have a shared root venv)
find packages -name ".venv" -type d -maxdepth 2 -exec rm -rf {} +
```
