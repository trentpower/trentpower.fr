#!/usr/bin/env python3
"""Link validator: counts internal/external links, checks internal links for
breakage and redirects, flags mixed content. Scope is the single target page;
no site-wide crawl.
"""

from __future__ import annotations

from urllib.parse import urljoin, urlsplit

import lib
from bs4 import BeautifulSoup

TOOL = "links"
CATEGORY = "links"


def _host(url):
    return urlsplit(url).netloc.lower()


def _check(http, url, cfg):
    """Return (status_code, redirected_bool) for an internal link, or (None, False)."""
    try:
        r = lib.fetch(http, url, cfg, method="HEAD", allow_redirects=False)
        if r.status_code in (403, 405, 501):  # some hosts dislike HEAD
            r = lib.fetch(http, url, cfg, method="GET", allow_redirects=False)
        return r.status_code, r.is_redirect or (300 <= r.status_code < 400)
    except Exception:
        return None, False


def run(target_url, cfg, http):
    resp = lib.fetch(http, target_url, cfg, allow_redirects=True)
    base = resp.url
    base_host = _host(base)
    page_is_https = urlsplit(base).scheme == "https"
    soup = BeautifulSoup(resp.text, "lxml")
    path = lib.path_of(target_url)

    internal, external = set(), set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(base, href)
        if not absolute.startswith(("http://", "https://")):
            continue
        if _host(absolute) == base_host:
            internal.add(absolute.split("#")[0])
        else:
            external.add(absolute.split("#")[0])

    # mixed content: any http:// resource referenced from an https page
    mixed = []
    if page_is_https:
        for tag, attr in [
            ("script", "src"),
            ("link", "href"),
            ("img", "src"),
            ("source", "src"),
            ("iframe", "src"),
        ]:
            for el in soup.find_all(tag):
                v = el.get(attr)
                if v and urljoin(base, v).startswith("http://"):
                    mixed.append(urljoin(base, v))

    broken, redirects = [], []
    for url in sorted(internal):
        code, redirected = _check(http, url, cfg)
        if code is None or code >= 400:
            broken.append((url, code))
        elif redirected:
            redirects.append((url, code))

    measurements = [
        lib.measurement(CATEGORY, "links.internal.count", value_numeric=len(internal)),
        lib.measurement(CATEGORY, "links.external.count", value_numeric=len(external)),
        lib.measurement(CATEGORY, "links.internal_broken.count", value_numeric=len(broken)),
        lib.measurement(CATEGORY, "links.redirects.count", value_numeric=len(redirects)),
        lib.measurement(CATEGORY, "links.mixed_content.count", value_numeric=len(mixed)),
    ]

    observations = []
    for url, code in broken:
        observations.append(
            lib.observation(
                metric="links.internal_broken.count",
                severity="error",
                observation_type="broken_link",
                code=f"BROKEN_{code or 'ERR'}",
                title=f"broken internal link ({code or 'no response'})",
                message=url,
                url=target_url,
                fingerprint=f"links:broken-internal:{urlsplit(url).path}:{path}",
                evidence=[lib.evidence("url", "Link", url, source_url=target_url)],
            )
        )
    for url in mixed:
        observations.append(
            lib.observation(
                metric="links.mixed_content.count",
                severity="warning",
                observation_type="mixed_content",
                code="MIXED_CONTENT",
                title="insecure (http) resource on https page",
                message=url,
                url=target_url,
                fingerprint=f"links:mixed-content:{url}:{path}",
            )
        )

    raw = {
        "internal": len(internal),
        "external": len(external),
        "broken": broken,
        "redirects": redirects,
        "mixed_content": mixed,
    }
    status = "error" if broken else ("warning" if mixed else "ok")
    return lib.result(
        target_url, TOOL, status, measurements=measurements, observations=observations, raw_json=raw
    )
