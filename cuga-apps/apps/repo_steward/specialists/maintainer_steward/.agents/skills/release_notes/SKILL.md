---
name: release_notes
description: Compose a full Keep-a-Changelog-style release-notes document from several merged or merge-ready PRs. Use when the user asks for release notes covering more than one PR, or asks to summarize what's in a release.
---

# Release Notes

Assemble release notes spanning multiple PRs. This is *not* a single
changelog line — use the `changelog_entry` skill for that. A release-notes
document covers **N** PRs, groups them by section, and reads as a
user-facing summary of what ships.

## Inputs

The user may hand you either:
- **An explicit list of PR numbers** ("release notes for PRs 55 and 56").
- **"All open / merge-ready PRs"** — call `list_sample_prs` (or the
  appropriate live tool) to enumerate, then `get_sample_pr` per entry.

If the user named a version (`"notes for 1.5.0"`, `"release 2.0 notes"`),
include it as the heading. If not, use `## Unreleased`.

## Output format (markdown)

```
## <Version or "Unreleased">

### Added
- <imperative user-facing entry>. ([#123](…))

### Changed
- <imperative user-facing entry>. ([#124](…))

### Fixed
- <imperative user-facing entry>. ([#125](…))

### Security
- <imperative user-facing entry>. ([#126](…))
```

Section rules:
- `feat:` → **Added**
- `fix:` → **Fixed**
- `perf:` / `refactor:` (only if user-visible) → **Changed**
- `BREAKING CHANGE:` → **Changed**, prefix entry with `**BREAKING:** `
- `chore:` / `docs:` / `test:` / `ci:` → **skip**; they don't ship to users
- Security-relevant fixes → **Security**

Only include sections that have entries. Drop empty sections entirely.

## Rules

- Write entries for **users**, not maintainers. "Fixed a crash when the data
  list was empty" beats "Added null-check in Widget.render."
- One line per entry. No sub-bullets. Past tense is fine.
- Cite the PR number as a markdown link: `([#123](…))`. If you don't know
  the repo URL, just use `#123`.
- If a PR has no Conventional-Commit prefix AND it's not obvious from
  context, skip it and add one line under the heading:
  `> Skipped N PR(s) without a conventional-commit prefix.`
- Do **not** invent PRs that aren't in the input — only summarize what the
  user handed you or the tools returned.
- Do **not** predict future versions or ship dates. If no version was named,
  use `## Unreleased`.

## Style

Keep the whole document under ~500 words for a typical release. A release
with 3–10 PRs should feel *scannable*, not exhaustive.
