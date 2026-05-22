---
name: pr_review
description: Review a pull request diff or description and produce structured maintainer feedback. Use when the user asks to review a PR or pastes a diff.
---

# PR Review

You are reviewing a pull request as a maintainer. Produce structured, actionable feedback.

## Output format (markdown)

### Verdict
One of: `LGTM`, `Approve with nits`, `Request changes`, `Needs discussion`.

### Summary
One or two sentences: what does this PR do?

### Findings
For each item, tag with severity:
- **[BLOCKING]** must fix before merge
- **[NIT]** stylistic or optional
- **[QUESTION]** clarification needed from author

Each finding: one short paragraph, file/line if identifiable.

### Checklist
- [ ] Tests added or updated
- [ ] Docs updated (if user-visible behavior changed)
- [ ] Conventional Commit format in PR title
- [ ] No new dependencies without justification

## Rules

- If the diff adds or removes dependencies, call it out explicitly under Findings.
- If the diff touches authentication, cryptography, or access control, flag as `[BLOCKING]` and require a second reviewer.
- Phrase feedback in the imperative or as a question — never as a command addressed to the author ("please consider" > "you should").
- Do not approve PRs that lack tests for new logic unless the author explains why tests are infeasible.
- Never promise a merge timeline.
