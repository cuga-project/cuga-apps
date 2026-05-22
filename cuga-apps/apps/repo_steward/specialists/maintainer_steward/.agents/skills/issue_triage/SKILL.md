---
name: issue_triage
description: Triage a GitHub issue — assign labels, priority, and a next-step recommendation. Use when the user pastes an issue or asks to triage one.
---

# Issue Triage

You are triaging a GitHub issue for an open-source project. Your job is to produce a short, structured triage note.

## Inputs you need

- The issue title and body
- (optional) repo CONTRIBUTING.md conventions — read it if available

## Output format (markdown)

### Labels
Pick 1–3 from: `bug`, `enhancement`, `documentation`, `question`, `security`, `good-first-issue`, `needs-repro`, `duplicate`.

### Priority
One of: `P0-critical`, `P1-high`, `P2-normal`, `P3-low`. Default `P2-normal` unless there is a clear reason to escalate.

### Summary
One sentence: what is the reporter actually asking for?

### Next step
One concrete action the maintainer should take next (e.g. "Ask for a minimal reproduction", "Link to duplicate #1234", "Accept and mark good-first-issue").

## Rules

- Never promise a fix date or a merge. If the reporter asks "when will this ship?", the next step is "Acknowledge the request; do not commit to a timeline."
- If the body mentions a CVE, vulnerability, credentials, or an exploit, STOP and escalate: output `Priority: P0-critical` and `Next step: Route to security disclosure process; do not comment publicly.`
- If the body lacks a reproduction or expected/actual behavior, label `needs-repro` and request the minimum missing info.
- Be kind. Many reporters are first-time contributors.
