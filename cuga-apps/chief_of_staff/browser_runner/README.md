# Browser Runner

The phase-4 service that drives a real browser (Chromium via Playwright)
to operate sites that have no API. Lives at port **8002**.

Persistent profiles live at `/data/profiles/<provider>/` inside the
container — one folder per logical "provider" (amazon, school_portal, etc.)
so cookies and session state survive restarts.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | service status + executor mode (playwright / mock) |
| `POST` | `/execute` | run a browser task: `{steps, inputs, secrets, allow_user_confirm}` → `{ok, reason, step_results, extracted}` |
| `POST` | `/probe` | dry-run a browser task with auto-approved confirms (used by Toolsmith's probe step) |
| `GET` | `/sessions/{provider}` | profile existence + size |
| `POST` | `/sessions/{provider}/clear` | wipe a provider's profile (forces re-login next time) |

## DSL

A browser task is a list of step dicts. Each step has exactly one action key:

| Action | Form | Purpose |
|---|---|---|
| `go_to` | `{go_to: <url>}` | Navigate, wait for DOM. URL can use `${input_var}` |
| `click_text` | `{click_text: <text>}` | Click first element matching text |
| `click_selector` | `{click_selector: <css>}` | Click by CSS selector |
| `fill_field` | `{fill_field: {selector, value}}` | Type into input. value can use `${input_var}` or `${secret_key}` |
| `wait_for_text` | `{wait_for_text: <text>, timeout_ms?}` | Wait until text appears |
| `wait_for_selector` | `{wait_for_selector: <css>, timeout_ms?}` | Wait until element appears |
| `extract_text` | `{extract_text: {selector, as}}` | Extract text into `extracted[<as>]` |
| `screenshot` | `{screenshot: <name>}` | Capture page (base64 in extracted) |
| `ensure_logged_in` | `{ensure_logged_in: <provider>}` | Verify session is active; fail if redirected to /login |
| `user_confirm` | `{user_confirm: <prompt>}` | Pause for human approval — webhook to backend |
| `sleep` | `{sleep: <ms>}` | Delay |

## Configuration

| Env | Default | Notes |
|---|---|---|
| `BROWSER_PROFILES_DIR` | `/data/profiles` | Where Chromium user-data dirs live |
| `BROWSER_AUTO_CONFIRM` | unset | If `1`, auto-approve `user_confirm` steps. Use only for benchmarks. |
| `CONFIRM_WEBHOOK_URL` | unset | If set, `user_confirm` posts the prompt to the backend; default deny on no callback |

## Mock executor

If the `playwright` package isn't importable (e.g. tests in a sandbox without
Chromium), the service falls back to a `MockExecutor` that records calls and
returns stub results. Same interface — the architecture verifies cleanly
without a real browser.
