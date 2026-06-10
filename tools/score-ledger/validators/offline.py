#!/usr/bin/env python3
"""Offline / service-worker runtime validator (Playwright).

Loads the page online so the service worker installs/activates, then goes
offline and reloads to confirm the page still renders from cache, and that a
NEVER_CACHE path (/integrity.json) is NOT served offline.

Flakiness discipline: if the SW does not activate within the timeout the result
is `unavailable` (inconclusive) - NOT a failure. A genuine failure
(page_renders_offline=false) is only recorded when the SW activated but the
offline reload truly failed. Per-target; category service_worker.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

import lib

from . import _browser

TOOL = "offline"
CATEGORY = "service_worker"

_SW_READY = """() => new Promise(resolve => {
  if (!('serviceWorker' in navigator)) return resolve(false);
  const t = setTimeout(() => resolve(false), 8000);
  navigator.serviceWorker.ready.then(() => { clearTimeout(t); resolve(true); })
    .catch(() => { clearTimeout(t); resolve(false); });
})"""

_INTEGRITY_BLOCKED = """async () => {
  try { const r = await fetch('/integrity.json', {cache: 'no-store'}); return !r.ok; }
  catch (e) { return true; }
}"""


def _origin(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, "", "", ""))


def run(target_url, cfg, http):
    path = lib.path_of(target_url)
    try:
        with _browser.launch_page(cfg) as (page, context):
            page.goto(target_url, wait_until="load")
            activated = bool(page.evaluate(_SW_READY))
            if not activated:
                # inconclusive: cannot test the offline guarantee this run
                return lib.result(
                    target_url,
                    TOOL,
                    "unavailable",
                    measurements=[
                        lib.measurement(
                            CATEGORY, "offline.sw_activated", value_bool=False, status="unavailable"
                        )
                    ],
                    observations=[
                        lib.observation(
                            metric="offline.sw_activated",
                            severity="info",
                            observation_type="service_worker",
                            code="SW_ACTIVATION_TIMEOUT",
                            title=f"service worker did not activate in time on {path}",
                            message="offline guarantee not tested (inconclusive, not a failure)",
                            url=target_url,
                            fingerprint=f"offline:sw-timeout:{path}",
                        )
                    ],
                    raw_json={"sw_activated": False},
                )

            context.set_offline(True)
            renders = True
            try:
                page.reload(wait_until="domcontentloaded")
                # a content anchor must still be present offline
                renders = bool(page.query_selector("body")) and page.evaluate(
                    "() => !!document.querySelector('[data-edition], title')"
                )
            except Exception as e:
                if _browser.is_timeout(e):
                    renders = False
                else:
                    raise
            integrity_blocked = bool(page.evaluate(_INTEGRITY_BLOCKED))
            context.set_offline(False)
    except lib.ToolMissing:
        raise
    except Exception as e:
        return lib.result(
            target_url,
            TOOL,
            "unavailable",
            raw_json={"error": type(e).__name__, "detail": str(e)[:300]},
        )

    measurements = [
        lib.measurement(CATEGORY, "offline.sw_activated", value_bool=True),
        lib.measurement(CATEGORY, "offline.page_renders_offline", value_bool=renders),
        lib.measurement(
            CATEGORY, "offline.never_cache_blocked_offline", value_bool=integrity_blocked
        ),
    ]
    observations = []
    if not renders:
        observations.append(
            lib.observation(
                metric="offline.page_renders_offline",
                severity="error",
                observation_type="service_worker",
                code="OFFLINE_RENDER_FAILED",
                title=f"{path} did not render offline despite active SW",
                message="service worker activated but the offline reload failed to render",
                url=target_url,
                fingerprint=f"offline:render-failed:{path}",
            )
        )
    if not integrity_blocked:
        observations.append(
            lib.observation(
                metric="offline.never_cache_blocked_offline",
                severity="warning",
                observation_type="service_worker",
                code="NEVER_CACHE_SERVED_OFFLINE",
                title="/integrity.json was served offline (should be never-cached)",
                message="a NEVER_CACHE resource resolved from cache offline",
                url=target_url,
                fingerprint=f"offline:integrity-served:{path}",
            )
        )

    status = "error" if not renders else ("warning" if not integrity_blocked else "ok")
    return lib.result(
        target_url,
        TOOL,
        status,
        measurements=measurements,
        observations=observations,
        raw_json={
            "sw_activated": True,
            "renders_offline": renders,
            "integrity_blocked": integrity_blocked,
        },
    )
