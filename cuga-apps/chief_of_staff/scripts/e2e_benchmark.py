"""End-to-end benchmark runner against the live chief-of-staff stack.

What it does:
  1. (Optional) Reset state — delete every Toolsmith artifact so we start clean.
  2. Read seed_prompts.json (curated by category).
  3. Send each prompt to /chat sequentially.
  4. Record the response, tools_used, gap, acquisition outcome.
  5. Classify each result and print live progress.
  6. At the end, write:
       results.json    — every prompt's full record (verified or not)
       benchmark.json  — only the prompts that demonstrably worked, in the
                         shape consumed by the rest of the project.

Usage:
  python3 e2e_benchmark.py --reset            # nuke artifacts, then run
  python3 e2e_benchmark.py --skip N           # resume from prompt N
  python3 e2e_benchmark.py --limit N          # stop after N prompts
  python3 e2e_benchmark.py --filter category=openapi_explicit
  python3 e2e_benchmark.py --backend http://localhost:8765   # override
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SEED_PATH = HERE / "seed_prompts.json"
RESULTS_PATH = HERE / "results.json"
BENCH_PATH = ROOT / "benchmark.json"

DEFAULT_BACKEND = "http://localhost:8765"
DEFAULT_TIMEOUT = 240.0


def classify(record: dict) -> str:
    """Decide what actually happened on this prompt."""
    if record.get("error"):
        return "transport_error"
    response = record.get("response_head", "") or ""
    tools = record.get("tools_used") or []
    gap = record.get("gap")
    acq = record.get("acquisition") or None

    answered = bool(response.strip())

    # Acquisition occurred?
    if acq:
        if acq.get("success"):
            return "acquired_and_answered" if answered else "acquired_no_answer"
        if acq.get("already_existed"):
            return "already_existed_and_answered" if answered else "already_existed_no_answer"
        if acq.get("needs_secrets"):
            return "needs_secrets"
        return "acquisition_failed"

    if gap:
        return "gap_no_acquisition"

    if answered and tools:
        return "answered_with_tool"
    if answered and not tools:
        return "answered_from_model"
    return "no_answer"


GOOD_OUTCOMES = {
    "answered_with_tool",
    "answered_from_model",
    "acquired_and_answered",
    "already_existed_and_answered",
    "needs_secrets",  # surfacing the prompt is correct behavior
}

# Outcomes that are technically valid responses for fail_cleanly cases.
EXPECTED_FAILS = {"fail_cleanly", "edge_case"}


async def fetch_artifacts(client: httpx.AsyncClient, backend: str) -> list[dict]:
    r = await client.get(f"{backend}/toolsmith/artifacts")
    r.raise_for_status()
    return r.json()


async def reset_artifacts(client: httpx.AsyncClient, backend: str) -> int:
    arts = await fetch_artifacts(client, backend)
    n = 0
    for a in arts:
        try:
            r = await client.delete(f"{backend}/toolsmith/artifacts/{a['id']}", timeout=30)
            if r.status_code in (200, 204):
                n += 1
        except httpx.HTTPError as exc:  # noqa: BLE001
            print(f"  reset: failed to delete {a['id']}: {exc}")
    return n


async def run_one(client: httpx.AsyncClient, backend: str, item: dict, idx: int, total: int) -> dict:
    """Run a single prompt. Returns a record (always — never raises)."""
    t0 = time.time()
    record: dict[str, Any] = {
        "idx": idx,
        "category": item.get("category"),
        "intent": item.get("intent"),
        "prompt": item.get("prompt"),
    }
    try:
        r = await client.post(
            f"{backend}/chat",
            json={"message": item["prompt"]},
            timeout=DEFAULT_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPError as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["elapsed_s"] = round(time.time() - t0, 1)
        record["outcome"] = classify(record)
        return record

    response = data.get("response") or ""
    record.update({
        "response_head": response[:300],
        "response_full_len": len(response),
        "tools_used": data.get("tools_used") or [],
        "gap": data.get("gap"),
        "acquisition": _slim_acq(data.get("acquisition")),
        "elapsed_s": round(time.time() - t0, 1),
    })
    if data.get("error"):
        record["chat_error"] = data["error"][:300]

    record["outcome"] = classify(record)
    return record


def _slim_acq(acq: dict | None) -> dict | None:
    if not acq:
        return None
    return {
        "success": acq.get("success"),
        "artifact_id": acq.get("artifact_id"),
        "summary": (acq.get("summary") or "")[:240],
        "already_existed": acq.get("already_existed", False),
        "needs_secrets": _slim_needs(acq.get("needs_secrets")),
    }


def _slim_needs(ns: dict | None) -> dict | None:
    if not ns:
        return None
    return {k: ns.get(k) for k in ("tool_id", "tool_name", "missing", "required") if k in ns}


def is_pass(record: dict) -> bool:
    """A record passes if its outcome is in the 'good' set, OR if the
    category is fail_cleanly and the outcome reflects an honest decline."""
    outcome = record["outcome"]
    if outcome in GOOD_OUTCOMES:
        return True
    if record.get("category") in EXPECTED_FAILS:
        return outcome in {"acquisition_failed", "no_answer", "gap_no_acquisition"}
    return False


def emit_progress(rec: dict, idx: int, total: int) -> None:
    flag = "✓" if is_pass(rec) else "✗"
    label = rec["outcome"][:24]
    elapsed = rec.get("elapsed_s", 0)
    prompt_short = (rec.get("prompt") or "")[:62]
    print(f"  [{idx:>3}/{total}] {flag} {label:<24} {elapsed:>5.1f}s  {prompt_short}", flush=True)


def write_results(records: list[dict]) -> None:
    RESULTS_PATH.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n")


def write_benchmark(records: list[dict], pre_artifacts: list[dict], post_artifacts: list[dict]) -> int:
    """Write the verified benchmark.json — only prompts that actually passed."""
    verified = [r for r in records if is_pass(r)]
    cases = []
    for i, r in enumerate(verified, start=1):
        cases.append({
            "id": i,
            "category": r["category"],
            "intent": r["intent"],
            "prompt": r["prompt"],
            "verdict": _verdict_from_outcome(r["outcome"], r.get("category")),
            "expected_outcome": r["outcome"],
            "expected_tools_used": [t.get("name") for t in r.get("tools_used") or []],
            "expected_acquisition": r.get("acquisition"),
            "observed_response_head": r.get("response_head"),
            "observed_elapsed_s": r.get("elapsed_s"),
        })
    # Diversity stats — useful when the run was meant to grow the catalog.
    # We split by Source: catalog mounts (mcp servers), openapi-generated,
    # browser-task templates, and Coder-generated wrappers.
    by_provenance: dict[str, int] = {}
    for a in post_artifacts:
        src = (a.get("provenance") or {}).get("source", "unknown")
        by_provenance[src] = by_provenance.get(src, 0) + 1

    by_category: dict[str, dict] = {}
    for r in records:
        cat = r["category"] or "uncategorized"
        b = by_category.setdefault(cat, {"total": 0, "passed": 0})
        b["total"] += 1
        if is_pass(r):
            b["passed"] += 1

    out = {
        "name": "chief_of_staff e2e benchmark",
        "version": "2.0",
        "description": (
            "Verified end-to-end benchmark — every entry was actually run "
            "against the live stack and its outcome recorded. Use this as "
            "the source of truth; the older Markdown narrative is descriptive only."
        ),
        "stats": {
            "total_run": len(records),
            "passed": len(verified),
            "failed": len(records) - len(verified),
            "registry_size_before": len(pre_artifacts),
            "registry_size_after": len(post_artifacts),
            "tools_acquired_during_run": len(post_artifacts) - len(pre_artifacts),
            "tools_by_provenance": by_provenance,
            "by_category": by_category,
        },
        "registry_after_run": [
            {"id": a.get("id"), "name": a.get("name"), "provenance": (a.get("provenance") or {}).get("source")}
            for a in post_artifacts
        ],
        "cases": cases,
    }
    BENCH_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    return len(cases)


def _verdict_from_outcome(outcome: str, category: str | None) -> str:
    if outcome.startswith("acquired"):
        return "auto_build"
    if outcome.startswith("already_existed"):
        return "already_existed"
    if outcome == "needs_secrets":
        return "needs_creds"
    if outcome == "answered_with_tool":
        return "should_work"
    if outcome == "answered_from_model":
        return "answered_from_model"
    if category in EXPECTED_FAILS:
        return "fail_cleanly"
    return "should_work"


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default=DEFAULT_BACKEND)
    parser.add_argument("--reset", action="store_true",
                        help="delete every Toolsmith artifact before running")
    parser.add_argument("--skip", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--filter", default=None,
                        help='filter prompts, e.g. "category=openapi_explicit"')
    parser.add_argument("--seed", default=str(SEED_PATH))
    args = parser.parse_args()

    seed = json.loads(Path(args.seed).read_text())
    prompts = list(seed["prompts"])
    if args.filter:
        k, _, v = args.filter.partition("=")
        prompts = [p for p in prompts if str(p.get(k)) == v]
    prompts = prompts[args.skip:]
    if args.limit:
        prompts = prompts[: args.limit]

    print(f"backend={args.backend}  prompts={len(prompts)}")

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        if args.reset:
            print("resetting artifacts…")
            n = await reset_artifacts(client, args.backend)
            print(f"  removed {n} artifact(s)")

        pre_arts = await fetch_artifacts(client, args.backend)
        print(f"registry size at start: {len(pre_arts)}")

        records: list[dict] = []
        total = len(prompts)
        t_total = time.time()
        for i, item in enumerate(prompts, start=1):
            rec = await run_one(client, args.backend, item, i, total)
            records.append(rec)
            emit_progress(rec, i, total)
            # Persist after every prompt so partial runs are recoverable.
            write_results(records)

        post_arts = await fetch_artifacts(client, args.backend)
        print(f"registry size at end:   {len(post_arts)}  (+{len(post_arts) - len(pre_arts)})")

        n_verified = write_benchmark(records, pre_arts, post_arts)

    elapsed = time.time() - t_total
    passed = sum(1 for r in records if is_pass(r))
    print()
    print(f"DONE in {elapsed:.0f}s  passed={passed}/{len(records)}  benchmark.json cases={n_verified}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted — partial results saved to results.json")
        sys.exit(130)
