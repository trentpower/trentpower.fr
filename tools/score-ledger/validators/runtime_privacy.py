#!/usr/bin/env python3
"""Runtime privacy validator (Playwright).

The runtime counterpart to the static `privacy` validator: it loads the page in
a real browser and inspects what actually happens - third-party network
requests, cookies set after load, and localStorage/sessionStorage keys written
at runtime - flagging anything not on the approved allowlist. Only key NAMES and
site-owned request URLs are recorded (never cookie/storage values). Per-target;
category privacy. Browser-missing or load timeout -> unavailable (non-fatal).
"""

from __future__ import annotations

from urllib.parse import urlsplit

import lib

from . import _browser

TOOL = "runtime_privacy"
CATEGORY = "privacy"


def _host(url):
    return urlsplit(url).netloc.lower()


def _is_external(url, base):
    h = _host(url)
    return bool(h) and h != base and not h.endswith("." + base)


def _allow(cfg):
    s = (cfg.raw.get("phase3") or {}).get("runtime_privacy") or {}
    return set(s.get("storage_keys", [])), list(s.get("storage_key_prefixes", []))


def _approved(key, keys, prefixes):
    return key in keys or any(key.startswith(p) for p in prefixes)


def run(target_url, cfg, http):
    base = _host(target_url)
    keys, prefixes = _allow(cfg)
    path = lib.path_of(target_url)
    requests = []

    try:
        with _browser.launch_page(cfg) as (page, context):
            page.on(
                "request",
                lambda req: requests.append(
                    {"url": req.url, "type": req.resource_type, "method": req.method}
                ),
            )
            try:
                page.goto(target_url, wait_until="networkidle")
            except Exception as e:
                if _browser.is_timeout(e):
                    page.wait_for_timeout(1500)  # settle; proceed with what we have
                else:
                    raise
            page.wait_for_timeout(800)
            cookies = context.cookies()
            ls = page.evaluate("() => Object.keys(window.localStorage)") or []
            ss = page.evaluate("() => Object.keys(window.sessionStorage)") or []
    except lib.ToolMissing:
        raise  # -> unavailable via dispatch
    except Exception as e:
        return lib.result(
            target_url,
            TOOL,
            "unavailable",
            raw_json={"error": type(e).__name__, "detail": str(e)[:300]},
        )

    third_party = [
        r
        for r in requests
        if r["url"].startswith(("http://", "https://")) and _is_external(r["url"], base)
    ]
    ext_fonts = [r for r in third_party if r["type"] == "font"]
    beacons = [r for r in third_party if r["type"] in ("beacon", "ping")]
    unapproved = [(k, "local") for k in ls if not _approved(k, keys, prefixes)] + [
        (k, "session") for k in ss if not _approved(k, keys, prefixes)
    ]

    measurements = [
        lib.measurement(
            CATEGORY, "runtime_privacy.third_party_requests.count", value_numeric=len(third_party)
        ),
        lib.measurement(
            CATEGORY, "runtime_privacy.cookies_runtime.count", value_numeric=len(cookies)
        ),
        lib.measurement(
            CATEGORY, "runtime_privacy.unapproved_storage_keys.count", value_numeric=len(unapproved)
        ),
        lib.measurement(
            CATEGORY, "runtime_privacy.external_fonts.count", value_numeric=len(ext_fonts)
        ),
        lib.measurement(CATEGORY, "runtime_privacy.beacons.count", value_numeric=len(beacons)),
    ]
    observations = []
    for r in third_party:
        observations.append(
            lib.observation(
                metric="runtime_privacy.third_party_requests.count",
                severity="error",
                observation_type="runtime_privacy",
                code="RUNTIME_THIRD_PARTY",
                title=f"third-party request: {_host(r['url'])}",
                message=f"{r['method']} {r['type']} {r['url']}",
                url=target_url,
                fingerprint=f"runtime:third-party:{_host(r['url'])}:{path}",
                evidence=[
                    lib.evidence("url", "request", r["url"]),
                    lib.evidence("text", "host/type", f"{_host(r['url'])} / {r['type']}"),
                ],
            )
        )
    for k, store in unapproved:
        observations.append(
            lib.observation(
                metric="runtime_privacy.unapproved_storage_keys.count",
                severity="error",
                observation_type="runtime_privacy",
                code="UNAPPROVED_STORAGE_KEY",
                title=f"unapproved {store}Storage key: {k}",
                message=f"key '{k}' in {store}Storage not on the approved allowlist",
                url=target_url,
                fingerprint=f"runtime:storage-key:{k}:{path}",
                evidence=[lib.evidence("text", "key", k), lib.evidence("text", "storage", store)],
            )
        )
    if cookies:
        observations.append(
            lib.observation(
                metric="runtime_privacy.cookies_runtime.count",
                severity="warning",
                observation_type="runtime_privacy",
                code="RUNTIME_COOKIE",
                title=f"{len(cookies)} cookie(s) after load",
                message="; ".join(sorted(c.get("name", "?") for c in cookies))[:300],
                url=target_url,
                fingerprint=f"runtime:cookies:{path}",
            )
        )

    status = "error" if (third_party or unapproved) else ("warning" if cookies else "ok")
    return lib.result(
        target_url,
        TOOL,
        status,
        measurements=measurements,
        observations=observations,
        raw_json={
            "requests": len(requests),
            "third_party": len(third_party),
            "cookies": len(cookies),
            "localStorage_keys": ls,
            "sessionStorage_keys": ss,
            "unapproved": [k for k, _ in unapproved],
        },
    )
