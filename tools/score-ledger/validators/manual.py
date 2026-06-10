#!/usr/bin/env python3
"""External-integration descriptors and manual placeholders.

The four external integrations (Mozilla Observatory, SSL Labs, PageSpeed,
WebPageTest) have real validators (observatory.py, ssl_labs.py, pagespeed.py,
webpagetest.py). When an integration is disabled in config, this module supplies
a site-level `manual` placeholder so the ledger still shows the check exists and
carries a source_url to run it by hand.
"""

from __future__ import annotations

from urllib.parse import urlsplit

import lib

TOOL = "manual"

# integration key (matches config "integrations") -> descriptor
INTEGRATIONS = {
    "mozilla_observatory": {
        "label": "Mozilla Observatory",
        "category": "security",
        "url": "https://developer.mozilla.org/en-US/observatory/analyze?host={host}",
    },
    "ssl_labs": {
        "label": "SSL Labs",
        "category": "tls",
        "url": "https://www.ssllabs.com/ssltest/analyze.html?d={host}",
    },
    "pagespeed": {
        "label": "PageSpeed Insights",
        "category": "performance",
        "url": "https://pagespeed.web.dev/analysis?url={site}",
    },
    "webpagetest": {
        "label": "WebPageTest",
        "category": "performance",
        "url": "https://www.webpagetest.org/?url={site}",
    },
}


def host_and_site(cfg):
    site = cfg.targets[0] if cfg.targets else "https://trentpower.fr/"
    host = urlsplit(site).netloc or "trentpower.fr"
    return host, site


def source_url(cfg, key):
    host, site = host_and_site(cfg)
    return INTEGRATIONS[key]["url"].format(host=host, site=site)


def placeholder(cfg, key):
    """One site-level `manual` result for a disabled integration."""
    spec = INTEGRATIONS[key]
    _, site = host_and_site(cfg)
    src = source_url(cfg, key)
    metric = f"manual.{key}.status"
    measurement = lib.measurement(
        spec["category"],
        metric,
        value_text="manual",
        unit="enum",
        comparison_mode="neutral",
        status="manual",
    )
    observation = lib.observation(
        metric=metric,
        severity="info",
        observation_type="manual",
        code="MANUAL_CHECK",
        title=f"{spec['label']}: manual check",
        message=(
            f"{spec['label']} is disabled in config. Enable it under "
            f"integrations, or run it by hand at the source URL."
        ),
        url=src,
        fingerprint=f"manual:{key}",
        evidence=[lib.evidence("url", "Check at", src, source_url=src)],
    )
    return lib.result(
        site,
        key,
        "manual",
        source_url=src,
        measurements=[measurement],
        observations=[observation],
        raw_json={
            "integration": key,
            "label": spec["label"],
            "source_url": src,
            "automated": False,
        },
    )
