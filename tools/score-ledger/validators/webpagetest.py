#!/usr/bin/env python3
"""WebPageTest validator.

Runs a WebPageTest test via the official API and records first-view AND
repeat-view timings (load, TTFB, Speed Index, Start Render, fully loaded, bytes,
requests). Works against the public webpagetest.org (requires a free API key) or
a self-hosted instance (configure the base URL; private instances may run
keyless). Provide a key via:
  - config: integration_settings.webpagetest_api_key
  - env:    WPT_API_KEY
Config:
  integration_settings.webpagetest_base_url    default https://www.webpagetest.org
  integration_settings.webpagetest_require_key  default true for the public host
Without a key (when required) the check is recorded unavailable with guidance.
A real test can take a few minutes; the validator polls until ready or times out.
Site-level.
"""

from __future__ import annotations

import os
import time

import lib

TOOL = "webpagetest"
CATEGORY = "performance"
PUBLIC_HOST = "https://www.webpagetest.org"

# WPT median.firstView/repeatView field -> our metric leaf
VIEW_FIELDS = [
    ("load_ms", "loadTime"),
    ("ttfb_ms", "TTFB"),
    ("speed_index_ms", "SpeedIndex"),
    ("start_render_ms", "render"),
    ("fully_loaded_ms", "fullyLoaded"),
    ("bytes_in", "bytesIn"),
    ("requests", "requests"),
]


def _settings(cfg):
    return cfg.raw.get("integration_settings") or {}


def _base_url(cfg):
    return (_settings(cfg).get("webpagetest_base_url") or PUBLIC_HOST).rstrip("/")


def _key(cfg):
    return _settings(cfg).get("webpagetest_api_key") or os.environ.get("WPT_API_KEY")


def _require_key(cfg, base):
    s = _settings(cfg)
    if "webpagetest_require_key" in s:
        return bool(s["webpagetest_require_key"])
    return base == PUBLIC_HOST  # public host needs a key; private default keyless


def _coerce_int(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def _view_measurements(view_data, view_name):
    out = []
    for leaf, src_field in VIEW_FIELDS:
        val = _coerce_int(view_data.get(src_field))
        if val is not None:
            out.append(
                lib.measurement(
                    CATEGORY, f"performance.webpagetest.{view_name}.{leaf}", value_numeric=val
                )
            )
    return out


def run(site_url, cfg, http):
    base = _base_url(cfg)
    src = f"{base}/?url={site_url}"
    key = _key(cfg)
    if _require_key(cfg, base) and not key:
        msg = (
            "WebPageTest requires a free API key for this host. Set it in "
            "integration_settings.webpagetest_api_key or env WPT_API_KEY, or "
            "point integration_settings.webpagetest_base_url at a keyless "
            "self-hosted instance."
        )
        return lib.result(
            site_url,
            TOOL,
            "unavailable",
            source_url=src,
            observations=[
                lib.observation(
                    metric="performance.webpagetest.first_view.load_ms",
                    severity="info",
                    observation_type="config",
                    code="WPT_NO_KEY",
                    title="WebPageTest needs an API key",
                    message=msg,
                    url=src,
                    fingerprint="webpagetest:no-key",
                )
            ],
            raw_json={"hint": msg, "base_url": base},
        )

    settings = _settings(cfg)
    max_wait = float(settings.get("webpagetest_max_wait_seconds", 240))
    poll = float(settings.get("webpagetest_poll_seconds", 15))
    timeout = float(cfg.network.get("timeout_seconds", 30))

    params = {"url": site_url, "f": "json"}
    if key:
        params["k"] = key
    start = http.get(f"{base}/runtest.php", params=params, timeout=timeout)
    if start.status_code != 200:
        return lib.result(
            site_url,
            TOOL,
            "unavailable",
            source_url=src,
            raw_json={"http_status": start.status_code, "base_url": base},
        )
    sd = start.json()
    if sd.get("statusCode") != 200:
        return lib.result(
            site_url,
            TOOL,
            "unavailable",
            source_url=src,
            raw_json={"statusCode": sd.get("statusCode"), "statusText": sd.get("statusText")},
        )
    info = sd.get("data", {})
    json_url = info.get("jsonUrl")
    user_url = info.get("userUrl")
    if not json_url:
        return lib.result(
            site_url,
            TOOL,
            "unavailable",
            source_url=src,
            raw_json={"reason": "no jsonUrl returned"},
        )

    deadline = time.monotonic() + max_wait
    result_data = None
    while True:
        r = http.get(json_url, timeout=timeout)
        if r.status_code == 200:
            jd = r.json()
            if jd.get("statusCode") == 200:
                result_data = jd.get("data", {})
                break
            if jd.get("statusCode", 0) >= 400:
                return lib.result(
                    site_url,
                    TOOL,
                    "unavailable",
                    source_url=src,
                    raw_json={
                        "statusCode": jd.get("statusCode"),
                        "statusText": jd.get("statusText"),
                    },
                )
        if time.monotonic() > deadline:
            return lib.result(
                site_url,
                TOOL,
                "unavailable",
                source_url=user_url or src,
                raw_json={"reason": f"not complete within {max_wait}s"},
            )
        time.sleep(poll)

    median = result_data.get("median", {}) or {}
    first = median.get("firstView", {}) or {}
    repeat = median.get("repeatView", {}) or {}
    measurements = _view_measurements(first, "first_view") + _view_measurements(
        repeat, "repeat_view"
    )
    if not measurements:
        return lib.result(
            site_url,
            TOOL,
            "unavailable",
            source_url=user_url or src,
            raw_json={"reason": "no median view metrics"},
        )

    return lib.result(
        site_url,
        TOOL,
        "ok",
        source_url=user_url or src,
        measurements=measurements,
        raw_json={
            "base_url": base,
            "first_view": {s: first.get(s) for _, s in VIEW_FIELDS},
            "repeat_view": {s: repeat.get(s) for _, s in VIEW_FIELDS},
        },
    )
