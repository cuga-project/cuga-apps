# Web Researcher

Research you can check. Every claim comes with the exact sentence from its source,
and the app checks that sentence is really on the page.

**Port:** 28798 → http://localhost:28798

## Modes

Each mode puts one Tavily strength to work, through **Tavily's hosted MCP server**
(all five of its tools). The mode's tools and read budget are enforced in code.

| Mode | Tavily tools | What it's for |
| --- | --- | --- |
| Quick answer | `tavily_search` (fast) | A short answer to a focused question |
| Deep dive | `tavily_search` (advanced) → `tavily_extract` with a `query` | An open question, answered from the exact passages of the best pages |
| Site study | `tavily_map` → `tavily_crawl` → `tavily_extract` | Everything one website says about a question; always starts by mapping the site |
| Report | `tavily_research` → `tavily_extract` | A cited report, with key claims re-quoted from the source pages |
| Watch | `tavily_search` (news, `start_date` = last run) | Scheduled topics that report only what's new |

**Auto** picks Site study when the question has a URL, Report when it asks for an
overview or report, and Deep dive otherwise.

## Source controls

Whole web · No social media or forums · Research papers · News · Custom domains, plus a
time window and a news switch. They become Tavily parameters (`include_domains`,
`exclude_domains`, `time_range`, `topic`) that the app fills in and enforces on every
call, including the URLs that extract, crawl and map may read.

## How an answer is checked: two agents

1. **Researcher agent** (a `CugaAgent`) researches with the mode's Tavily tools and ends its
   answer with a claims block: `{claim, quote, source_url}`.
2. **Plain code** checks every quote, word for word, against the pages the run read
   (`research.quote_supported`). A page not read in full is re-read with `tavily_extract`.
3. **Verifier agent** (a second `CugaAgent`, `verifier.py`, with its own policy store) gets
   each claim, the code check's result and a page-coverage hint. It judges whether each quote
   supports its claim and fixes the ones that fail, using four tools:
   `find_passages` (a better sentence on the same page), `find_second_source` (Tavily search
   + extract, within your source rules, at most 2 per answer), `check_quote`, and
   `record_verdict`: verified · revised · softened · not verified · dropped.
4. `record_verdict` is a code gate the verifier can't talk its way past. It refuses a
   verified, revised, softened or dropped verdict whose quote isn't on the page; a dropped
   verdict must quote the sentence that contradicts the claim; a softened claim may only
   remove words from the original. Claims the verifier leaves without a verdict fall back to
   a batched support check.
5. The **Evidence** tab shows each verdict, what changed (the researcher's original claim
   and quote) and why; softened, not-verified and dropped claims are listed under the answer.
   **Check again** re-reads a page with `tavily_extract` on demand.

## Governance

| Layer | What it does |
| --- | --- |
| Intent guard (CUGA) | Refuses to profile private individuals (addresses, phone numbers, personal details) |
| Playbook (CUGA) | Research method: narrow searches, read before quoting, claims block |
| Tool guide (CUGA) | Stay within the source rules; quote primary sources word for word |
| Output formatter (CUGA) | Keeps the Answer / Key findings / Sources sections and the claims block |
| Verifier playbook (CUGA, verifier's own store) | One verdict per claim; never invent or edit a quote |
| Egress guard (code) | Blocks any Tavily call carrying secrets, personal emails, private IPs or internal host names (`WR_INTERNAL_TERMS` adds your own words) |
| Source rules (code) | Fills in and enforces domains, time window and news on every call |
| Mode tools and budget (code) | Only the mode's tools; a cap on outside reads; crawl and map size caps |

The **Why** tab shows, for each answer, the CUGA policy decisions, the app guards that
fired, the sources read and the run receipt (Tavily calls by tool, claim checks, tokens,
LLM calls, time). CUGA policies live in this app's own store (`.cuga/policies.db`).

## Ratings

👍/👎 is saved with the report. Tavily's open-source MCP server has a `tavily_feedback`
tool; when the hosted server offers it, ratings are also sent to Tavily (the request
id, the URLs used and the verified quotes). Set `WR_FEEDBACK=0` to turn that off.

## API

| Route | Purpose |
| --- | --- |
| `POST /research` | Start a research job: `{question, mode, site_url, profile, include_domains, exclude_domains, time_window, news, report_model}` |
| `GET /jobs/{id}` | Live steps and, when done, the result |
| `POST /ask` | Synchronous research in Auto mode (scripts, tests) |
| `POST /verify` | Check one claim again: `{claim, quote, url}` |
| `POST /feedback` | Rate a report: `{report_id, rating: up\|down}` |
| `GET /reports` | Saved reports with claims, sources and receipts |
| `GET/POST /topics…` | Watch topics: list, add, toggle, delete, run now |
| `GET /status`, `GET /settings` | Connection, policies, modes, source profiles |

## Run

```bash
python main.py --port 28798
# open http://127.0.0.1:28798
```

Env: `LLM_PROVIDER`, `LLM_MODEL`, `AGENT_SETTING_CONFIG`, `TAVILY_API_KEY`.

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

Research with evidence, one Tavily strength per mode.

**MCP servers consumed:**
- **tavily** (hosted by Tavily) — `tavily_search` · `tavily_extract` · `tavily_map` · `tavily_crawl` · `tavily_research`

**Inline `@tool` defs:** none — every tool comes from MCP.

<!-- END: MCP usage -->
