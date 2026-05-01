# Chief of Staff — benchmark suite

> Machine-readable version: [`benchmark.json`](benchmark.json) — 70 cases with
> `id`, `section_id`, `phase`, `title`, `verdict`, `prompt`, `expected`,
> `bash_blocks`, and `tests` fields. Treat the JSON as the source of truth
> for tooling; this Markdown is the human-readable narrative.

Concrete test cases organized by capability + phase. Each example has:

- **The prompt** (what you type into the chat at `http://localhost:5174`)
- **Expected outcome** (what the system should do)
- **Why it's expected to work** (which subsystem handles it)
- **What it's testing architecturally**

## How to interpret each row

| Verdict | Meaning |
|---|---|
| ✅ Should work | Cuga answers directly, no acquisition needed |
| 🔧 Should auto-build a tool | Toolsmith acquires + mounts; second ask succeeds |
| 🔐 Should request credentials | Toolsmith returns `needs_secrets`; user pastes; second ask succeeds |
| 🌐 Should drive the browser | Phase-4 browser source; Toolsmith mounts a browser_task |
| ❌ Should fail cleanly | Toolsmith returns "no match" with an honest reason |
| ⚠️ Edge case | System should NOT crash; specific behavior described |

## Setup before running these

```bash
cd cuga-apps/chief_of_staff
docker compose down
docker compose build --no-cache
docker compose up -d
sleep 60
docker compose ps         # all 5 Up

# Verify each service
curl -s http://localhost:8000/health | jq        # cuga adapter
curl -s http://localhost:8001/health | jq        # toolsmith
curl -s http://localhost:8002/health | jq        # browser-runner
curl -s http://localhost:8765/health | jq        # backend
```

For tests requiring an LLM:
```bash
export TOOLSMITH_LLM_PROVIDER=rits
export TOOLSMITH_LLM_MODEL=gpt-oss-120b
# RITS_API_KEY in apps/.env
```

For tests requiring auth, you'll be prompted in the UI.

---

## Section A — Skeleton & infrastructure (1–8)

These prove the basic plumbing is alive.

### 1. Health checks across all services

```bash
curl -s http://localhost:8000/health http://localhost:8001/health \
        http://localhost:8002/health http://localhost:8765/health
```

✅ Expected: all four return `{"status":"ok",...}`. Backend health includes nested toolsmith health.
**Tests:** all services boot, can talk to each other.

### 2. Empty chat round-trip

**Prompt:** *"hello"*

✅ Expected: cuga responds with a greeting. No `acquisition` payload. Tools panel unchanged.
**Tests:** cuga adapter `/chat` works; orchestrator forwards correctly; UI renders.

### 3. Tools panel populates

Open `http://localhost:5174` in incognito. Header shows `tools: 10–15`.
✅ Expected: right-hand panel shows tools from `mcp-web`, `mcp-local`, `mcp-code` grouped under `MCP_SERVER`.
**Tests:** registry sync from cuga adapter on startup.

### 4. Direct cuga `/tools` endpoint

```bash
curl -s http://localhost:8000/tools | jq 'length'
```

✅ Expected: number ≥ 10. Each entry has `name`, `description`, `kind`.
**Tests:** cuga adapter exposes its loaded tools.

### 5. Direct toolsmith `/tools` (artifacts) endpoint

```bash
curl -s http://localhost:8001/tools | jq
```

✅ Expected: empty list on first run; grows as tools are acquired.
**Tests:** artifact persistence layer.

### 6. Effective state

```bash
curl -s http://localhost:8001/effective_state | jq
```

✅ Expected: `{mcp_servers: [], extra_tools: [], secrets: {}, blocked_artifacts: []}` initially.
**Tests:** the merged state the backend hands to cuga reload.

### 7. Vault status

```bash
curl -s http://localhost:8001/health | jq '.coder, .orchestration_llm, .artifact_count'
```

✅ Expected: `coder` is `gpt_oss` or `claude` per env; `orchestration_llm` true if RITS keys present.
**Tests:** Toolsmith config from env.

### 8. Frontend rebuild without backend

Stop just the backend:
```bash
docker stop cuga-apps-cos-backend
```
Hard-refresh `:5174`. Header shows `backend: backend-down`. Chat input still visible but submit fails gracefully.
✅ Expected: no JS crash. Bring backend back, refresh, normal operation.
**Tests:** frontend resilience.

---

## Section B — Catalog acquisition (phase 2) (9–14)

Tools that mount existing local MCP servers.

### 9. Wikipedia

**Prompt:** *"Look up the Eiffel Tower on Wikipedia."*

🔧 Expected:
- Cuga emits `[[TOOL_GAP]] {capability: "wikipedia search"}`
- Toolsmith catalog match → `Knowledge MCP`
- Green "Toolsmith built a tool" notice
- Tools panel grows by ~10 (knowledge tools)
- Re-ask gets a real Wikipedia summary

**Tests:** catalog source + live mount of an MCP server (no codegen).

### 10. Stock prices

**Prompt:** *"What's NVIDIA's current stock price?"*

🔧 Expected:
- Catalog match → `Finance MCP`
- After install, re-ask returns a real quote.

**Tests:** catalog matching across different domain.

### 11. Geocoding

**Prompt:** *"What are the lat/lon for Paris, France?"*

🔧 Expected:
- Catalog match → `Geo MCP`
- After install, geocode tools available.

**Tests:** geo MCP mount.

### 12. PDF text extraction

**Prompt:** *"Extract text from this PDF: https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"*

🔧 Expected:
- Catalog match → `Text MCP`
- After install, returns the PDF's text.

**Tests:** text MCP mount with URL parameter.

### 13. Multiple catalog acquisitions in sequence

**Prompts (in same chat):**
1. *"Wikipedia search the moon landing"* → Knowledge
2. *"What's the weather in Tokyo?"* → Geo (or OpenAPI Open-Meteo — see #18)
3. *"What's MSFT stock price?"* → Finance

🔧 Expected: tools panel grows with each successful install. No conflicts.
**Tests:** activations table records all approvals; planner state survives.

### 14. Direct catalog API

```bash
curl -s http://localhost:8765/toolsmith/artifacts | jq '.[] | select(.id | startswith("catalog__"))'
```

✅ Expected: lists installed catalog mounts.
**Tests:** persistence of catalog choices.

---

## Section C — OpenAPI no-auth tools (phase 3) (15–22)

Tools generated from public APIs that need no credentials.

### 15. Random joke

**Prompt:** *"Tell me a random joke."*

🔧 Expected:
- Catalog miss; OpenAPI match → `Official Joke API`
- Toolsmith generates `get_random_joke` via the Coder, probes (URL probe + exec probe)
- Artifact saved to `data/tools/openapi__get_random_joke/`
- Re-ask returns a real joke

**Tests:** OpenAPI source + Coder + probe + persistence.

### 16. Country information

**Prompt:** *"Tell me about France: capital, population, currency."*

🔧 Expected: OpenAPI match → `Country Info API`. Path-param substitution (`/name/{name}`).
**Tests:** path parameter handling in generated code.

### 17. Open-Meteo weather

**Prompt:** *"What's the current weather at lat 35.67, lon 139.65?"*

🔧 Expected: OpenAPI match → Open-Meteo. No auth needed.
**Tests:** numeric parameters; multi-param GET.

### 18. Multiple no-auth tools coexist

After running 15, 16, 17:
```bash
curl -s http://localhost:8000/health | jq '.extra_tool_count'
```

✅ Expected: `extra_tool_count >= 3`. All three coexist in cuga.
**Tests:** multiple generated tools mounted simultaneously.

### 19. Inspect a generated tool's code

```bash
docker exec cuga-apps-cos-toolsmith \
  cat /app/chief_of_staff/data/tools/openapi__get_random_joke/tool.py
```

✅ Expected: real Python with `httpx.AsyncClient`, no extras. Function name matches.
**Tests:** Coder output quality; artifact format.

### 20. Probe rejects a broken endpoint

Edit `spec_index.yaml` to change the joke path to `/nonexistent`, restart toolsmith:
```bash
docker compose restart chief-of-staff-toolsmith
```
**Prompt:** *"Tell me a random joke."*

❌ Expected: probe fails (`http 404` or similar). Artifact NOT registered. UI shows amber failure card.
**Tests:** probe gate filters broken tools.

### 21. Use the same tool twice in one chat

After installing the joke tool:
**Prompts:**
1. *"Tell me a joke."* → real joke
2. *"Tell me another joke."* → another real joke (no new acquisition)

✅ Expected: cuga calls the same tool twice. Tools panel doesn't grow on the second ask.
**Tests:** tool reuse without re-acquisition.

### 22. APIs.guru search (LLM path only)

With `TOOLSMITH_LLM_PROVIDER=rits` set:
**Prompt:** *"Convert 100 USD to JPY."*

🔧 Expected (with LLM): Toolsmith ReAct calls `search_apis_guru_directory`, finds e.g. Frankfurter. Builds tool.
❌ Expected (no LLM): falls through to deterministic; no match.
**Tests:** apis.guru integration in the ReAct path.

---

## Section D — Authenticated APIs (phase 3.6) (23–30)

### 23. GitHub bearer-token auth

**Prompt:** *"Search GitHub for popular Python repositories."*

🔐 Expected:
- OpenAPI match → `GitHub Search API`
- Credential prompt asks for `github_token`
- Provide a real PAT (any token; public search needs no scope)
- Re-ask: real repo list

**Tests:** bearer_token auth scheme; vault put; secret injection at call time.

### 24. OpenWeather query-param auth

**Prompt:** *"What's the current weather in Tokyo using OpenWeather?"*

🔐 Expected:
- Credential prompt asks for `openweather_api_key`
- Provide a real key (free at openweathermap.org)
- Re-ask: real current weather

**Tests:** api_key_query auth scheme.

### 25. Inspect generated auth-aware code

```bash
docker exec cuga-apps-cos-toolsmith \
  cat /app/chief_of_staff/data/tools/openapi__github_search_repos/tool.py
```

✅ Expected: function signature ends with `, github_token: str`. Body uses `Authorization: Bearer ${github_token}` header.
**Tests:** Coder honors auth scheme.

### 26. Vault list-keys (no values)

```bash
curl -s http://localhost:8765/vault/keys/openapi__github_search_repos | jq
```

✅ Expected: `{"tool_id":..., "keys": ["github_token"], "backend": "sqlite"}`. Values never returned.
**Tests:** vault privacy.

### 27. Programmatic vault put

```bash
curl -s -X POST http://localhost:8765/vault/secret \
  -H 'Content-Type: application/json' \
  -d '{"tool_id":"openapi__openweather_current","secret_key":"openweather_api_key","value":"YOUR_KEY"}'
```

✅ Expected: `{"stored":true, ...}`. Asking the weather question now skips the credential prompt.
**Tests:** vault API; backend resync after vault change.

### 28. Bad credentials fail cleanly

Provide a fake GitHub token. Re-ask the GitHub question.

❌ Expected: cuga calls the tool, GitHub returns 401, the tool errors. UI shows the error in the chat. **System does not crash.**
**Tests:** error propagation from generated code.

### 29. Hostile imports rejected

Manually drop a malicious artifact (per the README's Test 5 sandbox check).

⚠️ Expected: adapter logs `Artifact 'manual__danger' rejected: disallowed import: 'subprocess'`. Tool registers as a stub that errors on call.
**Tests:** import allowlist sandbox.

### 30. Persistence across restart

Build any auth tool. Then:
```bash
docker compose restart chief-of-staff-backend chief-of-staff-adapter
sleep 30
curl -s http://localhost:8000/health | jq '.extra_tool_count, .tools_with_secrets'
```

✅ Expected: counts unchanged. The vault still has the secret. The tool still works.
**Tests:** full persistence chain (vault + artifacts + reload).

---

## Section E — OAuth2 (phase 3.7) (31–36)

### 31. Gmail send needs four credentials

**Prompt:** *"Send an email through Gmail."*

🔐 Expected: credential prompt has FOUR fields:
- `gmail_access_token`
- `gmail_refresh_token`
- `google_oauth_client_id`
- `google_oauth_client_secret`

Help text walks through obtaining them via the OAuth playground.
**Tests:** oauth2_token auth scheme; multi-secret prompt.

### 32. After OAuth setup, send a test email

After providing the four secrets:
**Prompt:** *"Send a test email to myself with subject 'hello' and body 'this is a test'."*

🔧 Expected: cuga constructs the RFC 2822 message, base64-encodes it, calls `gmail_send_message`. Real email arrives.
**Tests:** end-to-end OAuth2 flow + Gmail API.

### 33. Token refresh on 401

Force-expire the access token:
```bash
curl -s -X POST http://localhost:8765/vault/secret \
  -H 'Content-Type: application/json' \
  -d '{"tool_id":"openapi__gmail_send_message","secret_key":"gmail_access_token","value":"definitely_expired"}'
```

Try sending an email again.

🔧 Expected:
- First call gets 401 from Gmail
- Adapter posts to `https://oauth2.googleapis.com/token` with the refresh token
- Receives a new access token, retries, succeeds
- Vault now has the fresh token

```bash
docker logs cuga-apps-cos-adapter --tail 30 | grep OAuth2
# → "OAuth2 refresh succeeded for 'openapi__gmail_send_message'"
```

**Tests:** OAuth2 refresh path.

### 34. Google Calendar list events

After installing GCal (same OAuth playground, `calendar.events` scope):
**Prompt:** *"What's on my Google Calendar this week?"*

🔧 Expected: cuga calls `gcal_list_events` with `timeMin/timeMax`, returns real events.
**Tests:** OAuth2 scheme reuse across multiple endpoints.

### 35. Multi-tool composition (Gmail + GCal)

After installing both:
**Prompt:** *"What's on my calendar tomorrow? Send me an email summary."*

🔧 Expected:
- Cuga calls `gcal_list_events` (tomorrow's range)
- Constructs an email with the events
- Calls `gmail_send_message`
- Both tools used in a single conversation, no extra acquisitions

**Tests:** cuga composes multiple acquired tools.

### 36. OAuth2 secrets persist correctly

```bash
docker exec cuga-apps-cos-toolsmith \
  sqlite3 /app/chief_of_staff/data/vault.sqlite \
  "SELECT tool_id, secret_key FROM secret_keys ORDER BY tool_id"
```

✅ Expected: rows for both gmail and gcal, listing all four secret keys each.
**Tests:** vault index integrity for OAuth2.

---

## Section F — Code-revise loop (phase 3.8) (37–40)

### 37. Force a probe failure to trigger revision

Edit spec_index.yaml — change open-meteo's path to `/forecastz` (typo). Restart toolsmith.

**Prompt:** *"Open-Meteo current temperature for lat 0, lon 0."*

🔧 Expected:
- URL probe passes (api.open-meteo.com is reachable)
- Exec probe fails: 404 from the wrong path
- Coder asked to revise; given the 404 + response excerpt
- Coder emits a fixed path; re-probe passes
- Tool registers

```bash
docker exec cuga-apps-cos-toolsmith \
  cat /app/chief_of_staff/data/tools/openapi__get_open_meteo_forecast/manifest.yaml \
  | grep -A 10 revisions
# revisions:
#   - {attempt: 0, ok: false, reason: 'upstream http 404'}
#   - {attempt: 1, ok: true, ...}
```

**Tests:** Coder.revise_tool path; probe feedback threading.

### 38. Hopeless code → give up after max attempts

Construct a spec entry where the URL is fundamentally broken. Toolsmith should retry 3 times then give up.

❌ Expected: `success: false`, summary mentions "after 3 revision(s)". No artifact.
**Tests:** revise loop is bounded.

### 39. Revisions visible in artifact

For any tool that succeeded after one revision:
```bash
curl -s http://localhost:8001/tools/openapi__get_open_meteo_forecast | jq '.provenance.revisions'
```

✅ Expected: array of `{attempt, ok, reason}` entries.
**Tests:** provenance persistence.

### 40. Coder A/B comparison

```bash
TOOLSMITH_CODER=claude docker compose up -d chief-of-staff-toolsmith
sleep 5
curl -s http://localhost:8765/toolsmith/artifacts/openapi__get_random_joke
docker exec cuga-apps-cos-toolsmith \
  rm -rf /app/chief_of_staff/data/tools/openapi__get_random_joke
# Re-ask "Tell me a random joke" — Claude builds it this time.
docker exec cuga-apps-cos-toolsmith \
  cat /app/chief_of_staff/data/tools/openapi__get_random_joke/tool.py
```

✅ Expected: code generated by Claude is generally cleaner / more idiomatic. `provenance.coder == "claude"`.
**Tests:** Coder swappability mid-run.

---

## Section G — Browser tools (phase 4) (41–47)

### 41. Hacker News scrape

**Prompt:** *"What are the top 5 stories on Hacker News right now?"*

🌐 Expected:
- Catalog and OpenAPI sources miss
- BrowserSource matches `hn_top_stories`
- Toolsmith probes via browser-runner: opens news.ycombinator.com, extracts titles
- Probe passes → registers
- Tools panel shows `hn_top_stories` (kind: browser_task)
- Re-ask returns the actual current top stories

**Tests:** end-to-end browser tool path; phase-4 happy case.

### 42. Wikipedia website search (vs. API)

**Prompt:** *"Search Wikipedia website for 'quantum computing'."*

🌐 Expected: BrowserSource match → opens en.wikipedia.org/wiki/Special:Search, extracts result text.
**Tests:** browser tool with parameter substitution (`${query}` in URL).

### 43. GitHub repo About without a token

**Prompt:** *"What's the About text and star count for the python/cpython GitHub repo?"*

🌐 Expected: BrowserSource match → `github_repo_about` (no auth needed; scrapes the page).

> Note: the system prefers the OpenAPI GitHub Search API for queries that match its capabilities. This one specifically asks about the *About text* and *stars on a specific repo* — features that the search API doesn't expose well — so the browser source wins.

**Tests:** routing — browser source wins when API source isn't a great fit.

### 44. School portal login (template demo)

**Prompt:** *"Check my kid's school portal for grades."*

🔐🌐 Expected: BrowserSource match → `school_portal_grades`. Requires `school_portal_username` + `school_portal_password`. Credential prompt asks for both.

> The bundled template uses `https://example.school.example.com/login` — fictional. To make this actually work, copy the template, edit selectors for your real school portal. **The auth prompt + browser dispatch flow works regardless.**

**Tests:** browser tool with auth; template adaptability.

### 45. user_confirm pause

**Prompt:** *"Submit the form at https://httpbin.org/forms/post with my approval."*

🌐⚠️ Expected:
- BrowserSource match → `form_submit_with_confirm`
- Browser-runner navigates, fills form, **pauses** at the `user_confirm` step
- A webhook fires to `chief-of-staff-backend:8765/internal/browser_confirm`
- For now, default-deny (no UI yet for the prompt — see "Honest gap" below)

**Tests:** human-in-the-loop pattern; webhook path.

### 46. Browser-runner direct probe

```bash
curl -s -X POST http://localhost:8002/probe \
  -H 'Content-Type: application/json' \
  -d '{"steps":[{"go_to":"https://news.ycombinator.com"},{"wait_for_selector":"tr.athing"}],"sample_input":{}}'
```

✅ Expected: `{"ok":true,"reason":"completed",...}`. The runner handles probes independently of toolsmith.
**Tests:** browser-runner is an independent service.

### 47. Browser session persistence

After running a tool that logs in:
```bash
docker exec cuga-apps-cos-browser ls /data/profiles/
# → directory per provider used (default, school_portal, etc.)

docker compose restart chief-of-staff-browser
sleep 10
docker exec cuga-apps-cos-browser ls /data/profiles/
# → same directories; cookies survived
```

✅ Expected: profiles persist via the Docker volume. Subsequent invocations of logged-in tools reuse cookies (no re-login).
**Tests:** browser-runner volume persistence.

---

## Section H — Failure & edge cases (48–55)

### 48. Truly unsupported request

**Prompt:** *"Place a Whole Foods order for me using my Amazon account."*

❌ Expected:
- Catalog miss
- OpenAPI miss (no consumer Amazon API)
- Browser source has nothing for "place an order on Amazon" (not in the curated index, ToS reasons)
- UI shows amber "Toolsmith couldn't build a tool — No catalog, OpenAPI, or browser-task match for this gap"

**Tests:** honest "I can't do this" surface.

### 49. Cuga is down

```bash
docker stop cuga-apps-cos-adapter
```
**Prompt:** *"Hello"*

⚠️ Expected: backend stub-fallback responds with `[stub:cuga-unreachable] echo: hello`. UI header shows `agent: stub`. Bring it back: normal operation resumes.
**Tests:** graceful degradation.

### 50. Toolsmith is down

```bash
docker stop cuga-apps-cos-toolsmith
```
Trigger any gap.

⚠️ Expected: backend's acquire call fails; chat response includes `acquisition: {success: false, summary: "toolsmith unreachable: ..."}`. Cuga still answers from its existing tools.
**Tests:** graceful degradation when Toolsmith is unreachable.

### 51. Browser-runner is down

```bash
docker stop cuga-apps-cos-browser
```
Trigger a browser tool gap (e.g. *"Top Hacker News stories"*).

⚠️ Expected: Toolsmith's probe to the runner fails. Toolsmith logs the failure but **falls through to register without probing** — the tool will work once the runner is back. (Tradeoff: phase 4 v1 is permissive about probe failures so the system stays usable when the runner is briefly down.)
**Tests:** runner-down resilience.

### 52. Concurrent acquisitions (race)

In the UI, ask two tool-gap questions in rapid succession. Each should trigger a separate Toolsmith acquire.

✅ Expected: both succeed. No artifact corruption. Tools panel shows both eventually.
**Tests:** concurrent /acquire (Toolsmith holds a lock during agent rebuild).

### 53. Same gap asked from two browser tabs

Open two browser tabs, ask the same uninstalled-tool question in both at the same time.

⚠️ Expected: both attempts trigger an acquire. The second sees the first's artifact already exists (or both succeed and one overwrites; idempotent). No duplicate tool entries in the registry.
**Tests:** registry idempotence.

### 54. Remove a tool

```bash
curl -s http://localhost:8765/toolsmith/artifacts | jq '.[].id'
curl -s -X DELETE http://localhost:8765/toolsmith/artifacts/openapi__get_random_joke
```

✅ Expected: `{removed: true}`. Tool unmounts from cuga within seconds. Tools panel updates.
**Tests:** removal lifecycle.

### 55. Vault key cleared → tool blocks

```bash
curl -s -X POST http://localhost:8765/vault/delete \
  -H 'Content-Type: application/json' \
  -d '{"tool_id":"openapi__github_search_repos","secret_key":"github_token"}'

curl -s http://localhost:8001/effective_state | jq '.blocked_artifacts'
```

✅ Expected: GitHub tool now appears in `blocked_artifacts` because its required secret is gone. Adapter unmounts it on next reload. Re-supplying the secret re-mounts.
**Tests:** vault deletion → effective state → adapter dispatch.

---

## Section I — Multi-tool composition (56–62)

These prove cuga can chain *multiple* acquired tools in one conversation.

### 56. Wikipedia + Geo

After installing Knowledge MCP and Geo MCP:
**Prompt:** *"Tell me about Tokyo: a quick history and current weather."*

🔧 Expected: cuga calls `get_wikipedia_article` AND `get_weather` in one chain. One coherent response.
**Tests:** parallel tool use within a single planner call.

### 57. Country + Weather

After installing both:
**Prompt:** *"What's the capital of Japan and what's the weather there right now?"*

🔧 Expected: `get_country_by_name(name="Japan")` → "Tokyo"; then `openweather_current(q="Tokyo,JP")` or `get_weather(...)`.
**Tests:** sequential tool use with output→input passing.

### 58. GitHub + Knowledge

**Prompt:** *"Find the most popular Python ORM library on GitHub and look it up on Wikipedia."*

🔧 Expected: `github_search_repos(q="Python ORM")` → e.g. SQLAlchemy → `get_wikipedia_article(title="SQLAlchemy")`.
**Tests:** OpenAPI auth tool + catalog tool composition.

### 59. Web research + browser scrape

After installing HN browser tool:
**Prompt:** *"Find the top Hacker News story right now and summarize what's discussed."*

🔧🌐 Expected: `hn_top_stories` (browser) → titles. cuga's `fetch_webpage` (built-in) → article body. cuga summarizes.
**Tests:** browser tool + native cuga tool composition.

### 60. Three-tool chain

**Prompt:** *"Lookup France: capital, weather there, and any Wikipedia summary."*

🔧 Expected: country → weather → wikipedia → synthesized response.
**Tests:** ≥3 tools in one chat.

### 61. Two browser tools in one chat

After both `hn_top_stories` and `github_repo_about` are installed:
**Prompt:** *"What's the top HN story today, and tell me about whatever GitHub repo it links to."*

🔧🌐 Expected: cuga calls HN → extracts a GitHub URL → calls github_repo_about → returns combined info.
**Tests:** browser tool composition.

### 62. Email digest

With Gmail + GCal both installed:
**Prompt:** *"Summarize my upcoming week's calendar and email it to me."*

🔧🔐 Expected: gcal_list_events → cuga summarizes → gmail_send_message → real email arrives.
**Tests:** end-to-end OAuth2 + multi-tool + real-world action.

---

## Section J — Direct API surface (63–70)

Use these to verify endpoints directly without going through the chat UI.

### 63. Toolsmith /acquire direct

```bash
curl -s -X POST http://localhost:8001/acquire \
  -H 'Content-Type: application/json' \
  -d '{"gap":{"capability":"random joke"}}' | jq '{success, artifact_id, summary}'
```

✅ Expected: success: true, artifact_id starts with `openapi__`.
**Tests:** Toolsmith service is independently usable.

### 64. Browser-runner /execute direct

```bash
curl -s -X POST http://localhost:8002/execute \
  -H 'Content-Type: application/json' \
  -d '{"steps":[{"go_to":"https://news.ycombinator.com"},{"extract_text":{"selector":"tr.athing td.title:nth-of-type(2)","as":"first_title"}}],"inputs":{},"secrets":{}}' \
  | jq '{ok, extracted}'
```

✅ Expected: ok: true, extracted has `first_title` populated.
**Tests:** browser-runner is independently usable.

### 65. Catalog listing

```bash
curl -s http://localhost:8765/catalog | jq '.[] | {id, name, active}'
```

✅ Expected: 5 catalog entries; `active` reflects which have been installed.
**Tests:** catalog endpoint.

### 66. Effective state with mounted tools

After installing a few tools:
```bash
curl -s http://localhost:8001/effective_state | jq '{
    mcp_servers: .mcp_servers,
    extra_tools: (.extra_tools | length),
    blocked: (.blocked_artifacts | length)
  }'
```

✅ Expected: numbers match what's installed.
**Tests:** effective state aggregation.

### 67. Adapter health includes secret count

```bash
curl -s http://localhost:8000/health | jq
```

✅ Expected: includes `tools_with_secrets` (count of tools that have at least one secret in `_State.secrets`).
**Tests:** adapter reports its full state.

### 68. Tools refresh

```bash
curl -s -X POST http://localhost:8765/tools/refresh | jq
```

✅ Expected: `{synced: N}` where N matches current tool count.
**Tests:** registry sync from adapter.

### 69. Browser session listing

```bash
curl -s http://localhost:8002/sessions/default | jq
curl -s http://localhost:8002/sessions/school_portal | jq
```

✅ Expected: per-provider profile state (exists, size_bytes).
**Tests:** browser-runner session metadata.

### 70. Clear a browser session

```bash
curl -s -X POST http://localhost:8002/sessions/default/clear | jq
```

✅ Expected: `{cleared: true, ...}`. Profile directory removed; next invocation requires re-login.
**Tests:** session reset.

---

## What overall passing means

If 60+ of these 70 examples pass, the system is doing what it claims:

- **Documented APIs** (any auth flavor) → Toolsmith finds, generates, probes, mounts (Sections B, C, D, E)
- **Code-revise loop** catches flaky generation (Section F)
- **Browser-driven tools** for sites with no API (Section G)
- **Honest failure** when nothing fits (Section H)
- **Composition** across tool sources in one chat (Section I)
- **Each service is independently usable** (Section J)

## Honest gap list — what these benchmarks deliberately don't test

1. **OAuth2 redirect flow** — phase 3.7 ships bring-your-own-token. Real redirect UX is deferred.
2. **Browser auto-discovery** — BrowserScriptCoder (LLM generates new browser DSL scripts on the fly) is not in v1; only curated templates.
3. **`user_confirm` UI flow** — the webhook fires, but the backend doesn't yet surface a UI prompt. Default behavior is deny. Set `BROWSER_AUTO_CONFIRM=1` on the runner for benchmarks.
4. **Health checks / auto-quarantine** (phase 5) — there's no daily probe; tools rot silently.
5. **Cross-domain mining** (phase 6) — not built; nothing analyzes patterns across artifacts.
6. **Subprocess sandboxing** — import allowlist is a tripwire, not isolation.
7. **Multi-user / cost caps** — single user dev only.
8. **Real Amazon / DoorDash ordering** — explicitly not bundled (ToS, captcha, payment confirmation realities).

These are the next phases (4.1+, 5, 6) — the architecture is ready for them; the features aren't built.
