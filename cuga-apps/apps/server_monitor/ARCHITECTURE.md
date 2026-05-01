# Server Monitor — Architecture

## Design principle

**The app does all metric collection, threshold checking, and alert timing.
The agent is called only when human-readable diagnosis or free-form Q&A is needed.**

Threshold comparison is a number check — no LLM needed. The agent earns its place
by diagnosing *why* something is wrong, not by detecting *that* something is wrong.

---

## Component map

```
┌─────────────────────────────────────────────────────────────────┐
│  App layer (main.py)                                            │
│                                                                 │
│  ┌─────────────────────┐                                        │
│  │ asyncio monitor     │                                        │
│  │ loop                │                                        │
│  │ polls every N sec   │                                        │
│  └──────────┬──────────┘                                        │
│             │                                                   │
│             ▼                                                   │
│  ┌─────────────────────┐    no breach → sleep, loop            │
│  │ metrics.py          │─────────────────────────────────┐     │
│  │ (psutil, no LLM)    │                                 │     │
│  │ cpu / ram / disk    │  breach + cooldown elapsed?     │     │
│  └──────────┬──────────┘         │                       │     │
│             │                    ▼ yes                   │     │
│             │           ┌────────────────┐               │     │
│             │           │   CugaAgent    │               │     │
│             │           │                │               │     │
│             │           │ tools:         │               │     │
│             │           │  get_metrics   │               │     │
│             │           │  top_procs     │               │     │
│             │           │  disk_usage    │               │     │
│             │           │  large_files   │               │     │
│             │           │  svc_status    │               │     │
│             │           │  safe_cmd      │               │     │
│             │           │                │               │     │
│             │           │  → diagnosis   │               │     │
│             │           └────────┬───────┘               │     │
│             │                    │                       │     │
│             │                    ▼                       │     │
│             │           _alert_log[] (in-memory, cap 50) │     │
│             └───────────────────────────────────────────▶┘     │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  FastAPI web UI                                          │   │
│  │  /metrics   → metrics.py direct (no agent)             │   │
│  │  /ask       → agent.invoke(question)                   │   │
│  │  /alerts    → read _alert_log                          │   │
│  │  /check-now → trigger immediate monitor cycle          │   │
│  │  /settings  → read/write .store.json                  │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## What the app owns

| Responsibility | How |
|---|---|
| Metric collection | `metrics.py` — psutil, no LLM |
| Threshold checking | Numeric comparison in `_monitor_loop` |
| Cooldown tracking | `_last_alert_ts` float, compared to `time.time()` |
| Alert log | In-memory list capped at 50 entries |
| Settings persistence | `.store.json` via `json` stdlib |
| Web UI | FastAPI + inline HTML |
| Live metric gauges | `/metrics` endpoint reads psutil directly |

## What CugaAgent owns

| Responsibility | How |
|---|---|
| Threshold breach diagnosis | Receives metrics snapshot, uses tools to investigate |
| Ad-hoc health Q&A | Receives user question, uses tools to answer |

---

## Agent configuration

```python
CugaAgent(
    model   = create_llm(...),
    tools   = _make_tools(),      # 6 read-only tools (see below)
    plugins = [CugaSkillsPlugin(...)],
)
```

## Agent tools

All tools are **read-only**. The skill file explicitly instructs the agent to
never suggest destructive operations.

| Tool | Source | Purpose |
|---|---|---|
| `get_system_metrics` | `metrics.get_system_metrics()` | Full snapshot with severity |
| `list_top_processes` | `metrics.list_top_processes()` | Top N by CPU or memory |
| `check_disk_usage` | `metrics.check_disk_usage()` | Directory breakdown |
| `find_large_files` | `metrics.find_large_files()` | Files over N MB |
| `get_service_status` | `metrics.get_service_status()` | systemctl / launchctl |
| `run_safe_command` | subprocess with allowlist | df, du, uptime, ps, netstat, etc. |

`run_safe_command` blocks pipes, semicolons, and all shell metacharacters. Only
commands matching an explicit prefix allowlist are executed.

---

## Background monitor data flow

```
1.  App: psutil snapshot → check cpu/ram/disk vs thresholds
2.  No breach → sleep(poll_interval), loop

3.  Breach detected AND cooldown elapsed:
      → build message: "WARNING: cpu=91% ram=88%\n{json metrics}"
      → agent.invoke(message, thread_id="server-alert-{severity}")
          → agent calls get_system_metrics()  (fresh snapshot)
          → agent calls list_top_processes()  (if cpu high)
          → agent calls check_disk_usage()    (if disk high)
          → agent returns diagnosis report

4.  App: append { severity, alerts, diagnosis, timestamp } to _alert_log
5.  App: update _last_alert_ts = now
6.  Browser alert log auto-refreshes every 10s
```

## Chat data flow

```
1.  User types: "What's using the most CPU?"
2.  POST /ask { question }
3.  agent.invoke(question, thread_id="chat")
      → agent calls list_top_processes(by="cpu")
      → agent returns: "Top CPU consumers: python (34%), chrome (18%)..."
4.  Browser displays answer
```

---

## Safety constraints

- **No write tools** — the agent cannot modify files, kill processes, or restart services
- **Service allowlist** — `get_service_status` only queries services in `ALLOWED_SERVICES`
- **Command allowlist** — `run_safe_command` checks prefix against an explicit list
- **Shell injection blocked** — all metacharacters (`;`, `&&`, `|`, `` ` ``, `$`) are rejected
- **Skill instructions** — `server_health.md` tells the agent: never suggest `rm`, never kill PIDs, always recommend human confirmation for restarts
