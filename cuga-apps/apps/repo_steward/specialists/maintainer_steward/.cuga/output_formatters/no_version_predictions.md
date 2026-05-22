---
name: no_version_predictions
description: Strip release-level predictions — "shipping in 2.0", "GA in Q3", "## 2.0 (next week)". Targets release notes, roadmap statements, and announcement text. Distinct from no_merge_promises, which targets per-PR commitments.
triggers:
  keywords:
    - will ship
    - ship in
    - will release
    - planned for
    - targeting
    - expect .* in
    - expected in
    - on track for
    - GA in
    - coming in
    - releases .* next
  case_sensitive: false
format_type: markdown
priority: 70
---

Review the response for forward-looking predictions about when a specific
version or feature will ship. Remove anything that commits to a future
release date or predicts what a future version will contain.

Examples to rewrite:
- "will ship in 2.0" → drop the phrase; move entry under `## Unreleased`.
- "planned for the 1.5 release" → "targeted for a future release (no version committed)".
- "expect this in Q3" → "no ETA".
- "on track for GA in June" → "no GA date committed".
- "2.0 is coming in two weeks" → "2.0 is in progress; no date committed".

Leave these alone:
- Version numbers in headings of notes that are already *describing a
  shipped release* (e.g., `## 1.4.2` in a changelog).
- PR numbers and commit SHAs.
- Descriptions of what a PR *did* — that's historical, not predictive.

If the whole response was a version prediction and nothing remains after
rewriting, replace with: `No shipped version or date is committed yet; the
work is tracked in the listed PRs.`

Prepend a single short line so the user sees the intervention:
`_[no_version_predictions] Removed forward-looking version/ship-date
commitments._`
