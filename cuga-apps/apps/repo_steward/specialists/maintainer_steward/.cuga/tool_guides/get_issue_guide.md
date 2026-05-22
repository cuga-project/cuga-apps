---
name: get_issue_guide
description: Extra guidance the agent should follow every time it calls an issue-fetching tool — reminds it to inspect author association and link back to CONTRIBUTING.md on bug reports.
target_tools:
  - get_sample_issue
  - get_issue
triggers:
  always: true
priority: 50
---

When you call `get_sample_issue` or `get_issue`:

1. **Inspect `author_association`** immediately after printing the JSON.
   Values to watch for:
   - `FIRST_TIME_CONTRIBUTOR` — include an onboarding note in the Next Step.
   - `NONE` — likely external reporter; no special privileges implied.
   - `MEMBER` / `OWNER` — internal; you can skip the CONTRIBUTING.md
     grounding step, they already know the rules.

2. **For bug reports, verify the three required fields** from the project's
   CONTRIBUTING.md — reproduction steps, expected behavior, actual behavior.
   If any are missing, propose the `needs-repro` label in your triage.

3. **Never speculate** about what a missing field "probably" means. If the
   body doesn't include a version, ask for it in the Next Step rather than
   assuming.
