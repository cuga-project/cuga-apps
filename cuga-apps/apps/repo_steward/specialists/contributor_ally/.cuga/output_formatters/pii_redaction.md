---
name: pii_redaction
description: Strip email addresses and access tokens from any output before it leaves the agent.
triggers:
  always: true
format_type: markdown
priority: 90
---

Before returning your response, scrub personally identifiable information and credentials from it:

- **Email addresses** → replace with `[email redacted]`.
- **GitHub personal access tokens** (strings starting with `ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_`) → replace with `[token redacted]`.
- **AWS keys** (strings matching `AKIA[0-9A-Z]{16}`) → replace with `[aws-key redacted]`.
- **Generic bearer tokens** (strings of 32+ base64 chars preceded by `Bearer `, `token `, or `key=`) → replace with `[token redacted]`.

Never print the original value alongside the redaction. If the redaction changes the meaning of the response, add a single line at the end: `Note: one or more values were redacted by the pii_redaction policy.`

Do not redact usernames, handles (e.g. `@octocat`), repository names, or commit SHAs — those are public identifiers on GitHub.
