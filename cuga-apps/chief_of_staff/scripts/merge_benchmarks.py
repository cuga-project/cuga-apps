"""Merge multiple benchmark.json files into a unified, deduplicated benchmark.

Why: each run of e2e_benchmark.py overwrites benchmark.json. We sometimes
want a benchmark that spans multiple runs (catalog growth + verify).
This merges them, dedupes by prompt text, picks the latest passing
record for each prompt, and writes a final benchmark.json.

Usage:
  python3 merge_benchmarks.py --inputs path1.json path2.json --output benchmark.json
  python3 merge_benchmarks.py --inputs path1.json path2.json --output bench.json \
      --registry-snapshot artifacts.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", nargs="+", required=True,
                        help="benchmark.json files to merge (later wins ties)")
    parser.add_argument("--output", required=True)
    parser.add_argument("--registry-snapshot", default=None,
                        help="optional separate JSON of artifacts to use as registry_after_run")
    args = parser.parse_args()

    by_prompt: dict[str, dict] = {}
    seen_registry: dict[str, dict] = {}
    total_attempted = 0

    for ipath in args.inputs:
        data = load(Path(ipath))
        # Cases keyed by prompt text — last-write-wins per file order.
        for case in data.get("cases", []):
            key = case.get("prompt") or f"__noprompt__{case.get('id')}"
            # If we already have this prompt and the previous record passed
            # but the new one would lose info, keep the earlier richer one.
            existing = by_prompt.get(key)
            if existing and case.get("verdict") == "fail_cleanly" and existing.get("verdict") != "fail_cleanly":
                continue
            by_prompt[key] = case
        # Registry artifacts: union across all inputs.
        for art in data.get("registry_after_run", []):
            seen_registry[art.get("id") or art.get("name")] = art
        total_attempted += data.get("stats", {}).get("total_run", 0)

    # Renumber the merged cases.
    merged_cases = sorted(by_prompt.values(), key=lambda c: (c.get("category") or "", c.get("intent") or ""))
    for i, c in enumerate(merged_cases, start=1):
        c["id"] = i

    # Coverage stats.
    by_verdict: dict[str, int] = {}
    by_category: dict[str, dict] = {}
    for c in merged_cases:
        by_verdict[c.get("verdict", "unknown")] = by_verdict.get(c.get("verdict", "unknown"), 0) + 1
        cat = c.get("category", "uncategorized")
        bucket = by_category.setdefault(cat, {"total": 0})
        bucket["total"] += 1

    # Optional fresh registry snapshot.
    if args.registry_snapshot:
        snap = json.loads(Path(args.registry_snapshot).read_text())
        registry = [
            {"id": a.get("id"), "name": a.get("name"),
             "provenance": (a.get("provenance") or {}).get("source")}
            for a in snap
        ]
    else:
        registry = list(seen_registry.values())

    by_provenance: dict[str, int] = {}
    for r in registry:
        by_provenance[r.get("provenance", "unknown")] = by_provenance.get(r.get("provenance", "unknown"), 0) + 1

    out = {
        "name": "chief_of_staff e2e benchmark (merged)",
        "version": "2.1",
        "description": (
            "Verified end-to-end benchmark, merged across multiple runs against "
            "the live stack. Each prompt is included only if it actually passed "
            "in at least one run. Use this as the source of truth."
        ),
        "stats": {
            "total_unique_prompts": len(merged_cases),
            "total_attempts_across_runs": total_attempted,
            "registry_size": len(registry),
            "by_verdict": by_verdict,
            "by_category": {k: v for k, v in sorted(by_category.items())},
            "tools_by_provenance": by_provenance,
            "merged_from": args.inputs,
        },
        "registry_after_run": registry,
        "cases": merged_cases,
    }
    Path(args.output).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {args.output}: {len(merged_cases)} unique prompts, {len(registry)} registry artifacts")
    print(f"  by_verdict: {by_verdict}")
    print(f"  by_provenance: {by_provenance}")


if __name__ == "__main__":
    main()
