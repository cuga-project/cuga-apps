# Bird Invocable API Creator

A FastAPI app that turns a [Bird-SQL](https://bird-bench.github.io/) database
(sqlite + NL/SQL question pack) into a **validated invocable API** plus a
per-question **ground-truth tool-call sequence dataset**, then emits a runnable
MCP server you can plug into any tool-calling agent for benchmarking.

**Port:** 28815 → http://localhost:28815

```
   ┌─────────────────────────────────────────────────────────────────┐
   │  bird_invocable_api_creator (this app, port 28815)              │
   │  ┌─────────────────────────────────────────────────────────┐    │
   │  │   CugaAgent  ←─── system prompt (synthesis policy)      │    │
   │  │      │                                                   │    │
   │  │      │ tool calls                                       │    │
   │  │      ▼                                                   │    │
   │  │   15 MCP tools (mcp-invocable_apis, port 29107)          │    │
   │  └─────────────────────────────────────────────────────────┘    │
   │            │                       │                            │
   │            ▼                       ▼                            │
   │   ┌──────────────────┐   ┌─────────────────────────┐            │
   │   │ Bird sqlite (RO) │   │  state registry         │            │
   │   │  + dev.json      │   │  (tools, sequences,     │            │
   │   │                  │   │   validations, ignored) │            │
   │   └──────────────────┘   └─────────────────────────┘            │
   │                                       │                          │
   │                                       ▼                          │
   │                         output/<db>/<db>_*.{py,json}            │
   └─────────────────────────────────────────────────────────────────┘
```

---

## What problem does this solve?

You have a Bird-SQL database — say `california_schools` — with 89 NL questions
each paired with a gold SQL query. You want to turn this into:

1. A small, reusable, parametric **API surface** (Python tools) that, when
   composed in sequences, can answer every NL question.
2. A **ground-truth dataset** mapping each NL question to the exact tool-call
   sequence that answers it.
3. A **runnable MCP server** exposing the tools so other agents can be
   benchmarked against the same API.

Done well, the API is small (a few dozen tools cover all 89 questions), tools
are reused across questions, sequences are sometimes multi-step (the gold SQL
has subqueries that decompose naturally), and every record carries proof its
tool sequence reproduces the gold SQL result on the actual sqlite.

This is a generic pipeline. Bird is just one input — point it at any sqlite
+ NL/SQL pack and it produces the same artifact shape.

---

## Why CUGA? Why not a one-shot LLM script?

This is the most important question this README answers. The naive approach —
"LLM, here's the gold SQL, write me a Python tool" — is 50 lines of code. So
why pull in CUGA, an MCP server, and 15 tools?

### What a one-shot script gets you

A `for question in dev.json: tool = llm("convert this SQL to a function")`
loop. It will:

- Produce *something* for every question (an LLM that's seen Python and SQL
  rarely refuses).
- Run fast and look impressive in a demo.

It will also, silently:

- Hallucinate column names ("the `enrollment` column" when the column is
  actually ``"`Enrollment (K-12)`"``).
- Miss case sensitivity (gold uses `'Alameda'`; LLM emits a tool that fails
  on `'alameda'`).
- Hardcode literals (`WHERE county = 'Alameda'` instead of a `county_name`
  parameter).
- Produce 89 unique tools for 89 questions — zero reuse, no API surface
  worth calling.
- Give you no way to know any of this without running each tool against the
  database and diffing against gold yourself.

A one-shot script is a SQL-to-Python *transpiler* with no oracle. You'll
discover its bugs after burning a thousand tokens on a downstream benchmark.

### What CUGA brings: a closed-loop synthesis agent

CUGA is not "the LLM that writes the code." CUGA is the **multi-turn loop**
that:

1. **Orients** before designing — calls `db_get_schema`, `db_sample_rows`,
   `db_run_sql SELECT DISTINCT col` to learn the actual column names, types,
   and value vocabularies. The LLM doesn't guess.

2. **Reads the oracle** — calls `bird_run_gold(qid)` to capture the
   canonical answer. Now there's a target the synthesis must hit.

3. **Reasons about decomposition** — looks at the gold SQL's structure
   (subqueries? CTEs? joins?) and decides how many tools the question needs.
   For qid 28 ("schools whose enrollment difference exceeds the average for
   locally-funded schools"), it factors the subquery into its own tool and
   chains via variable binding.

4. **Reuses what already exists** — calls `tool_list` first; if a tool that
   answers the question with different args is already registered, it's
   reused, not duplicated. The server enforces this with hard guards
   (forbidden-name patterns, SQL-skeleton equality, ≥85% name-token overlap
   → rejection).

5. **Validates closed-loop** — registers each new tool, immediately
   `tool_call`s it to confirm it executes on real sqlite, records the
   sequence, then `seq_validate`s — runs the recorded sequence end-to-end
   and **compares the composed result to the gold SQL result** on the actual
   sqlite. Pass-or-fail, not vibes.

6. **Course-corrects** — if validation fails, the failure message points at
   the offending tool. The agent re-registers it (fixing the bug), re-runs
   `seq_validate`. Up to 2 retries before fallback.

7. **Accumulates state** — every tool registered for question N is visible
   when synthesizing question N+1. The API surface shrinks over the batch.
   This is the meta-moat: the dataset's value is proportional to how
   compositional the API surface is.

### Concrete value the loop delivers

| Without CUGA (one-shot script) | With CUGA |
|---|---|
| Tool's column name might be wrong | `db_get_schema` is called first; LLM only writes columns it has seen |
| `WHERE col = 'Alameda'` (hardcoded literal) | Slot-value discovery: `SELECT DISTINCT col` + lift to a parameter, populate `examples` from OTHER values (not the question's literal — the answer isn't leaked) |
| 89 unique tools for 89 questions | Reuse imperative + server-side near-duplicate guard → smaller, composable API surface |
| Single-tool-per-question always | Decomposition signals (subqueries, CTEs) → 2-step sequences chained via `{{varname}}` binding |
| No oracle; can't tell pass from fail | Every record has `validated: bool`; comparator handles dict-of-list-of-dicts vs SQL-tuples; `failure_msg` for failed cases |
| Generated code is a black box | Tools are stored in a sqlite registry, browsable in the UI, with persisted `tool_usage.json` showing which qids reference each tool |
| If a tool is buggy, you find out at downstream eval time | Every emitted tool has executed against real sqlite + been compared to gold. Trustworthy by construction. |

### A worked example (qid 28)

NL: *"Consider the average difference between K-12 enrollment and 15-17
enrollment of schools that are locally funded; list the names and DOC type
of schools which has a difference above this average."*

A one-shot script would emit something like:

```python
def question_28(conn):
    return conn.execute("""<the gold SQL pasted in>""").fetchall()
```

— hardcoded `'Locally funded'`, no parameters, no reuse, dies if the
column name has a typo, never tested.

CUGA's loop produces:

1. `db_get_schema` → confirms `frpm.Enrollment (K-12)`, `schools.FundingType`.
2. `db_sample_rows("schools", n=5)` → sees `FundingType` values look free-form.
3. `db_run_sql("SELECT DISTINCT FundingType FROM schools")` → `['Directly funded', 'Locally funded', 'Not in CS funding model']`.
4. `bird_get_question(28)`, `bird_run_gold(28)` → 57-row gold result.
5. *Reasoning*: "the gold SQL has a subquery — strong decomposition seam.
   Two reusable tools: one for the average, one for the filter."
6. `tool_register(avg_enrollment_difference_by_funding_type, slot funding_type with examples ['Directly funded', 'Not in CS funding model'])` — note: 'Locally funded' is the *answer*, so it's NOT in examples.
7. `tool_call(... funding_type="Locally funded")` → `{avg_difference: 16.7}`. Verified.
8. `tool_register(schools_with_enrollment_difference_above, slots funding_type + threshold)`.
9. `tool_call(... threshold=16.7, funding_type="Locally funded")` → 57 schools. Verified.
10. `seq_record(qid=28, [step1 with bind="avg", step2 with threshold="{{avg.avg_difference}}"])`.
11. `seq_validate(28)` → `passed=True` (set-equality vs gold).

Now `avg_enrollment_difference_by_funding_type(funding_type)` is in the
registry. When the agent later hits qid 47 ("avg enrollment difference for
*directly* funded schools"), it sees this tool in `tool_list`, reuses it
with `funding_type='Directly funded'`, and doesn't register a sibling.
That's the value.

### Could you build this without CUGA?

You could build *something*. Replicating CUGA's value would require:

- A multi-step orchestrator that lets the LLM call schema + sample tools
  before designing.
- A persistent registry across questions.
- An execution-and-validation harness with diff feedback.
- A guard layer rejecting forbidden names + duplicates.
- Retry/fallback logic.

That's CUGA. The choice isn't "use CUGA or write 50 lines." It's "use CUGA
or rebuild a worse version of CUGA inline." The MCP boundary also means the
synthesizer (this app) is independent of the synthesis primitives (the MCP
server) — point a different agent at the same MCP server, or point this
agent at a different MCP server, and everything keeps working.

---

## Architecture

Three layers:

1. **`bird_invocable_api_creator`** (this app, port 28815) — FastAPI shell
   wrapping a `CugaAgent`. The agent is bound to the 15 MCP tools and a
   long [system prompt](main.py) that defines the synthesis policy.
   Endpoints (see below) drive single-question or batch synthesis.

2. **`mcp-invocable_apis`** ([mcp_servers/invocable_apis/server.py](../../mcp_servers/invocable_apis/server.py),
   port 29107) — exposes 15 primitives the agent calls. Owns the per-DB
   sqlite registry where tools, sequences, validations, and ignore flags
   live.

3. **The Bird data** — sqlite databases under `BIRD_DBS_DIR` (read-only),
   and `dev.json` at `BIRD_DEV_JSON`. Both are configurable via env.

The 15 MCP tools fall into 5 groups:

| Group | Tools | Role |
|---|---|---|
| `db_*` | `db_get_schema`, `db_sample_rows`, `db_run_sql` | Read-only sqlite introspection |
| `bird_*` | `bird_list_databases`, `bird_list_questions`, `bird_get_question`, `bird_run_gold` | Bird question + oracle access |
| `tool_*` | `tool_register`, `tool_list`, `tool_get`, `tool_call`, `tool_delete` | Per-DB synthesized-tool registry |
| `seq_*` | `seq_record`, `seq_execute`, `seq_validate` | Per-question tool-call sequence ground truth |
| `dataset_*` | `dataset_emit` | Freeze the registry → on-disk artifacts |
| `ignore_*` | `ignore_set`, `ignore_list` | Manual review flag |

---

## Output artifacts (per database)

After batch + emit, you get under `output/<db>/`:

| File | Content |
|---|---|
| `<db>_tools.py` | Every registered tool as a plain Python function. Importable. |
| `<db>_tools.json` | `{name, description, params_schema, return_description}` per tool. |
| `<db>_dataset.json` | Array of records, one per Bird `question_id`: NL question, evidence, gold SQL, gold result, recorded tool sequence, per-step outputs, final result, `validated`, `failure_msg`, `ignored`, `ignore_reason`. |
| `<db>_mcp_server.py` | Standalone runnable MCP server exposing every tool with the right signatures — point any agent at it for benchmarking. |
| `<db>_validation_report.json` | Coverage stats: totals, validation pass/fail counts, multi-step counts, sequence-length distribution, reuse counts, pass-rate %. |
| `<db>_tool_usage.json` | For each tool: name, description, params_schema, **`used_by_question_ids`** list, `reuse_count`. The browse-the-API artifact. |

Every file is suffixed with `<db>` so artifacts from all 11 Bird DBs can be
flattened into a single directory without collisions.

Bird counts are preserved: 89 questions in → 89 records in `dataset.json`.
Failed questions stay with `validated: false` + `failure_msg` so the gap
is auditable, not silently swept.

---

## The synthesis loop, step-by-step

When you POST `/question/california_schools/0`, here's exactly what CUGA does
(observable by tailing the apps log):

```
1.  bird_get_question(db='california_schools', question_id=0)
    → {question, evidence, SQL, difficulty}
2.  bird_run_gold(db, 0)              # the oracle
    → {result: {rows: [[1.0]], columns: [...]}}
3.  db_get_schema(db)                 # only on first question
    → {tables: [...], foreign_keys: [...]}
4.  tool_list(db)                     # what's already registered
    → {tools: []}                       # empty on first qid
5.  db_sample_rows("frpm", n=5)       # value-shape check
    → 5 rows; agent sees `County Name` is free-text
6.  db_run_sql("SELECT DISTINCT `County Name` FROM frpm ORDER BY 1")
    → ['Alameda', 'Alpine', 'Amador', ..., 'Yuba']      # 58 counties
7.  Reasoning: "single conceptual op + no subquery → 1 tool.
    `examples` for county_name should NOT include 'Alameda'
    (the question's literal). Pick 'Los Angeles', 'San Diego', 'Sacramento'."
8.  tool_register(name='get_highest_free_meal_ratio_by_county', ...
                  code uses ? placeholder + COLLATE NOCASE,
                  examples=['Los Angeles','San Diego','Sacramento'])
    → registered
9.  tool_call(name=..., args={'county_name': 'Alameda'})
    → {output: {rate: 1.0}}              # smoke-tested, real
10. seq_record(qid=0, sequence=[
      {tool: 'get_highest_free_meal_ratio_by_county',
       args: {county_name: 'Alameda'}}
    ])
11. seq_validate(qid=0)
    → {passed: true, gold_result: [[1.0]], final_result: {rate: 1.0}}
```

For multi-step questions like qid 28, steps 8–10 expand: two tools registered
and tool_called, the sequence has two steps with `bind` + `{{var}}` binding.

The app verifies each agent.invoke by re-calling `seq_validate` server-side,
so the job log records `recorded` and `passed` — a chatty agent that didn't
actually call tools won't masquerade as completion.

---

## Quality guards

These exist because the LLM, even with a good system prompt, will sometimes
take shortcuts. The server enforces hard rules:

- **Forbidden tool-name patterns** — `tool_register` rejects names matching
  `question_*`, `q<N>*`, `*_wrapper`, `*_solver`, `gold_*`, `fallback_*`,
  `generic_*`, `todo_*`. Returns `tool_error(code='forbidden_name')`.

- **Near-duplicate detection** — for each new tool registration:
  - **SQL-skeleton equality** (literals stripped) → reject (`duplicate_sql_skeleton`).
  - **Name-token Jaccard ≥ 0.85** → reject (`near_duplicate_name`).
  - The 0.85 threshold lets `..._by_county` vs `..._by_district` through;
    only catches cosmetic dups (`..._v2`, dropped `get_` prefix).
  - The error message names the existing tool so the agent has a clear
    next step (reuse with different args, or `tool_delete` + re-register
    broader).

- **Re-registering the SAME name** is allowed (fix-in-place is the
  intended path for course-correcting a buggy tool).

- **`exec()` sandbox** — generated tool code runs with `sqlite3` / `json` /
  `re` only, on a `mode=ro` connection. Cannot mutate the Bird data.

- **System-prompt rules** — slot examples must NOT contain the question's
  literal value (otherwise the dataset leaks the answer). Slot value
  vocabularies come from `db_run_sql SELECT DISTINCT`. String-equality
  predicates use `COLLATE NOCASE` so callers don't have to know exact case.

---

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET  | `/health` | liveness |
| GET  | `/databases` | list discoverable Bird DBs (passthrough to MCP) |
| GET  | `/questions/{db}` | Bird question summary list |
| GET  | `/qmeta/{db}/{qid}` | full Bird record (NL + evidence + SQL) |
| GET  | `/dataset/{db}` | live registered tools + question count |
| GET  | `/dataset_full/{db}` | the entire emitted `dataset.json` (UI consumes this) |
| GET  | `/stats/{db}` | aggregate stats from emitted dataset (UI panel) |
| GET  | `/record/{db}/{qid}` | single record from emitted dataset |
| GET  | `/tools_full/{db}` | tool browser feed (uses `tool_usage.json` if emitted) |
| POST | `/question/{db}/{qid}` | **interactive demo**: run agent on one question |
| POST | `/synthesize/{db}` | batch: agent walks every question (returns `job_id`) |
| GET  | `/jobs/{job_id}` | batch progress: `{processed, recorded, passed, total, status}` |
| POST | `/emit/{db}` | re-freeze artifacts to `output/<db>/` |
| POST | `/ignore/{db}/{qid}` | toggle the manual ignore flag (re-emits) |
| GET  | `/` | HTML UI |

---

## UI

Open http://localhost:28815/ to drive the whole pipeline:

- **Database picker** + **Batch synthesize** button with live progress bar
  and per-question recorded/passed counters.
- **Question list** with status icons (`✓ pass`, `✗ fail`, `⊘ ignored`,
  `· no seq`) and filter pills.
- **Stats panel** with 8 tiles + sequence-length distribution. The
  *"tools reused across qs"* tile is yellow at 0 — that's the meta-moat
  alarm; non-zero means decomposition is producing real reuse.
- **Question inspector** showing NL + evidence + gold SQL + recorded
  sequence + each step's tool description + slot list + final-vs-gold +
  failure message + buttons to re-run the agent or toggle ignore.
- **Tool browser** card listing every registered tool with name, reuse
  badge, description, slot pills (name : type with enum/examples preview).
  Filter by name; sort by most-reused / least-reused / name. Click a tool
  to see the qids that reference it.

---

## Run

### Docker (recommended)

```bash
cd /home/amurthi/work/agent-apps/cuga-apps

# Configure LLM in apps/.env
cat >> apps/.env <<'EOF'
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-4-6
ANTHROPIC_API_KEY=sk-ant-...
EOF

docker compose up -d --build mcp-invocable_apis apps mcp-tool-explorer
open http://localhost:28815
```

### Local (no docker)

```bash
python apps/launch.py start mcp-invocable_apis bird_invocable_api_creator
```

Both paths require Bird data accessible at `BIRD_DEV_JSON` and
`BIRD_DBS_DIR` (the MCP server reads these — see Configuration below).

### Verify it's working

```bash
# 1) MCP server sees Bird DBs
curl -s http://localhost:28815/databases | jq
# → {"databases": ["california_schools", "card_games", ...]}

# 2) Bird questions accessible
curl -s http://localhost:28815/questions/california_schools | jq '.data.count'
# → 89

# 3) Run agent on one question (requires LLM_PROVIDER configured)
curl -sX POST http://localhost:28815/question/california_schools/0 \
     -H 'Content-Type: application/json' -d '{}' | jq
# Response includes verification: {recorded: bool, passed: bool}
```

---

## Configuration

| Env var | Default | Read by |
|---|---|---|
| `BIRD_DEV_JSON` | `/home/amurthi/work/dev_20240627/dev.json` | mcp-invocable_apis |
| `BIRD_DBS_DIR` | `/home/amurthi/work/enterprise-benchmark/data/db` | mcp-invocable_apis |
| `INVOCABLE_APIS_STATE_DIR` | `mcp_servers/invocable_apis/state` | mcp-invocable_apis |
| `BIRD_DEV_JSON_HOST` | (unset → falls back to default) | docker-compose bind-mount source |
| `BIRD_DBS_DIR_HOST` | (unset → falls back to default) | docker-compose bind-mount source |
| `LLM_PROVIDER` | — | this app |
| `LLM_MODEL` | — | this app |
| `MCP_INVOCABLE_APIS_URL` | derived from compose | this app (override only) |

---

## Trust boundary

Generated tool code is `exec()`'d in this app's MCP server on every
`tool_call`. The exec namespace is restricted to `sqlite3` / `json` / `re`.
The sqlite connection is opened with `mode=ro` URI. Generated code cannot
mutate the Bird data, can't import other modules, can't open files. That
said, it's running on the same host as the MCP server — don't point this
pipeline at sensitive sqlite files outside the Bird corpus.

---

## When you might *not* want CUGA

This loop is designed for **synthesizing tools you don't yet have**, where
each tool needs validation against an oracle. Cases where CUGA is overkill:

- You already have the API. You just want to **call** existing tools to
  answer NL questions — that's a normal tool-calling agent, not synthesis.
- You only have one question. CUGA's reuse + accumulation has nothing to
  cross-amortize.
- The "API" is allowed to be a black-box `def solve(q): return ...`. CUGA
  is for producing a *transparent, parametric, decomposed* API surface.

For everything else — converting any (sqlite + NL/SQL pack) into a
trustworthy invocable API + dataset — CUGA pays for itself by the time
you've batched 10 questions.

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

CUGA-driven synthesizer that turns Bird-SQL pairs into a validated invocable
API + ground-truth tool-call sequences.

**MCP servers consumed:**
- **mcp-invocable_apis** — `db_get_schema` · `db_sample_rows` · `db_run_sql` ·
  `bird_list_databases` · `bird_list_questions` · `bird_get_question` ·
  `bird_run_gold` · `tool_register` · `tool_list` · `tool_get` · `tool_call` ·
  `tool_delete` · `seq_record` · `seq_execute` · `seq_validate` ·
  `ignore_set` · `ignore_list` · `dataset_emit`

**Inline `@tool` defs:** none — every tool comes from MCP.

<!-- END: MCP usage -->
