---
name: triage_protocol
description: Mandatory procedural steps the maintainer specialist must follow when the user asks to triage an issue.
triggers:
  keywords:
    - triage
    - triage this
    - triage issue
    - triage the
    - look at issue
  case_sensitive: false
priority: 80
---

# Triage Protocol

When the user asks you to triage an issue, you must complete these steps in
order before returning the final triage. This playbook is non-negotiable —
skipping a step means producing an incomplete triage.

## Step 1 — Fetch the issue

Use `get_sample_issue` (sample repo) or `get_issue` (live repo). Store the
result in a named variable.

## Step 2 — Check author association

Read the `author_association` field on the fetched issue. Possible values:
`FIRST_TIME_CONTRIBUTOR`, `CONTRIBUTOR`, `COLLABORATOR`, `MEMBER`, `OWNER`,
`NONE`. If `FIRST_TIME_CONTRIBUTOR`, include a one-line note in the Next
Step telling the maintainer to onboard warmly (the contributor_ally
specialist owns the actual welcome comment, not you).

## Step 3 — Check repo conventions

Call `get_contributing_md` once. Use its bug-report requirements to decide
if the issue needs the `needs-repro` label.

## Step 4 — (Live repo only) Check CODEOWNERS

If the active repo is live, attempt `get_repo_file("CODEOWNERS")`. If the
file exists and the issue body names a file path that maps to a codeowner,
mention that owner in the Next Step. If CODEOWNERS is missing, skip this
step silently.

## Step 5 — Run the issue_triage skill

Load `issue_triage` and follow its output format exactly — all four sections
(`Labels`, `Priority`, `Summary`, `Next step`) must be present.

## What you must NOT do

- Skip Step 2 for sample issues. Sample issues carry a realistic
  `author_association` field precisely so the protocol can be exercised.
- Invent CODEOWNERS data when the file doesn't exist. Missing is missing.
- Produce the triage without calling `get_contributing_md` at least once in
  the session (Step 3).
