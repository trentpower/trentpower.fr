#!/usr/bin/env python3
"""SEO semantics validator (robots.txt + sitemap.xml).

Beyond status 200: robots.txt is parseable and references the sitemap; the
sitemap parses, lists the configured target URLs, and excludes source mirrors.
Optional pages are never failed on. Site-level (root only); category seo.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

import lib

TOOL = "seo_semantics"
CATEGORY = "seo"


def _origin(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, "", "", ""))


def run(target_url, cfg, http):
    if lib.path_of(target_url) != "/":
        return lib.result(
            target_url,
            TOOL,
            "skipped",
            raw_json={"reason": "robots/sitemap checked at site root only"},
        )

    origin = _origin(target_url)
    robots = lib.fetch(http, origin + "/robots.txt", cfg, allow_redirects=True)
    sitemap = lib.fetch(http, origin + "/sitemap.xml", cfg, allow_redirects=True)

    robots_text = robots.text if robots.status_code == 200 else ""
    robots_parseable = bool(re.search(r"(?im)^\s*user-agent\s*:", robots_text)) and bool(
        re.search(r"(?im)^\s*(allow|disallow)\s*:", robots_text)
    )
    sitemap_ref = re.search(r"(?im)^\s*sitemap\s*:\s*(\S+)", robots_text)
    references_sitemap = bool(sitemap_ref and "sitemap.xml" in sitemap_ref.group(1))

    sitemap_ok = sitemap.status_code == 200
    locs = re.findall(r"<loc>\s*([^<]+?)\s*</loc>", sitemap.text) if sitemap_ok else []
    targets_in = sum(
        1 for t in cfg.targets if t in locs or t.rstrip("/") in [loc.rstrip("/") for loc in locs]
    )
    source_leak = [loc for loc in locs if "/source/" in loc]

    measurements = [
        lib.measurement(CATEGORY, "seo_semantics.robots_parseable", value_bool=robots_parseable),
        lib.measurement(
            CATEGORY, "seo_semantics.robots_references_sitemap", value_bool=references_sitemap
        ),
        lib.measurement(CATEGORY, "seo_semantics.sitemap_reachable", value_bool=sitemap_ok),
        lib.measurement(
            CATEGORY, "seo_semantics.targets_in_sitemap.count", value_numeric=targets_in
        ),
        lib.measurement(
            CATEGORY, "seo_semantics.source_mirror_excluded", value_bool=(len(source_leak) == 0)
        ),
    ]
    observations = []
    if not robots_parseable:
        observations.append(
            lib.observation(
                metric="seo_semantics.robots_parseable",
                severity="warning",
                observation_type="seo",
                code="ROBOTS_UNPARSEABLE",
                title="robots.txt missing or unparseable",
                message=origin + "/robots.txt",
                url=origin + "/robots.txt",
                fingerprint="seo:robots-unparseable",
            )
        )
    if not references_sitemap:
        observations.append(
            lib.observation(
                metric="seo_semantics.robots_references_sitemap",
                severity="warning",
                observation_type="seo",
                code="ROBOTS_NO_SITEMAP",
                title="robots.txt does not reference sitemap.xml",
                message=origin + "/robots.txt",
                url=origin + "/robots.txt",
                fingerprint="seo:robots-no-sitemap",
            )
        )
    if targets_in < len(cfg.targets):
        missing = [
            t
            for t in cfg.targets
            if t not in locs and t.rstrip("/") not in [loc.rstrip("/") for loc in locs]
        ]
        observations.append(
            lib.observation(
                metric="seo_semantics.targets_in_sitemap.count",
                severity="error",
                observation_type="seo",
                code="TARGET_NOT_IN_SITEMAP",
                title=f"{len(missing)} target(s) absent from sitemap",
                message=", ".join(missing),
                url=origin + "/sitemap.xml",
                fingerprint="seo:targets-missing",
                evidence=[lib.evidence("list", "missing", ", ".join(missing))],
            )
        )
    if source_leak:
        observations.append(
            lib.observation(
                metric="seo_semantics.source_mirror_excluded",
                severity="warning",
                observation_type="seo",
                code="SOURCE_MIRROR_INDEXED",
                title=f"{len(source_leak)} source mirror(s) listed in sitemap",
                message="; ".join(source_leak[:5]),
                url=origin + "/sitemap.xml",
                fingerprint="seo:source-leak",
                evidence=[lib.evidence("list", "loc", "; ".join(source_leak[:10]))],
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
        source_url=origin + "/sitemap.xml",
        measurements=measurements,
        observations=observations,
        raw_json={
            "robots_parseable": robots_parseable,
            "references_sitemap": references_sitemap,
            "sitemap_reachable": sitemap_ok,
            "targets_in_sitemap": targets_in,
            "loc_count": len(locs),
            "source_leak": source_leak[:10],
        },
    )
