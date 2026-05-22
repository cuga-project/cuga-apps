---
name: no_merge_promises
description: Strip per-PR commitments — "we'll merge this next week", "expect a review by Friday", "this fix lands tomorrow". Targets reviewer/maintainer replies on individual issues and PRs.
triggers:
  always: true
format_type: markdown
priority: 80
---

Review the response and remove any language that promises:

- A specific merge date or release date ("we'll merge this next week", "expect this in 2.4.0").
- A specific review date ("someone will look at this tomorrow", "we'll get back to you by Friday").
- A guaranteed fix ETA ("this will be fixed by end of month").

Replace such statements with neutral phrasing:

- "We'll merge this next week" → "This is tracked; merge timing depends on review capacity."
- "Someone will look at it soon" → "A maintainer will review when one is available."
- "Fixed by end of month" → "On the backlog; no ETA yet."

If the entire response was a promise and nothing remains after redaction, replace with: `Acknowledged. This is tracked; no timeline committed at this stage.`
