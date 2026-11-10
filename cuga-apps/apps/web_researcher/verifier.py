"""
verifier.py — the second agent. It checks the researcher's claims before the
user sees them.

Division of labour:
  * Plain code (research.quote_supported) decides whether a quote is on a page,
    word for word. The verifier can't be talked into a match: record_verdict
    refuses a "verified", "revised" or "softened" verdict whose quote isn't on
    the page it names.
  * The verifier agent (a CugaAgent with its own policy store) judges whether
    each quote really supports its claim, and fixes the claims that fail: a
    better passage on the same page, a second source found with Tavily, a softer
    claim the evidence does support — or "not verified" / "dropped".

The tools work on the run's state (`ctx`): the pages the researcher read, the
unwrapped Tavily tools, the run's source rules and its step log.
"""
from __future__ import annotations

import re
from typing import Any, Callable

import research

STATUSES = ("verified", "revised", "softened", "not_verified", "dropped")
PROVEN = ("verified", "revised", "softened")
MAX_SECOND_SOURCES = 2

VERIFIER_SYSTEM = """\
# Claim verifier

You check a research answer's claims before anyone sees them. You did not write them.
For each numbered claim you get the claim, the quote the researcher gave, its page,
and a code check that says whether that quote is on the page word for word.

## For every claim, decide and call record_verdict exactly once
1. Quote on the page AND it supports the claim → status "verified".
   "Supports" means a careful reader would accept the claim from the quote alone: same
   subject, and the quote contains every specific fact the claim states (numbers, versions,
   dates, names, words like "only" or "all").
2. Otherwise, decide what kind of failure it is, then fix it:
   a. The page says something DIFFERENT (the claim says X does A, the page says X does B):
      record "dropped", with the sentence that contradicts it as the quote. No contradicting
      sentence on the page means it is not a contradiction: use the steps below.
   b. The page covers the topic but the quote is weak: find_passages on the same page. If a
      passage supports the claim → "revised" with that passage copied exactly as the quote.
   c. The page doesn't discuss the claim's subject at all (the brief says so under PAGE
      COVERAGE): find_second_source (at most 2 claims per answer). If a passage supports the
      claim → "revised" with it and its URL.
   d. The evidence supports the claim only without one of its details (a number, "only",
      "all", a date) → "softened": delete that detail from the claim's own words. Code
      refuses a softened claim that adds any new word.
   e. Nothing supports it → "not_verified".
3. Quotes must be copied exactly from a page. record_verdict re-checks this in code: it
   refuses a verified, revised, softened or dropped verdict whose quote isn't on the page.

Work quickly: claims that pass step 1 need no tools beyond record_verdict. At most two fix
attempts per claim. When every claim has a verdict, reply "done".
"""

VERIFIER_PLAYBOOK = """\
# Verify claims

1. Read each claim and its quote. Does the quote, alone, back up the claim?
2. Yes → record_verdict verified. No → find_passages, then find_second_source, then soften,
   then not_verified or dropped.
3. One verdict per claim. Never invent or edit a quote: copy it from a page.
"""


def _is_prose(text: str) -> bool:
    """A sentence a person would quote: mostly letters and spaces, not JSON, code or markup."""
    t = text.strip()
    if not t or t[0] in "{[<|`" or t.count('"') > 6 or any(x in t for x in ("{", "}", "\\n", "](", "```")):
        return False
    letters = sum(ch.isalpha() or ch.isspace() for ch in t)
    return letters / len(t) >= 0.85

def candidate_passages(claim: str, text: str, k: int = 3, width: int = 400) -> list[str]:
    """Up to `k` sentences (or sentence pairs) of a page that share the most words with the claim."""
    words = set(w for w in research._words(claim) if len(w) > 3)
    if not words or not text:
        return []
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text)
                 if 20 <= len(s.strip()) <= 600 and _is_prose(s)]
    scored = sorted(((len(words & set(research._words(s))), i) for i, s in enumerate(sentences)), reverse=True)
    out: list[str] = []
    for sc, i in scored:
        if sc < 2 or len(out) >= k:
            break
        s = sentences[i]
        if i + 1 < len(sentences) and len(s) < 160:          # short sentence: include the next one
            s = s + " " + sentences[i + 1]
        if s[:width] not in out:
            out.append(s[:width])
    return out


def make_tools(ctx: dict[str, Any]):
    """The verifier's tools. They read `ctx` at call time, so one verifier agent
    serves every run; the app fills ctx (run, claims, extract, search, step)
    before each verification."""
    from langchain_core.tools import tool

    class _Run(dict):
        def __getitem__(self, k):
            return ctx["run"][k]

        def setdefault(self, k, v=None):
            return ctx["run"].setdefault(k, v)

    run = _Run()

    def step(text: str) -> None:
        ctx["step"](text)

    def _claim(n: int) -> dict | None:
        claims = ctx.get("claims") or []
        try:
            n = int(n)
        except (TypeError, ValueError):
            return None
        return claims[n - 1] if 1 <= n <= len(claims) else None

    async def _page(url: str, query: str) -> str:
        """Text of a page: from this run's reads, else read now with tavily_extract."""
        text = research.find_page(url, run["pages"]) or ""
        if text or not url or not ctx.get("extract"):
            return text
        if research.egress_violations({"url": url, "query": query}):
            return ""
        try:
            res = await ctx["extract"](urls=[url], query=query[:300], format="text")
        except Exception:  # noqa: BLE001
            return ""
        run["counts"]["verifier_tavily"] = run["counts"].get("verifier_tavily", 0) + 1
        rows = (res.get("results") if isinstance(res, dict) else None) or []
        text = "\n".join((r.get("raw_content") or "") for r in rows if isinstance(r, dict))
        if text:
            run["pages"][url] = text
        return text

    @tool
    async def check_quote(n: int, quote: str, source_url: str) -> dict:
        """Code check: is `quote` on the page at `source_url`, word for word?

        Args:
            n: claim number.
            quote: the exact text to look for.
            source_url: the page it should be on.

        Returns {n, on_page: bool}. The page is re-read with tavily_extract if this run hasn't read it.
        """
        c = _claim(n)
        text = await _page(source_url, (c or {}).get("claim", quote))
        return {"n": n, "on_page": bool(text and quote and research.quote_supported(quote, text))}

    @tool
    async def find_passages(n: int, source_url: str) -> dict:
        """The passages on `source_url` that best match claim `n` — candidates for a better quote.

        Args:
            n: claim number.
            source_url: the page to search (usually the claim's own page).

        Returns {n, source_url, passages: [text, ...]}. Copy a passage exactly if you use it.
        """
        c = _claim(n)
        if c is None:
            return {"error": f"no claim {n}"}
        step(f"Verifier · find_passages · claim {n}")
        text = await _page(source_url, c["claim"])
        return {"n": n, "source_url": source_url, "passages": candidate_passages(c["claim"], text)}

    @tool
    async def find_second_source(n: int, query: str) -> dict:
        """Search for another source for claim `n` (Tavily search, then extract), within the
        user's source rules. At most 2 claims per answer may use this.

        Args:
            n: claim number.
            query: a short search query for the claim's fact.

        Returns {n, sources: [{url, passages: [text, ...]}]}. Copy a passage exactly if you use it.
        """
        c = _claim(n)
        if c is None:
            return {"error": f"no claim {n}"}
        used = run.setdefault("second_sources", [])
        if n not in used and len(used) >= MAX_SECOND_SOURCES:
            return {"n": n, "sources": [], "note": "Second-source budget used up; soften or mark not_verified."}
        if research.egress_violations({"query": query}) or not ctx.get("search"):
            return {"n": n, "sources": [], "note": "This search can't be sent."}
        kwargs = {"query": query[:300], "max_results": 5, "search_depth": "advanced", "include_raw_content": False}
        _, refused = research.apply_source_rules("tavily_search", kwargs, run["rules"])
        if refused:
            return {"n": n, "sources": [], "note": refused}
        if n not in used:
            used.append(n)
        step(f"Verifier · second source · claim {n} · \"{query[:60]}\"")
        try:
            res = await ctx["search"](**kwargs)
        except Exception as exc:  # noqa: BLE001
            return {"n": n, "sources": [], "note": f"search failed: {exc}"}
        run["counts"]["verifier_tavily"] = run["counts"].get("verifier_tavily", 0) + 1
        urls = [r["url"] for r in (res.get("results") if isinstance(res, dict) else None) or []
                if isinstance(r, dict) and r.get("url") and research.url_key(r["url"]) != research.url_key(c.get("source_url", ""))][:3]
        out = []
        if urls and ctx.get("extract"):
            try:
                ex = await ctx["extract"](urls=urls, query=c["claim"][:300], format="text")
                run["counts"]["verifier_tavily"] += 1
                for r in (ex.get("results") if isinstance(ex, dict) else None) or []:
                    if isinstance(r, dict) and r.get("url") and r.get("raw_content"):
                        run["pages"][r["url"]] = r["raw_content"]
                        if r["url"] not in run["sources"]:
                            run["sources"].append(r["url"])
                        out.append({"url": r["url"], "passages": candidate_passages(c["claim"], r["raw_content"], 2)})
            except Exception:  # noqa: BLE001
                pass
        return {"n": n, "sources": out}

    @tool
    def record_verdict(n: int, status: str, claim: str, quote: str, source_url: str, note: str) -> dict:
        """Record the final verdict for claim `n`. Call exactly once per claim.

        Args:
            n: claim number.
            status: verified | revised | softened | not_verified | dropped.
            claim: the claim as it should stand (the softened text when softening).
            quote: the exact supporting text, copied from the page ("" for not_verified/dropped).
            source_url: the page the quote is on.
            note: one short sentence: why this verdict.

        Returns {accepted: bool, reason?}. A verified/revised/softened verdict is refused if
        the quote is not on that page word for word.
        """
        c = _claim(n)
        if c is None:
            return {"accepted": False, "reason": f"no claim {n}"}
        status = (status or "").strip().lower()
        if status not in STATUSES:
            return {"accepted": False, "reason": f"status must be one of {', '.join(STATUSES)}"}
        if status in PROVEN or status == "dropped":
            text = research.find_page(source_url, run["pages"]) or ""
            if not (text and quote and research.quote_supported(quote, text)):
                step(f"Verifier · claim {n} · refused: quote not on the page")
                if status == "dropped":
                    return {"accepted": False,
                            "reason": "To drop a claim, quote the sentence on the page that contradicts it. "
                                      "If no sentence contradicts it, record not_verified (or try "
                                      "find_second_source if the page doesn't cover the subject)."}
                return {"accepted": False,
                        "reason": "That quote is not on that page word for word. Copy a passage from "
                                  "find_passages or find_second_source, or record not_verified."}
        if status == "softened":
            # Softening may only take details out of the researcher's claim, never put new
            # facts in: every content word of the new claim must come from the original.
            original = set(research._words(c["claim"]))
            added = sorted({w for w in research._words(claim) if len(w) > 3} - original)
            if added:
                step(f"Verifier · claim {n} · refused: softening added new words")
                return {"accepted": False,
                        "reason": "A softened claim may only remove details from the original claim. "
                                  f"It added: {', '.join(added[:6])}. Remove details instead, or record "
                                  "not_verified."}
        run.setdefault("verdicts", {})[int(n)] = {
            "status": status, "claim": claim or c["claim"], "quote": quote,
            "source_url": source_url or c.get("source_url", ""), "note": note[:300],
        }
        step(f"Verifier · claim {n} · {status.replace('_', ' ')}")
        return {"accepted": True}

    return [check_quote, find_passages, find_second_source, record_verdict]


def covers(claim: str, page: str) -> bool:
    """Does the page discuss the claim's subject? At least two of the claim's words must
    be on the page, not counting words the page uses everywhere (on Tavily's docs,
    "Tavily" alone says nothing about an acquisition)."""
    words = research._words(page)
    if not words:
        return False
    counts: dict[str, int] = {}
    for w in words:
        counts[w] = counts.get(w, 0) + 1
    limit = max(3, len(words) // 200)                 # more than 0.5% of the page = generic
    hits = {w for w in research._words(claim) if len(w) > 3 and 0 < counts.get(w, 0) <= limit}
    return len(hits) >= 2

def brief(claims: list[dict], pages: dict[str, str] | None = None) -> str:
    """The verifier's task: every claim with two code checks — is the quote on the page,
    and does the page discuss the claim's subject at all."""
    lines = ["Check these claims. Call record_verdict once for each.", ""]
    for n, c in enumerate(claims, 1):
        page = research.find_page(c.get("source_url", ""), pages or {}) or ""
        covered = covers(c["claim"], page)
        lines += [
            f"{n}. CLAIM: {c['claim']}",
            f"   QUOTE: {c.get('quote') or '(none)'}",
            f"   PAGE: {c.get('source_url') or '(none)'}",
            f"   CODE CHECK: quote {'IS' if c.get('on_page') else 'is NOT'} on the page word for word",
            "   PAGE COVERAGE: " + ("the page discusses this subject" if covered
                                   else "the page does NOT discuss this subject; try find_second_source"),
            "",
        ]
    return "\n".join(lines)


def apply_verdicts(claims: list[dict], verdicts: dict[int, dict]) -> tuple[list[dict], list[int]]:
    """Merge the verifier's verdicts into the claims. Returns (claims, numbers with no verdict)."""
    out, missing = [], []
    for n, c in enumerate(claims, 1):
        c = dict(c)
        v = verdicts.get(n)
        if v is None:
            missing.append(n)
            out.append(c)
            continue
        status = v["status"]
        if status in ("revised", "softened"):
            c["original_claim"], c["agent_quote"] = c["claim"], c.get("quote", "")
            c["original_url"] = c.get("source_url", "")
        c.update(status=status, verified=status in PROVEN, note=v["note"], by="verifier")
        if status in PROVEN:
            c.update(claim=v["claim"], quote=v["quote"], source_url=v["source_url"], supports=True)
        elif status == "dropped":
            c.update(contradiction=v["quote"], contradiction_url=v["source_url"])
        c["checked"] = {
            "verified": "quote on the page; the verifier agrees it supports the claim",
            "revised": "the verifier replaced the quote with a passage that supports the claim",
            "softened": "the verifier narrowed the claim to what the source says",
            "not_verified": "the verifier found no passage that supports it",
            "dropped": "the verifier found the sources contradict it",
        }[status] + (f" — {v['note']}" if v["note"] else "")
        out.append(c)
    return out, missing


def changes_note(claims: list[dict]) -> str:
    """A short markdown section for the answer, listing what the verifier changed."""
    rows = []
    for c in claims:
        s = c.get("status")
        if s == "softened":
            rows.append(f"- **Narrowed:** \"{c.get('original_claim', '')}\" → \"{c['claim']}\"")
        elif s == "not_verified":
            rows.append(f"- **Not verified:** \"{c['claim']}\"")
        elif s == "dropped":
            rows.append(f"- **Dropped:** \"{c['claim']}\" (the sources contradict it)")
    return ("\n\n**Verifier notes**\n" + "\n".join(rows)) if rows else ""
