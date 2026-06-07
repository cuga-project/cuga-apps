#!/usr/bin/env python3
"""
preview_carbon.py — render any app's carbonized UI to the browser, no backend.

The agent endpoints (/ask etc.) need API keys + MCP servers, but the *look* of
the page is fully static HTML/CSS — so to eyeball the Carbon restyle you don't
need any of that. This pulls each app's HTML string (or static file) and opens
it directly.

Usage:
    python preview_carbon.py city_beat        # open one app in your browser
    python preview_carbon.py --all            # render all + open an index gallery
    python preview_carbon.py city_beat --no-open   # just write the file, print path
"""
from __future__ import annotations

import argparse
import ast
import importlib
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = Path("/tmp/carbon_preview")
OUT.mkdir(exist_ok=True)

# Apps whose HTML is not in ui.py / static (entry file differs)
ENTRY_OVERRIDE = {"video_qa": "run.py"}


def _from_module(app: str) -> str | None:
    """Import <app>/ui.py and read _HTML (safe: ui modules are light)."""
    ui_py = HERE / app / "ui.py"
    if not ui_py.exists():
        return None
    sys.path.insert(0, str(HERE / app))
    try:
        mod = importlib.import_module("ui")
        importlib.reload(mod)
        return getattr(mod, "_HTML", None)
    except Exception as exc:  # noqa: BLE001
        print(f"  (ui.py import failed: {exc}) — falling back to source scan")
        return None
    finally:
        sys.path.pop(0)
        sys.modules.pop("ui", None)


def _from_static(app: str) -> str | None:
    idx = HERE / app / "static" / "index.html"
    return idx.read_text() if idx.exists() else None


def _from_source(app: str) -> str | None:
    """Extract the longest module-level string literal that looks like an HTML doc,
    WITHOUT executing the module (handles inline _WEB_HTML/_HTML in main.py/run.py)."""
    entry = ENTRY_OVERRIDE.get(app, "main.py")
    src = HERE / app / entry
    if not src.exists():
        return None
    tree = ast.parse(src.read_text())
    best = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            val = node.value.value
            if ("<!doctype" in val.lower() or "<html" in val.lower()) \
                    and (best is None or len(val) > len(best)):
                best = val
    return best


def render(app: str) -> Path | None:
    html = _from_module(app) or _from_static(app) or _from_source(app)
    if not html:
        print(f"  ✗ {app}: could not locate HTML")
        return None
    dest = OUT / f"{app}.html"
    dest.write_text(html)
    print(f"  ✓ {app}: {len(html):>7} chars -> {dest}")
    return dest


def all_apps() -> list[str]:
    skip = {"__pycache__"}
    return sorted(
        d.name for d in HERE.iterdir()
        if d.is_dir() and not d.name.startswith((".", "_")) and d.name not in skip
        and ((d / "ui.py").exists() or (d / "main.py").exists()
             or (d / "run.py").exists() or (d / "static" / "index.html").exists())
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("app", nargs="?", help="app name, or omit with --all")
    ap.add_argument("--all", action="store_true", help="render every app + index gallery")
    ap.add_argument("--no-open", action="store_true", help="write files only, don't open browser")
    args = ap.parse_args()

    if args.all:
        rendered = [(a, render(a)) for a in all_apps()]
        links = "".join(
            f'<li><a href="{p.name}" target="_blank">{a}</a></li>'
            for a, p in rendered if p
        )
        index = OUT / "index.html"
        index.write_text(
            "<!DOCTYPE html><meta charset='utf-8'>"
            "<title>Carbon previews</title>"
            "<style>body{font-family:'IBM Plex Sans',system-ui,sans-serif;background:#f4f4f4;"
            "color:#161616;padding:32px;max-width:640px;margin:auto}"
            "h1{font-weight:600}a{color:#0f62fe;text-decoration:none;line-height:2.2}"
            "a:hover{text-decoration:underline}li{list-style:none}"
            "ul{border:1px solid #e0e0e0;background:#fff;padding:20px 24px}</style>"
            f"<h1>Carbonized app previews</h1><ul>{links}</ul>"
        )
        print(f"\nGallery: {index}")
        if not args.no_open:
            subprocess.run(["open", str(index)], check=False)
        return

    if not args.app:
        ap.error("give an app name, or use --all")
    dest = render(args.app)
    if dest and not args.no_open:
        subprocess.run(["open", str(dest)], check=False)


if __name__ == "__main__":
    main()
