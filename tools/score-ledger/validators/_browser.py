#!/usr/bin/env python3
"""Shared Playwright launch helper for the browser-based validators.

Lazily imports Playwright so a machine without it degrades gracefully: any
import/launch failure raises lib.ToolMissing, which the dispatch wrapper maps to
an `unavailable` (non-fatal) tool_result. One headless Chromium is launched and
closed per call, so peak memory is a single browser - never run concurrently
with Lighthouse. Validators drive the page themselves and ignore the `http`
session, the same way lighthouse.py shells out.
"""

from __future__ import annotations

from contextlib import contextmanager

import lib


def _browser_cfg(cfg):
    return (cfg.raw.get("phase3") or {}).get("browser") or {}


@contextmanager
def launch_page(cfg):
    """Yield (page, context) for a fresh headless Chromium. Launch failures ->
    ToolMissing (unavailable). The validator body's own exceptions propagate so
    each validator can distinguish inconclusive from genuine failure."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise lib.ToolMissing(f"playwright not installed: {e}") from e

    bc = _browser_cfg(cfg)
    viewport = bc.get("viewport") or {"width": 1280, "height": 800}
    locale = bc.get("locale", "en-AU")
    nav_timeout = float(bc.get("nav_timeout_seconds", 30)) * 1000
    ua = cfg.network.get("user_agent", "score-ledger")

    pw = browser = context = None
    try:  # launch + context creation -> ToolMissing on failure
        pw = sync_playwright().start()
        browser = pw.chromium.launch(
            headless=True, args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            viewport=viewport, locale=locale, reduced_motion="reduce", user_agent=ua
        )
        page = context.new_page()
        page.set_default_timeout(nav_timeout)
        page.set_default_navigation_timeout(nav_timeout)
    except Exception as e:
        for closer in (lambda: browser and browser.close(), lambda: pw and pw.stop()):
            try:
                closer()
            except Exception:
                pass
        raise lib.ToolMissing(f"playwright/chromium launch failed: {e}") from e

    try:
        yield page, context
    finally:
        for closer in (context.close, browser.close, pw.stop):
            try:
                closer()
            except Exception:
                pass


def is_timeout(exc):
    """True if exc is a Playwright timeout (inconclusive, not a real failure)."""
    return exc.__class__.__name__ in ("TimeoutError", "PlaywrightTimeoutError")
