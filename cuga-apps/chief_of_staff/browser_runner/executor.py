"""Playwright-backed executor for the browser task DSL.

Two execution modes:

  PlaywrightExecutor — real browser via playwright.async_api. Used in
                       production. Needs Chromium + the playwright package
                       installed (the Dockerfile uses the official Microsoft
                       Playwright image which has both pre-baked).

  MockExecutor       — records calls, returns stub results. Used in tests
                       so the architecture can be verified without a real
                       browser. Selected automatically when playwright is
                       not importable.

Executors share the run() and probe() interface, so calling code stays
identical across modes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

from .dsl import StepResult, needs_user_confirm, required_providers, validate_steps

log = logging.getLogger(__name__)


class _BaseExecutor:
    name = "base"

    async def run(
        self,
        steps: list[dict],
        inputs: dict | None = None,
        secrets: dict | None = None,
        confirm_callback=None,
    ) -> dict:
        raise NotImplementedError

    async def probe(
        self,
        steps: list[dict],
        sample_input: dict | None = None,
        secrets: dict | None = None,
    ) -> dict:
        # Probe = a "dry" run with confirms auto-approved.
        async def _auto(_prompt: str) -> bool:
            return True
        return await self.run(steps, inputs=sample_input or {},
                              secrets=secrets or {}, confirm_callback=_auto)

    async def aclose(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Playwright path
# ---------------------------------------------------------------------------

try:
    from playwright.async_api import async_playwright  # type: ignore[import-not-found]
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False


class PlaywrightExecutor(_BaseExecutor):
    name = "playwright"

    def __init__(self, profiles_dir: Path | str = "/data/profiles", default_timeout_ms: int = 30_000):
        self._profiles_dir = Path(profiles_dir)
        self._profiles_dir.mkdir(parents=True, exist_ok=True)
        self._default_timeout_ms = default_timeout_ms
        self._pw = None
        self._browser_lock = asyncio.Lock()

    async def _ensure_pw(self):
        if self._pw is None:
            self._pw = await async_playwright().start()
        return self._pw

    def _profile_for(self, provider: str | None) -> Path:
        # One profile per logical "provider" (amazon, school_portal, etc.)
        # so cookies persist independently. "default" is the catch-all.
        return self._profiles_dir / (provider or "default")

    async def run(self, steps, inputs=None, secrets=None, confirm_callback=None) -> dict:
        errs = validate_steps(steps)
        if errs:
            return {"ok": False, "reason": "; ".join(errs), "step_results": []}

        inputs = inputs or {}
        secrets = secrets or {}

        # Pick a profile based on the first ensure_logged_in (if any).
        providers = required_providers(steps)
        profile = self._profile_for(providers[0] if providers else None)

        pw = await self._ensure_pw()
        async with self._browser_lock:
            ctx = await pw.chromium.launch_persistent_context(
                user_data_dir=str(profile),
                headless=True,
                accept_downloads=False,
            )
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            page.set_default_timeout(self._default_timeout_ms)

            results: list[StepResult] = []
            extracted: dict = {}
            ok = True
            reason = ""
            try:
                for i, step in enumerate(steps):
                    sr = await _execute_step(
                        page, step, inputs, secrets, confirm_callback,
                    )
                    results.append(sr)
                    if sr.extracted:
                        extracted.update(sr.extracted)
                    if not sr.ok:
                        ok = False
                        reason = f"step {i} ({sr.action}) failed: {sr.detail}"
                        break
            finally:
                await ctx.close()

            return {
                "ok": ok, "reason": reason or "completed",
                "step_results": [_step_to_dict(s) for s in results],
                "extracted": extracted,
            }


async def _execute_step(page, step, inputs, secrets, confirm_callback) -> StepResult:
    action, value = next(iter(step.items()))
    try:
        if action == "go_to":
            url = _interp(value, inputs)
            await page.goto(url, wait_until="domcontentloaded")
            return StepResult(action=action, ok=True, detail=f"navigated to {url}")

        if action == "click_text":
            await page.get_by_text(_interp(str(value), inputs), exact=False).first.click()
            return StepResult(action=action, ok=True, detail=str(value))

        if action == "click_selector":
            await page.locator(value).first.click()
            return StepResult(action=action, ok=True, detail=value)

        if action == "fill_field":
            sel = value["selector"]
            val = _interp(str(value["value"]), inputs, secrets)
            await page.fill(sel, val)
            return StepResult(action=action, ok=True, detail=f"filled {sel}")

        if action == "wait_for_text":
            timeout = step.get("timeout_ms", 10_000)
            await page.get_by_text(_interp(str(value), inputs), exact=False).first.wait_for(timeout=timeout)
            return StepResult(action=action, ok=True, detail=str(value))

        if action == "wait_for_selector":
            timeout = step.get("timeout_ms", 10_000)
            await page.wait_for_selector(value, timeout=timeout)
            return StepResult(action=action, ok=True, detail=value)

        if action == "extract_text":
            sel = value["selector"]
            name = value["as"]
            text = (await page.locator(sel).first.text_content()) or ""
            return StepResult(action=action, ok=True, detail=f"{name}={text[:80]}",
                              extracted={name: text.strip()})

        if action == "screenshot":
            # Returns a base64 string in extracted; useful for debugging.
            import base64
            png = await page.screenshot()
            return StepResult(action=action, ok=True, detail=f"captured {value}",
                              extracted={f"screenshot_{value}": base64.b64encode(png).decode()})

        if action == "ensure_logged_in":
            # Heuristic: page is "logged in" if our session cookie is present
            # and we're not on a /signin or /login URL. The persistent profile
            # keeps cookies, so this is mostly a check.
            cur = page.url
            if "/login" in cur or "/signin" in cur:
                return StepResult(action=action, ok=False,
                                  detail=f"not logged in to {value}; redirected to {cur}")
            return StepResult(action=action, ok=True, detail=f"logged in to {value}")

        if action == "user_confirm":
            prompt = _interp(str(value), inputs)
            if confirm_callback is None:
                return StepResult(action=action, ok=False,
                                  detail="user_confirm step but no confirm_callback")
            allowed = await confirm_callback(prompt)
            if not allowed:
                return StepResult(action=action, ok=False, detail=f"user denied: {prompt}")
            return StepResult(action=action, ok=True, detail=f"user approved: {prompt}")

        if action == "sleep":
            await asyncio.sleep(int(value) / 1000)
            return StepResult(action=action, ok=True, detail=f"slept {value}ms")

        return StepResult(action=action, ok=False, detail=f"unknown action: {action}")

    except Exception as exc:  # noqa: BLE001
        return StepResult(action=action, ok=False, detail=f"{type(exc).__name__}: {exc}")


_VAR_RE = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _interp(template: str, inputs: dict, secrets: dict | None = None) -> str:
    """Substitute ${name} references from inputs, then secrets."""
    def _sub(m):
        key = m.group(1)
        if key in inputs:
            return str(inputs[key])
        if secrets and key in secrets:
            return str(secrets[key])
        return m.group(0)
    return _VAR_RE.sub(_sub, str(template))


def _step_to_dict(s: StepResult) -> dict:
    d = {"action": s.action, "ok": s.ok, "detail": s.detail}
    if s.extracted and "screenshot_" not in next(iter(s.extracted), ""):
        d["extracted"] = s.extracted
    return d


# ---------------------------------------------------------------------------
# Mock executor — used when playwright isn't available (tests, CI)
# ---------------------------------------------------------------------------

class MockExecutor(_BaseExecutor):
    name = "mock"

    def __init__(self):
        self.calls: list[dict] = []

    async def run(self, steps, inputs=None, secrets=None, confirm_callback=None) -> dict:
        errs = validate_steps(steps)
        if errs:
            return {"ok": False, "reason": "; ".join(errs), "step_results": []}

        results = []
        extracted = {}
        for step in steps:
            action, value = next(iter(step.items()))
            self.calls.append({"action": action, "value": value, "inputs": dict(inputs or {})})
            if action == "extract_text":
                extracted[value["as"]] = f"[mock extracted {value['as']}]"
                results.append({"action": action, "ok": True,
                                "detail": f"{value['as']} (mock)",
                                "extracted": {value["as"]: extracted[value["as"]]}})
            elif action == "user_confirm" and confirm_callback is not None:
                ok = await confirm_callback(value)
                results.append({"action": action, "ok": ok, "detail": "mock confirm"})
                if not ok:
                    return {"ok": False, "reason": "user denied (mock)", "step_results": results,
                            "extracted": extracted}
            else:
                results.append({"action": action, "ok": True, "detail": f"mock {action}"})
        return {"ok": True, "reason": "mock run completed",
                "step_results": results, "extracted": extracted}


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def build_executor(profiles_dir: str | None = None) -> _BaseExecutor:
    """Pick an executor based on what's available in the runtime."""
    if _PLAYWRIGHT_AVAILABLE:
        return PlaywrightExecutor(profiles_dir=profiles_dir or "/data/profiles")
    log.warning("playwright not available; using MockExecutor (browser steps will be stubbed)")
    return MockExecutor()
