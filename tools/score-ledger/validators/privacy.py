#!/usr/bin/env python3
"""Privacy validator: cookies, external/third-party resources, tracker heuristics."""

from __future__ import annotations

from urllib.parse import urljoin, urlsplit

import lib
from bs4 import BeautifulSoup

TOOL = "privacy"
CATEGORY = "privacy"

# Lightweight host substrings that signal analytics / tracking.
ANALYTICS_HINTS = [
    "google-analytics",
    "googletagmanager",
    "gtag",
    "analytics.",
    "plausible",
    "matomo",
    "piwik",
    "segment.",
    "mixpanel",
    "hotjar",
    "fullstory",
    "clarity.ms",
    "statcounter",
]
TRACKING_HINTS = [
    "doubleclick",
    "facebook.",
    "fbcdn",
    "connect.facebook",
    "adservice",
    "adsystem",
    "scorecardresearch",
    "criteo",
    "taboola",
    "outbrain",
    "bing.com/bat",
    "linkedin.com/px",
]


def _host(url):
    return urlsplit(url).netloc.lower()


def _is_external(url, base_host):
    h = _host(url)
    return bool(h) and h != base_host and not h.endswith("." + base_host)


def run(target_url, cfg, http):
    resp = lib.fetch(http, target_url, cfg, allow_redirects=True)
    base_host = _host(resp.url) or _host(target_url)
    soup = BeautifulSoup(resp.text, "lxml")
    path = lib.path_of(target_url)

    set_cookie = (
        resp.raw.headers.get_all("Set-Cookie") if hasattr(resp.raw.headers, "get_all") else []
    )
    set_cookie_count = len(set_cookie or [])
    cookie_count = len(resp.cookies)

    def externals(tag, attr):
        found = []
        for el in soup.find_all(tag):
            src = el.get(attr)
            if not src:
                continue
            absolute = urljoin(resp.url, src)
            if absolute.startswith(("http://", "https://")) and _is_external(absolute, base_host):
                found.append(absolute)
        return found

    ext_scripts = externals("script", "src")
    ext_styles = [
        urljoin(resp.url, link.get("href"))
        for link in soup.find_all("link", rel="stylesheet")
        if link.get("href") and _is_external(urljoin(resp.url, link.get("href")), base_host)
    ]
    ext_images = externals("img", "src")
    third_party = sorted(set(ext_scripts) | set(ext_styles) | set(ext_images))

    blob = " ".join(third_party).lower()
    analytics = any(h in blob for h in ANALYTICS_HINTS)
    tracking = any(h in blob for h in TRACKING_HINTS)

    measurements = [
        lib.measurement(CATEGORY, "privacy.cookies.count", value_numeric=cookie_count),
        lib.measurement(
            CATEGORY, "privacy.set_cookie_headers.count", value_numeric=set_cookie_count
        ),
        lib.measurement(
            CATEGORY, "privacy.third_party_resources.count", value_numeric=len(third_party)
        ),
        lib.measurement(CATEGORY, "privacy.external_scripts.count", value_numeric=len(ext_scripts)),
        lib.measurement(
            CATEGORY, "privacy.external_stylesheets.count", value_numeric=len(ext_styles)
        ),
        lib.measurement(CATEGORY, "privacy.external_images.count", value_numeric=len(ext_images)),
        lib.measurement(CATEGORY, "privacy.analytics_detected", value_bool=analytics),
        lib.measurement(CATEGORY, "privacy.tracking_detected", value_bool=tracking),
    ]

    observations = []
    for url in third_party:
        observations.append(
            lib.observation(
                metric="privacy.third_party_resources.count",
                severity="warning",
                observation_type="external_resource",
                code="THIRD_PARTY",
                title="third-party resource",
                message=url,
                url=target_url,
                fingerprint=f"privacy:external-resource:{url}:{path}",
                evidence=[lib.evidence("url", "Resource", url, source_url=target_url)],
            )
        )
    if set_cookie_count:
        observations.append(
            lib.observation(
                metric="privacy.set_cookie_headers.count",
                severity="warning",
                observation_type="cookie",
                code="SET_COOKIE",
                title=f"{set_cookie_count} Set-Cookie header(s)",
                message="; ".join(set_cookie)[:500],
                url=target_url,
                fingerprint=f"privacy:set-cookie:{path}",
            )
        )

    raw = {
        "base_host": base_host,
        "third_party": third_party,
        "cookies": cookie_count,
        "set_cookie_headers": set_cookie_count,
        "analytics_detected": analytics,
        "tracking_detected": tracking,
    }
    status = "warning" if third_party or set_cookie_count or analytics or tracking else "ok"
    return lib.result(
        target_url, TOOL, status, measurements=measurements, observations=observations, raw_json=raw
    )
