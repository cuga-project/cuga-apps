"""
_carbon.py — shared IBM Carbon Design System foundation for all cuga-apps UIs.

This is the single source of truth for the "carbonized" look across every app:
IBM Plex typography, the Carbon color tokens, the no-radius Carbon aesthetic,
and a small library of reusable component classes (buttons, inputs, tiles,
tags, data tables, notifications, the UI-shell header, spinner, etc).

Apps live with the apps/ root on sys.path (they already `import _mcp_bridge`,
`_ports`, etc), so any app can simply:

    from _carbon import carbon_head, carbon_css

    _HTML = (
        "<!DOCTYPE html><html lang='en'><head>"
        + carbon_head("My App")        # meta + IBM Plex fonts + <title>
        + carbon_css("light")          # tokens + reset + component library
        + "<style> /* app-specific tweaks */ </style>"
        "</head><body> ... </body></html>"
    )

Use string concatenation (not f-strings/.format) around carbon_css() — the CSS
contains literal { } braces.

Themes:
    "light" — Carbon White / g10.  Productivity tools, forms, content apps.
    "dark"  — Carbon Gray 100.     Dashboards, monitors, data-dense apps.

Component classes are namespaced `cds-` (e.g. .cds-btn, .cds-tile, .cds-tag)
to avoid colliding with each app's existing class names.
"""

from __future__ import annotations

# IBM Plex Sans + IBM Plex Mono from the Google Fonts CDN. Carbon ships these as
# its product typefaces; Plex Mono is used for code / numeric / mono contexts.
_FONT_LINKS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?'
    "family=IBM+Plex+Sans:wght@300;400;500;600;700&"
    "family=IBM+Plex+Mono:wght@400;500;600&"
    'display=swap" rel="stylesheet">'
)


def carbon_head(title: str = "Cuga App") -> str:
    """Return the standard <head> preamble: charset, viewport, IBM Plex fonts, title."""
    safe = (title or "Cuga App").replace("<", "&lt;").replace(">", "&gt;")
    return (
        '<meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        + _FONT_LINKS
        + f"<title>{safe}</title>"
    )


# ── Theme token sets ─────────────────────────────────────────────────────────
# Carbon color tokens. Names follow Carbon's semantic token vocabulary so the
# per-app CSS reads like Carbon. Apps should reference these vars rather than
# hardcoding hex, so light/dark swap is a one-line change.

_TOKENS_LIGHT = """
  /* Carbon White (g10) */
  --cds-background:        #ffffff;
  --cds-background-hover:  #e8e8e8;
  --cds-layer-01:          #f4f4f4;
  --cds-layer-02:          #ffffff;
  --cds-layer-03:          #f4f4f4;
  --cds-layer-hover:       #e8e8e8;
  --cds-layer-accent:      #e0e0e0;
  --cds-field-01:          #f4f4f4;
  --cds-field-02:          #ffffff;
  --cds-border-subtle:     #e0e0e0;
  --cds-border-strong:     #8d8d8d;
  --cds-border-inverse:    #161616;
  --cds-text-primary:      #161616;
  --cds-text-secondary:    #525252;
  --cds-text-placeholder:  #a8a8a8;
  --cds-text-helper:       #6f6f6f;
  --cds-text-on-color:     #ffffff;
  --cds-text-inverse:      #ffffff;
  --cds-link-primary:      #0f62fe;
  --cds-link-hover:        #0043ce;
  --cds-icon-primary:      #161616;
  --cds-icon-secondary:    #525252;
  --cds-overlay:           rgba(22,22,22,0.5);
  --cds-skeleton:          #e5e5e5;
"""

_TOKENS_DARK = """
  /* Carbon Gray 100 */
  --cds-background:        #161616;
  --cds-background-hover:  #292929;
  --cds-layer-01:          #262626;
  --cds-layer-02:          #393939;
  --cds-layer-03:          #525252;
  --cds-layer-hover:       #333333;
  --cds-layer-accent:      #393939;
  --cds-field-01:          #262626;
  --cds-field-02:          #393939;
  --cds-border-subtle:     #393939;
  --cds-border-strong:     #6f6f6f;
  --cds-border-inverse:    #ffffff;
  --cds-text-primary:      #f4f4f4;
  --cds-text-secondary:    #c6c6c6;
  --cds-text-placeholder:  #6f6f6f;
  --cds-text-helper:       #8d8d8d;
  --cds-text-on-color:     #ffffff;
  --cds-text-inverse:      #161616;
  --cds-link-primary:      #78a9ff;
  --cds-link-hover:        #a6c8ff;
  --cds-icon-primary:      #f4f4f4;
  --cds-icon-secondary:    #c6c6c6;
  --cds-overlay:           rgba(0,0,0,0.65);
  --cds-skeleton:          #333333;
"""

# Tokens shared by both themes: the IBM blue interaction ramp, support colors,
# the Carbon spacing scale, type scale, and motion easings.
_TOKENS_SHARED = """
  /* Interactive (IBM Blue) — identical across themes */
  --cds-interactive:          #0f62fe;
  --cds-button-primary:       #0f62fe;
  --cds-button-primary-hover: #0353e9;
  --cds-button-primary-active:#002d9c;
  --cds-button-secondary:        #393939;
  --cds-button-secondary-hover:  #4c4c4c;
  --cds-button-danger:        #da1e28;
  --cds-button-danger-hover:  #ba1b23;
  --cds-focus:                #0f62fe;
  --cds-focus-inset:          #ffffff;

  /* Support / status */
  --cds-support-error:    #da1e28;
  --cds-support-success:  #24a148;
  --cds-support-warning:  #f1c21b;
  --cds-support-info:     #0043ce;
  --cds-support-error-bg:   rgba(218,30,40,0.12);
  --cds-support-success-bg: rgba(36,161,72,0.12);
  --cds-support-warning-bg: rgba(241,194,27,0.16);
  --cds-support-info-bg:    rgba(0,67,206,0.12);

  /* Spacing scale (Carbon) */
  --cds-sp-01: 0.125rem;  /* 2  */
  --cds-sp-02: 0.25rem;   /* 4  */
  --cds-sp-03: 0.5rem;    /* 8  */
  --cds-sp-04: 0.75rem;   /* 12 */
  --cds-sp-05: 1rem;      /* 16 */
  --cds-sp-06: 1.5rem;    /* 24 */
  --cds-sp-07: 2rem;      /* 32 */
  --cds-sp-08: 2.5rem;    /* 40 */
  --cds-sp-09: 3rem;      /* 48 */
  --cds-sp-10: 4rem;      /* 64 */

  /* Type */
  --cds-font-sans: 'IBM Plex Sans', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  --cds-font-mono: 'IBM Plex Mono', ui-monospace, 'SFMono-Regular', Menlo, monospace;

  /* Motion (Carbon productive easing) */
  --cds-ease-productive: cubic-bezier(0.2, 0, 0.38, 0.9);
  --cds-ease-entrance:   cubic-bezier(0, 0, 0.38, 0.9);
  --cds-ease-exit:       cubic-bezier(0.2, 0, 1, 0.9);
  --cds-dur-fast: 110ms;
  --cds-dur-mod:  150ms;
  --cds-dur-slow: 240ms;
"""

# ── Reset + base typography + component library ──────────────────────────────
# Pure CSS, no interpolation. The hallmark Carbon trait: NO border-radius on
# structural elements (buttons/inputs/tiles are square); only tags & the spinner
# are rounded.
_BASE_CSS = """
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  html { -webkit-text-size-adjust: 100%; }

  body {
    background: var(--cds-background);
    color: var(--cds-text-primary);
    font-family: var(--cds-font-sans);
    font-size: 0.875rem;       /* body-01: 14px */
    line-height: 1.43;
    letter-spacing: 0.16px;
    font-weight: 400;
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
    min-height: 100vh;
  }

  ::selection { background: var(--cds-interactive); color: #fff; }

  /* Carbon type scale helpers */
  .cds-heading-01 { font-size: 0.875rem; line-height: 1.29; font-weight: 600; letter-spacing: 0.16px; }
  .cds-heading-02 { font-size: 1rem;     line-height: 1.5;  font-weight: 600; }
  .cds-heading-03 { font-size: 1.25rem;  line-height: 1.4;  font-weight: 400; }
  .cds-heading-04 { font-size: 1.75rem;  line-height: 1.29; font-weight: 400; }
  .cds-heading-05 { font-size: 2rem;     line-height: 1.25; font-weight: 400; }
  .cds-heading-06 { font-size: 2.625rem; line-height: 1.19; font-weight: 300; }
  .cds-body-01    { font-size: 0.875rem; line-height: 1.43; }
  .cds-body-02    { font-size: 1rem;     line-height: 1.5; }
  .cds-label-01   { font-size: 0.75rem;  line-height: 1.33; letter-spacing: 0.32px; color: var(--cds-text-secondary); }
  .cds-helper-01  { font-size: 0.75rem;  line-height: 1.33; letter-spacing: 0.32px; color: var(--cds-text-helper); }
  .cds-code-01    { font-family: var(--cds-font-mono); font-size: 0.75rem; line-height: 1.33; }
  .cds-mono       { font-family: var(--cds-font-mono); }

  a, .cds-link {
    color: var(--cds-link-primary);
    text-decoration: none;
  }
  a:hover, .cds-link:hover { color: var(--cds-link-hover); text-decoration: underline; }

  /* ── UI-shell header ─────────────────────────────────────────────────── */
  .cds-header {
    position: sticky; top: 0; z-index: 8000;
    display: flex; align-items: center; gap: var(--cds-sp-05);
    height: 3rem;                       /* 48px Carbon header */
    padding: 0 var(--cds-sp-05);
    background: #161616;                /* Carbon header is always dark */
    color: #f4f4f4;
    border-bottom: 1px solid #393939;
  }
  .cds-header__name {
    font-weight: 600; font-size: 0.875rem; letter-spacing: 0.1px;
    display: flex; align-items: center; gap: var(--cds-sp-03); color: #f4f4f4;
  }
  .cds-header__name b { font-weight: 600; }
  .cds-header__prefix { font-weight: 400; opacity: 0.75; }
  .cds-header__actions { margin-left: auto; display: flex; align-items: center; gap: var(--cds-sp-04); }

  /* ── Buttons ─────────────────────────────────────────────────────────── */
  .cds-btn {
    --_bg: var(--cds-button-primary);
    --_bg-hover: var(--cds-button-primary-hover);
    --_fg: var(--cds-text-on-color);
    position: relative;
    display: inline-flex; align-items: center; justify-content: space-between;
    gap: var(--cds-sp-05);
    min-height: 3rem;                   /* 48px lg field */
    padding: 0 var(--cds-sp-05) 0 var(--cds-sp-05);
    max-width: 20rem;
    border: 1px solid transparent;
    background: var(--_bg);
    color: var(--_fg);
    font-family: var(--cds-font-sans);
    font-size: 0.875rem; font-weight: 400; line-height: 1.29;
    letter-spacing: 0.16px;
    text-align: left;
    cursor: pointer;
    transition: background var(--cds-dur-mod) var(--cds-ease-productive),
                color var(--cds-dur-mod) var(--cds-ease-productive),
                border-color var(--cds-dur-mod) var(--cds-ease-productive);
  }
  .cds-btn:hover { background: var(--_bg-hover); }
  .cds-btn:active { background: var(--cds-button-primary-active); }
  .cds-btn:focus-visible,
  .cds-btn:focus {
    outline: 2px solid var(--cds-focus);
    outline-offset: -2px;
    box-shadow: inset 0 0 0 1px var(--cds-focus-inset);
  }
  .cds-btn:disabled, .cds-btn[disabled] {
    background: var(--cds-layer-accent);
    color: var(--cds-text-placeholder);
    cursor: not-allowed;
    box-shadow: none;
  }
  .cds-btn--secondary {
    --_bg: var(--cds-button-secondary);
    --_bg-hover: var(--cds-button-secondary-hover);
    --_fg: #ffffff;
  }
  .cds-btn--tertiary {
    --_fg: var(--cds-interactive);
    background: transparent;
    border-color: var(--cds-interactive);
  }
  .cds-btn--tertiary:hover { background: var(--cds-interactive); color: #fff; }
  .cds-btn--ghost {
    --_fg: var(--cds-link-primary);
    background: transparent;
  }
  .cds-btn--ghost:hover { background: var(--cds-layer-hover); color: var(--cds-link-hover); }
  .cds-btn--danger {
    --_bg: var(--cds-button-danger);
    --_bg-hover: var(--cds-button-danger-hover);
    --_fg: #ffffff;
  }
  .cds-btn--sm { min-height: 2rem; }     /* 32px */
  .cds-btn--md { min-height: 2.5rem; }   /* 40px */
  .cds-btn--full { max-width: none; width: 100%; }
  .cds-btn--icon {
    justify-content: center; gap: 0;
    width: 3rem; max-width: 3rem; padding: 0;
  }
  .cds-btn svg { flex: none; }

  /* ── Form fields ─────────────────────────────────────────────────────── */
  .cds-label {
    display: block;
    font-size: 0.75rem; line-height: 1.33; letter-spacing: 0.32px;
    color: var(--cds-text-secondary);
    margin-bottom: var(--cds-sp-03);
  }
  .cds-input, .cds-textarea, .cds-select {
    width: 100%;
    min-height: 3rem;                   /* 48px lg */
    padding: 0 var(--cds-sp-05);
    background: var(--cds-field-01);
    color: var(--cds-text-primary);
    border: none;
    border-bottom: 1px solid var(--cds-border-strong);
    font-family: var(--cds-font-sans);
    font-size: 0.875rem; letter-spacing: 0.16px;
    transition: outline var(--cds-dur-fast) var(--cds-ease-productive),
                background var(--cds-dur-fast) var(--cds-ease-productive);
  }
  .cds-textarea { padding: var(--cds-sp-04) var(--cds-sp-05); min-height: 6rem; line-height: 1.43; resize: vertical; }
  .cds-input::placeholder, .cds-textarea::placeholder { color: var(--cds-text-placeholder); }
  .cds-input:focus, .cds-textarea:focus, .cds-select:focus {
    outline: 2px solid var(--cds-focus);
    outline-offset: -2px;
  }
  .cds-input:disabled, .cds-textarea:disabled, .cds-select:disabled {
    color: var(--cds-text-placeholder);
    border-bottom-color: transparent;
    cursor: not-allowed;
  }
  .cds-select {
    appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 16 16'%3E%3Cpath d='M8 11L3 6l.7-.7L8 9.6l4.3-4.3.7.7z'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right var(--cds-sp-05) center;
    padding-right: var(--cds-sp-08);
  }

  /* ── Tile / card ─────────────────────────────────────────────────────── */
  .cds-tile {
    background: var(--cds-layer-01);
    border: 1px solid var(--cds-border-subtle);
    padding: var(--cds-sp-06);
  }
  .cds-tile--clickable { cursor: pointer; transition: background var(--cds-dur-mod) var(--cds-ease-productive); }
  .cds-tile--clickable:hover { background: var(--cds-layer-hover); }

  /* ── Tags (pill — the one rounded element in Carbon) ─────────────────── */
  .cds-tag {
    display: inline-flex; align-items: center; gap: var(--cds-sp-02);
    height: 1.5rem; padding: 0 var(--cds-sp-03);
    border-radius: 0.9375rem;
    background: var(--cds-layer-accent);
    color: var(--cds-text-primary);
    font-size: 0.75rem; line-height: 1; letter-spacing: 0.16px;
    white-space: nowrap;
  }
  .cds-tag--blue    { background: var(--cds-support-info-bg);    color: var(--cds-link-primary); }
  .cds-tag--green   { background: var(--cds-support-success-bg); color: var(--cds-support-success); }
  .cds-tag--red     { background: var(--cds-support-error-bg);   color: var(--cds-support-error); }
  .cds-tag--yellow  { background: var(--cds-support-warning-bg); color: var(--cds-text-primary); }

  /* ── Inline notification ─────────────────────────────────────────────── */
  .cds-notification {
    display: flex; gap: var(--cds-sp-05);
    padding: var(--cds-sp-04) var(--cds-sp-05);
    border-left: 3px solid var(--cds-support-info);
    background: var(--cds-support-info-bg);
    color: var(--cds-text-primary);
    font-size: 0.875rem;
  }
  .cds-notification--error   { border-left-color: var(--cds-support-error);   background: var(--cds-support-error-bg); }
  .cds-notification--success { border-left-color: var(--cds-support-success); background: var(--cds-support-success-bg); }
  .cds-notification--warning { border-left-color: var(--cds-support-warning); background: var(--cds-support-warning-bg); }

  /* ── Data table ──────────────────────────────────────────────────────── */
  .cds-table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
  .cds-table thead th {
    text-align: left; font-weight: 600;
    background: var(--cds-layer-accent);
    color: var(--cds-text-primary);
    padding: var(--cds-sp-03) var(--cds-sp-05);
    height: 3rem; white-space: nowrap;
    border-bottom: 1px solid var(--cds-border-subtle);
  }
  .cds-table tbody td {
    padding: var(--cds-sp-03) var(--cds-sp-05);
    height: 3rem;
    border-bottom: 1px solid var(--cds-border-subtle);
    color: var(--cds-text-secondary);
  }
  .cds-table tbody tr { background: var(--cds-layer-01); transition: background var(--cds-dur-fast) var(--cds-ease-productive); }
  .cds-table tbody tr:hover { background: var(--cds-layer-hover); }

  /* ── Spinner (Carbon rotating dashed ring) ───────────────────────────── */
  .cds-spinner {
    width: 2rem; height: 2rem;
    border: 2px solid var(--cds-layer-accent);
    border-top-color: var(--cds-interactive);
    border-radius: 50%;
    animation: cds-spin 690ms linear infinite;
  }
  .cds-spinner--sm { width: 1rem; height: 1rem; border-width: 1.5px; }
  @keyframes cds-spin { to { transform: rotate(360deg); } }

  /* ── Skeleton ────────────────────────────────────────────────────────── */
  .cds-skeleton {
    background: var(--cds-skeleton);
    position: relative; overflow: hidden;
  }
  .cds-skeleton::after {
    content: ""; position: absolute; inset: 0;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.12), transparent);
    animation: cds-shimmer 1.4s ease-in-out infinite;
  }
  @keyframes cds-shimmer { 0% { transform: translateX(-100%); } 100% { transform: translateX(100%); } }

  /* ── Code block ──────────────────────────────────────────────────────── */
  .cds-code {
    font-family: var(--cds-font-mono);
    font-size: 0.8125rem; line-height: 1.5;
    background: var(--cds-layer-01);
    border: 1px solid var(--cds-border-subtle);
    padding: var(--cds-sp-05);
    overflow: auto; white-space: pre;
  }

  /* ── Layout helpers ──────────────────────────────────────────────────── */
  .cds-container { max-width: 66rem; margin: 0 auto; padding: var(--cds-sp-07) var(--cds-sp-05); }
  .cds-stack > * + * { margin-top: var(--cds-sp-05); }
  .cds-row { display: flex; gap: var(--cds-sp-05); }
  .cds-grid { display: grid; gap: var(--cds-sp-05); }

  /* Scrollbar — slim Carbon style */
  *::-webkit-scrollbar { width: 8px; height: 8px; }
  *::-webkit-scrollbar-thumb { background: var(--cds-border-strong); }
  *::-webkit-scrollbar-track { background: transparent; }

  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation-duration: 0.001ms !important; transition-duration: 0.001ms !important; }
  }
"""


def carbon_css(theme: str = "light") -> str:
    """Return a <style> block: Carbon tokens for `theme` + shared tokens + component library.

    theme: "light" (Carbon White / g10) or "dark" (Carbon Gray 100).
    """
    tokens = _TOKENS_DARK if str(theme).lower() in ("dark", "g100", "g90") else _TOKENS_LIGHT
    return "<style>\n:root {\n" + tokens + _TOKENS_SHARED + "\n}\n" + _BASE_CSS + "\n</style>"


# Convenience: full <head> string in one call.
def carbon_full_head(title: str = "Cuga App", theme: str = "light") -> str:
    return carbon_head(title) + carbon_css(theme)


__all__ = ["carbon_head", "carbon_css", "carbon_full_head"]
