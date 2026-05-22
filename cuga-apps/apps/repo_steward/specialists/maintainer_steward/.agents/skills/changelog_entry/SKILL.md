---
name: changelog_entry
description: Convert a single merged PR (title + description) into one user-facing changelog line. Use ONLY when the input is exactly one PR. For multi-PR release-notes documents, use the release_notes skill instead.
---

# Changelog Entry

Turn a PR into a single user-facing changelog entry following Keep-a-Changelog conventions.

## Output format

A single markdown list item under the correct section heading. Sections:
- `### Added` — new features
- `### Changed` — changes in existing behavior
- `### Deprecated` — soon-to-be removed features
- `### Removed` — removed features
- `### Fixed` — bug fixes
- `### Security` — security fixes

Each entry:
```
- <Imperative verb phrase>. ([#123](https://github.com/<owner>/<repo>/pull/123))
```

## Rules

- Infer the section from the PR's Conventional Commit prefix:
  - `feat:` → Added
  - `fix:` → Fixed
  - `perf:`, `refactor:` → Changed (only if user-visible)
  - `chore:`, `docs:`, `test:`, `ci:` → skip, not user-facing
  - `BREAKING CHANGE:` → Changed, prefixed with `**BREAKING:** `
- Write for **users**, not maintainers. Say what the user can now do or what is fixed from their perspective, not what the commit did internally.
- One line. No sub-bullets. Past tense is fine ("Fixed crash when…").
- If the PR has no Conventional Commit prefix and it is not obvious from context, output: `SKIP — PR lacks a conventional-commit prefix. Ask the author to retitle.`
