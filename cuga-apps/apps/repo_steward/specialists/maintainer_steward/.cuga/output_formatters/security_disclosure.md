---
name: security_disclosure_escalation
description: Rewrite responses that discuss a security vulnerability to route the maintainer to the private disclosure process instead of publishing a public triage.
triggers:
  keywords:
    - CVE-
    - vulnerability
    - exploit
    - security advisory
    - RCE
    - remote code execution
    - zero-day
    - 0-day
    - credentials leaked
    - token leak
    - XSS
  case_sensitive: false
format_type: markdown
priority: 100
---

This turn involves a potential security disclosure. **Do not ship the public-style triage below.** Rewrite the response so it:

1. Opens with a one-line note that the `security_disclosure_escalation` policy fired and the original draft was replaced because it described or acknowledged a vulnerability in public-channel language.
2. Tells the maintainer to:
   - Route the reporter to `SECURITY.md` and the project's private disclosure channel.
   - Not confirm, deny, or speculate about severity in public comments.
   - Avoid linking to the issue in public discussion until a fix is shipped.
3. Does NOT echo the original issue body, the reporter's exploit description, or any technical detail of the vulnerability.
4. Does NOT suggest a fix, patch approach, or reproduction steps.

Keep the final response under 120 words. Plain markdown. No headings from the original triage survive.
