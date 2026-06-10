#!/usr/bin/env python3
"""Google PageSpeed Insights validator.

Calls the official PSI API and records the Lighthouse category scores Google
measures from its own infrastructure. PSI requires a free API key for reliable
use (the keyless quota is effectively zero). Provide one via:
  - config: integration_settings.pagespeed_api_key
  - env:    PAGESPEED_API_KEY
Without a key (or on quota/429) the check is recorded unavailable with guidance.
Site-level.
"""

from __future__ import annotations

import os

import lib

TOOL = "pagespeed"
CATEGORY = "performance"
ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

CAT_METRICS = {
    "performance": "performance.pagespeed.performance.score",
    "accessibility": "performance.pagespeed.accessibility.score",
    "best-practices": "performance.pagespeed.best_practices.score",
    "seo": "performance.pagespeed.seo.score",
}


def _key(cfg):
    settings = cfg.raw.get("integration_settings") or {}
    return settings.get("pagespeed_api_key") or os.environ.get("PAGESPEED_API_KEY")


def run(site_url, cfg, http):
    src = f"https://pagespeed.web.dev/analysis?url={site_url}"
    settings = cfg.raw.get("integration_settings") or {}
    strategy = settings.get("pagespeed_strategy", "mobile")
    timeout = float(cfg.network.get("timeout_seconds", 30))
    key = _key(cfg)

    params = {"url": site_url, "strategy": strategy, "category": list(CAT_METRICS.keys())}
    if key:
        params["key"] = key

    r = http.get(ENDPOINT, params=params, timeout=timeout)
    if r.status_code == 429 or (r.status_code == 403 and not key):
        msg = (
            "PageSpeed quota exceeded / no API key. Set a free key in "
            "integration_settings.pagespeed_api_key or env PAGESPEED_API_KEY."
        )
        return lib.result(
            site_url,
            TOOL,
            "unavailable",
            source_url=src,
            observations=[
                lib.observation(
                    metric="performance.pagespeed.performance.score",
                    severity="info",
                    observation_type="config",
                    code="PSI_NO_KEY",
                    title="PageSpeed needs an API key",
                    message=msg,
                    url=src,
                    fingerprint="pagespeed:no-key",
                )
            ],
            raw_json={"http_status": r.status_code, "hint": msg},
        )
    if r.status_code != 200:
        return lib.result(
            site_url,
            TOOL,
            "unavailable",
            source_url=src,
            raw_json={"http_status": r.status_code, "body": r.text[:400]},
        )

    data = r.json()
    lr = data.get("lighthouseResult", {})
    cats = lr.get("categories", {})
    measurements = []
    for cat_id, metric in CAT_METRICS.items():
        c = cats.get(cat_id)
        if c and c.get("score") is not None:
            score = round(c["score"] * 100)
            measurements.append(
                lib.measurement(CATEGORY, metric, value_numeric=score, normalised_score=score)
            )
    if not measurements:
        return lib.result(
            site_url,
            TOOL,
            "unavailable",
            source_url=src,
            raw_json={"reason": "no categories in response"},
        )

    return lib.result(
        site_url,
        TOOL,
        "ok",
        tool_version=lr.get("lighthouseVersion"),
        source_url=src,
        measurements=measurements,
        raw_json={
            "strategy": strategy,
            "scores": {k: (cats.get(k) or {}).get("score") for k in CAT_METRICS},
        },
    )
