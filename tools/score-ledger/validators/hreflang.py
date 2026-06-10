#!/usr/bin/env python3
"""hreflang reciprocity validator.

Confirms each page self-canonicalises, declares reciprocal en-AU<->fr
alternates, an x-default to root, and that sub-editions do not leak their
canonical back to root. Reciprocity is checked from a per-run cache (<=3 fetches
total). Per-target; category seo. Exact offending hrefs are recorded as evidence.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

import lib
from bs4 import BeautifulSoup

TOOL = "hreflang"
CATEGORY = "seo"

_CACHE = {}


def _origin(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, "", "", ""))


def _norm(url):
    return (url or "").rstrip("/")


def _page_info(url, cfg, http):
    if url not in _CACHE:
        try:
            r = lib.fetch(http, url, cfg, allow_redirects=True)
            soup = BeautifulSoup(r.text, "lxml")
            can = soup.find("link", attrs={"rel": "canonical"})
            alts = {}
            for link in soup.find_all("link", attrs={"rel": "alternate", "hreflang": True}):
                if link.get("href"):
                    alts[link.get("hreflang").lower()] = link.get("href")
            _CACHE[url] = {"canonical": can.get("href") if can else None, "alts": alts}
        except Exception:
            _CACHE[url] = {"canonical": None, "alts": {}}
    return _CACHE[url]


def run(target_url, cfg, http):
    origin = _origin(target_url)
    root = origin + "/"
    path = lib.path_of(target_url)
    info = _page_info(target_url, cfg, http)
    canonical = info["canonical"]
    alts = info["alts"]

    self_canonical = _norm(canonical) == _norm(target_url)
    alt_en = alts.get("en-au")
    alt_fr = alts.get("fr")
    x_default = alts.get("x-default")
    canonical_root_leak = path != "/" and _norm(canonical) == _norm(root)

    # reciprocity: each other-language alternate page must link back to this page
    reciprocal = True
    broken_back = []
    for hl in ("en-au", "fr"):
        href = alts.get(hl)
        if not href or _norm(href) == _norm(target_url):
            continue
        other = _page_info(href, cfg, http)
        back = any(_norm(v) == _norm(target_url) for v in other["alts"].values())
        if not back:
            reciprocal = False
            broken_back.append(href)

    measurements = [
        lib.measurement(CATEGORY, "hreflang.self_canonical", value_bool=self_canonical),
        lib.measurement(CATEGORY, "hreflang.alt_en_au_present", value_bool=bool(alt_en)),
        lib.measurement(CATEGORY, "hreflang.alt_fr_present", value_bool=bool(alt_fr)),
        lib.measurement(
            CATEGORY,
            "hreflang.x_default_present",
            value_bool=(bool(x_default) and _norm(x_default) == _norm(root)),
        ),
        lib.measurement(CATEGORY, "hreflang.reciprocal", value_bool=reciprocal),
        lib.measurement(
            CATEGORY, "hreflang.canonical_not_root_leak", value_bool=(not canonical_root_leak)
        ),
        lib.measurement(CATEGORY, "hreflang.alternates.count", value_numeric=len(alts)),
    ]
    observations = []
    if canonical_root_leak:
        observations.append(
            lib.observation(
                metric="hreflang.canonical_not_root_leak",
                severity="error",
                observation_type="seo",
                code="CANONICAL_ROOT_LEAK",
                title=f"{path} canonical leaks to root",
                message=f"canonical={canonical}",
                url=target_url,
                fingerprint=f"hreflang:canonical-leak:{path}",
                evidence=[
                    lib.evidence("href", "canonical", canonical or "-", source_url=target_url)
                ],
            )
        )
    if not reciprocal:
        observations.append(
            lib.observation(
                metric="hreflang.reciprocal",
                severity="error",
                observation_type="seo",
                code="HREFLANG_NOT_RECIPROCAL",
                title=f"{path} alternates not reciprocal",
                message="pages that do not link back: " + ", ".join(broken_back),
                url=target_url,
                fingerprint=f"hreflang:not-reciprocal:{path}",
                evidence=[lib.evidence("href", "no-backlink", h) for h in broken_back],
            )
        )
    if not self_canonical:
        observations.append(
            lib.observation(
                metric="hreflang.self_canonical",
                severity="warning",
                observation_type="seo",
                code="CANONICAL_NOT_SELF",
                title=f"{path} canonical is not self",
                message=f"canonical={canonical}",
                url=target_url,
                fingerprint=f"hreflang:not-self:{path}",
                evidence=[lib.evidence("href", "canonical", canonical or "-")],
            )
        )

    status = (
        "error"
        if any(o["severity"] == "error" for o in observations)
        else ("warning" if observations else "ok")
    )
    return lib.result(
        target_url,
        TOOL,
        status,
        measurements=measurements,
        observations=observations,
        raw_json={
            "canonical": canonical,
            "alts": alts,
            "reciprocal": reciprocal,
            "broken_back": broken_back,
        },
    )
