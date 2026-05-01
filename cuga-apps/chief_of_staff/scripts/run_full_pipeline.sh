#!/usr/bin/env bash
# Full pipeline orchestration:
#   1. Snapshot catalog #2 outputs
#   2. Re-enable web_search (in case still disabled)
#   3. Run verify pass (no reset, on grown registry)
#   4. Snapshot verify outputs
#   5. Merge all three runs into a unified benchmark.json
#   6. Report final stats
#
# Invoke from chief_of_staff/. Assumes catalog2 already finished.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="$ROOT/.venv/bin/python"

echo "=== Step 1: snapshot catalog2 outputs ==="
cp benchmark.json /tmp/benchmark_catalog2.json
cp scripts/results.json /tmp/results_catalog2.json
ls -la /tmp/benchmark_catalog{,2}.json /tmp/results_catalog{,2}.json

echo
echo "=== Step 2: re-enable web_search ==="
curl -sS -X POST 'http://localhost:8765/tools/web_search/toggle' \
  -H 'Content-Type: application/json' -d '{"disabled":false}' \
  | python3 -m json.tool

echo
echo "=== Step 3: snapshot registry pre-verify ==="
curl -sS http://localhost:8765/toolsmith/artifacts > /tmp/artifacts_pre_verify.json
echo "  artifacts: $(python3 -c 'import sys,json; print(len(json.load(sys.stdin)))' < /tmp/artifacts_pre_verify.json)"

echo
echo "=== Step 4: run seed_prompts verify (200 prompts, no reset) ==="
echo "  this takes ~60-90 minutes; tail -f /tmp/verify.log to watch"
PYTHONUNBUFFERED=1 "$PYTHON" -u scripts/e2e_benchmark.py \
  --seed scripts/seed_prompts.json \
  > /tmp/verify.log 2>&1
echo "  verify done"

echo
echo "=== Step 5: snapshot verify outputs ==="
cp benchmark.json /tmp/benchmark_verify.json
cp scripts/results.json /tmp/results_verify.json
curl -sS http://localhost:8765/toolsmith/artifacts > /tmp/artifacts_post_verify.json

echo
echo "=== Step 6: merge all three runs ==="
"$PYTHON" scripts/merge_benchmarks.py \
  --inputs /tmp/benchmark_catalog.json /tmp/benchmark_catalog2.json /tmp/benchmark_verify.json \
  --output benchmark.json \
  --registry-snapshot /tmp/artifacts_post_verify.json

echo
echo "=== Final benchmark.json ==="
"$PYTHON" -c "
import json
b = json.load(open('benchmark.json'))
print(f'cases: {len(b[\"cases\"])}')
print(f'registry: {b[\"stats\"][\"registry_size\"]}')
print('by_verdict:')
for k,v in sorted(b['stats']['by_verdict'].items()):
    print(f'  {k:<24} {v}')
print('tools_by_provenance:')
for k,v in sorted(b['stats']['tools_by_provenance'].items()):
    print(f'  {k:<14} {v}')"
