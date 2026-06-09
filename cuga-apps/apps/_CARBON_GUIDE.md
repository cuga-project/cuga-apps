# Carbonizing the cuga-apps UIs — implementation guide

Goal: every app's web UI adopts the **IBM Carbon Design System** look — IBM Plex
typography, Carbon color tokens, the square-cornered Carbon aesthetic, IBM blue
(`#0f62fe`) interactions — while keeping each app's layout, behavior, JS, and
HTTP endpoints exactly as they were.

The single source of truth is **`_carbon.py`** in the apps root (already on
`sys.path` for every app). Two reference implementations are done:
`paper_scout/ui.py` (light, full rewrite) and `city_beat/ui.py` (dark, surgical
remap). Match their quality.

---

## The foundation: `_carbon.py`

```python
from _carbon import carbon_head, carbon_css

carbon_head("App Title")   # -> <meta> charset/viewport + IBM Plex font links + <title>
carbon_css("light")        # -> <style> with Carbon White tokens + reset + component lib
carbon_css("dark")         # -> <style> with Carbon Gray 100 tokens + reset + component lib
```

Use **string concatenation** around `carbon_css()` — the CSS contains literal
`{ }` so f-strings/`.format` will break.

### Tokens (CSS custom properties, available after `carbon_css`)

Color: `--cds-background`, `--cds-layer-01/02/03`, `--cds-layer-hover`,
`--cds-layer-accent`, `--cds-field-01/02`, `--cds-border-subtle/strong`,
`--cds-text-primary/secondary/placeholder/helper/on-color/inverse`,
`--cds-link-primary/hover`, `--cds-interactive`, `--cds-button-primary(-hover/-active)`,
`--cds-button-secondary(-hover)`, `--cds-button-danger(-hover)`, `--cds-focus`,
`--cds-support-error/success/warning/info` (+ matching `*-bg`), `--cds-skeleton`,
`--cds-overlay`.

Spacing: `--cds-sp-01..10` (2,4,8,12,16,24,32,40,48,64 px).
Type: `--cds-font-sans` (IBM Plex Sans), `--cds-font-mono` (IBM Plex Mono).
Motion: `--cds-ease-productive`, `--cds-dur-fast/mod/slow`.

### Component classes (namespaced `cds-`)

`cds-header` / `cds-header__name` / `cds-header__prefix` / `cds-header__actions`,
`cds-btn` (+ `--secondary --tertiary --ghost --danger --sm --md --full --icon`),
`cds-input` / `cds-textarea` / `cds-select` / `cds-label`,
`cds-tile` (+ `--clickable`),
`cds-tag` (+ `--blue --green --red --yellow`),
`cds-notification` (+ `--error --success --warning`),
`cds-table`, `cds-spinner` (+ `--sm`), `cds-skeleton`, `cds-code`,
type helpers `cds-heading-01..06 / cds-body-01/02 / cds-label-01 / cds-helper-01 / cds-mono`,
layout `cds-container / cds-stack / cds-row / cds-grid`.

---

## The two carbonization patterns

**A. Full rewrite (preferred for small/medium UIs)** — see `paper_scout/ui.py`.
Replace the bespoke `<style>` with `carbon_head + carbon_css(theme)` plus a small
app-specific `<style>` that only does layout, using `cds-*` classes and `--cds-*`
tokens in the markup. Build `_HTML` by concatenation.

**B. Surgical remap (for large UIs with lots of bespoke components)** — see
`city_beat/ui.py`. Keep the existing markup/CSS, but:
1. Add the IBM Plex `<link>` tags in `<head>`.
2. Replace the `:root {…}` block: map the app's existing variable names onto
   Carbon token values (keep the names so the rest of the CSS keeps working).
3. Switch `body { font-family }` to `'IBM Plex Sans', system-ui, …`.
4. Append a short "Carbon polish" override block before `</style>`:
   `border-radius: 0 !important` on structural elements (buttons, inputs, cards,
   tiles, message bubbles), IBM-blue primary buttons with the Carbon focus ring
   (`outline: 2px solid var(--cds-focus); outline-offset:-2px; box-shadow: inset 0 0 0 1px #fff`),
   and `outline` focus on inputs.

---

## Hard rules (non-negotiable Carbon traits)

- **Square corners** everywhere structural. The ONLY rounded things are tags/
  pills/chips (≈15px radius) and circular avatars/status dots/spinners.
- **IBM Plex Sans** for UI text, **IBM Plex Mono** for code/numeric/mono.
- **IBM blue `#0f62fe`** is the primary interactive color (dark theme links use
  `#78a9ff`, accent `#4589ff`). No teal/purple/pink as the primary action color.
- **Carbon focus ring**: 2px solid `--cds-focus`, `outline-offset: -2px`, plus a
  1px white inset on filled buttons.
- **No drop-shadow-heavy "material" cards** — Carbon tiles use 1px subtle borders,
  not big shadows.
- Keep emoji only as small inline accents, never as the brand mark; prefer a
  text wordmark `IBM <App Name>` in the header (`cds-header__prefix` for "IBM").

## Must NOT change

- Any `id=`, `fetch()` URL, POST body shape, JS function name, or route. The
  backend contract is fixed — restyle only.
- App behavior, copy/labels (beyond cosmetic), or data flow.

## Verify

Render the page to a temp file and screenshot with headless Chrome:
```
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless \
  --disable-gpu --hide-scrollbars --window-size=1280,800 \
  --screenshot=/tmp/<app>.png /tmp/<app>.html
```
Confirm: Plex font loads, square corners, IBM blue actions, no leftover legacy
neon accent colors, layout intact.

---

## App → theme manifest

**DARK (Carbon Gray 100)** — monitoring / live-data dashboards:
- `city_beat` ✅ done
- `server_monitor`
- `stock_alert`

**LIGHT (Carbon White)** — tools / forms / content apps:
- `paper_scout` ✅ done
- `api_doc_gen`, `arch_diagram`, `bird_invocable_api_creator`,
  `bird_invocable_api_creator_cuga_native`, `box_qa`, `brief_budget`,
  `code_engine_deployer`, `code_reviewer`, `deck_forge`, `drop_summarizer`,
  `hiking_research`, `ibm_cloud_advisor`, `ibm_docs_qa`, `ibm_whats_new`,
  `movie_recommender`, `newsletter`, `recipe_composer`, `smart_todo`,
  `travel_planner`, `trip_designer`, `video_qa`, `voice_journal`,
  `web_researcher`, `webpage_summarizer`, `wiki_dive`, `youtube_research`

**MIXED** — large multi-page app, choose per page (dark for the agent-monitoring
dashboard, light for forms/content):
- `ouroboros`

Notes on UI location per app: most keep HTML in `ui.py` (imported as `_HTML`);
some keep it inline in `main.py` (`_WEB_HTML` / similar string); `deck_forge`
and `travel_planner` use `static/index.html`; `video_qa` uses `run.py`;
`ouroboros` has many HTML files under its tree.
