#!/usr/bin/env python3
"""Service-worker static-correctness validator.

Static text analysis of the served /sw.js + /sw-register.js (no browser): the
cache version encodes the current edition, the never-cache list covers the
sensitive paths, and the registration scope is '/'. Uncertain parsing is recorded
as a warning, never a hard failure. Site-level (root only); category
service_worker. (Runtime offline behaviour is the separate `offline` validator.)
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

import lib

TOOL = "service_worker"
CATEGORY = "service_worker"

DEFAULT_NEVER_CACHE = ["/integrity.json", "/site-metadata.json", "/llms.txt", "/local/"]
DEFAULT_NEVER_CACHE_PREFIX = ["/.well-known/"]


def _origin(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, "", "", ""))


def _list_literal(js, var):
    """Extract string entries from a `var NAME = [ ... ]` literal."""
    m = re.search(re.escape(var) + r"\s*=\s*\[(.*?)\]", js, re.S)
    if not m:
        return None
    return re.findall(r"['\"]([^'\"]+)['\"]", m.group(1))


def run(target_url, cfg, http):
    if lib.path_of(target_url) != "/":
        return lib.result(
            target_url,
            TOOL,
            "skipped",
            raw_json={"reason": "service worker checked at site root only"},
        )

    origin = _origin(target_url)
    settings = (cfg.raw.get("phase3") or {}).get("service_worker") or {}
    required = settings.get("required_never_cache", DEFAULT_NEVER_CACHE)
    required_prefix = settings.get("required_never_cache_prefix", DEFAULT_NEVER_CACHE_PREFIX)

    sw = lib.fetch(http, origin + "/sw.js", cfg, allow_redirects=True)
    reg = lib.fetch(http, origin + "/sw-register.js", cfg, allow_redirects=True)
    edition = None
    try:
        man = lib.fetch(http, origin + "/integrity.json", cfg)
        if man.status_code == 200:
            edition = man.json().get("edition")
    except Exception:
        edition = None

    sw_ok = sw.status_code == 200
    measurements = [lib.measurement(CATEGORY, "service_worker.sw_reachable", value_bool=sw_ok)]
    observations = []
    if not sw_ok:
        return lib.result(
            target_url,
            TOOL,
            "error",
            source_url=origin + "/sw.js",
            measurements=measurements,
            observations=[
                lib.observation(
                    metric="service_worker.sw_reachable",
                    severity="error",
                    observation_type="service_worker",
                    code="SW_UNREACHABLE",
                    title="/sw.js not reachable",
                    message=f"status {sw.status_code}",
                    url=origin + "/sw.js",
                    fingerprint="sw:unreachable",
                )
            ],
            raw_json={"sw_status": sw.status_code},
        )

    js = sw.text
    cache_m = re.search(r"CACHE\s*=\s*['\"]([^'\"]+)['\"]", js)
    cache_version = cache_m.group(1) if cache_m else None
    if cache_version:
        measurements.append(
            lib.measurement(CATEGORY, "service_worker.cache_version", value_text=cache_version)
        )

    # cache_encodes_edition: uncertain parse -> warning (unavailable metric), not error
    if cache_version is None or edition is None:
        measurements.append(
            lib.measurement(
                CATEGORY,
                "service_worker.cache_encodes_edition",
                value_bool=None,
                status="unavailable",
            )
        )
        observations.append(
            lib.observation(
                metric="service_worker.cache_encodes_edition",
                severity="warning",
                observation_type="service_worker",
                code="SW_PARSE_UNCERTAIN",
                title="could not confirm cache/edition",
                message="CACHE or edition not parseable",
                url=origin + "/sw.js",
                fingerprint="sw:parse-uncertain",
            )
        )
        encodes = None
    else:
        encodes = edition in cache_version
        measurements.append(
            lib.measurement(CATEGORY, "service_worker.cache_encodes_edition", value_bool=encodes)
        )
        if not encodes:
            observations.append(
                lib.observation(
                    metric="service_worker.cache_encodes_edition",
                    severity="error",
                    observation_type="service_worker",
                    code="SW_EDITION_STALE",
                    title="SW cache version does not encode current edition",
                    message=f"edition {edition} not in CACHE {cache_version}",
                    url=origin + "/sw.js",
                    fingerprint="sw:edition-stale",
                    evidence=[
                        lib.evidence("text", "CACHE", cache_version),
                        lib.evidence("text", "edition", edition),
                    ],
                )
            )

    # never-cache coverage
    never = _list_literal(js, "NEVER_CACHE") or []
    never_prefix = _list_literal(js, "NEVER_CACHE_PREFIX") or []
    all_never = set(never) | set(never_prefix)
    missing = [p for p in required if p not in all_never] + [
        p for p in required_prefix if p not in all_never
    ]
    if never or never_prefix:
        complete = len(missing) == 0
        measurements.append(
            lib.measurement(CATEGORY, "service_worker.never_cache_complete", value_bool=complete)
        )
        measurements.append(
            lib.measurement(
                CATEGORY, "service_worker.never_cache_missing.count", value_numeric=len(missing)
            )
        )
        if missing:
            observations.append(
                lib.observation(
                    metric="service_worker.never_cache_complete",
                    severity="error",
                    observation_type="service_worker",
                    code="NEVER_CACHE_INCOMPLETE",
                    title=f"{len(missing)} sensitive path(s) not in NEVER_CACHE",
                    message=", ".join(missing),
                    url=origin + "/sw.js",
                    fingerprint="sw:never-cache-incomplete",
                    evidence=[lib.evidence("list", "missing", ", ".join(missing))],
                )
            )
    else:
        # could not parse the lists -> uncertain, not a failure
        measurements.append(
            lib.measurement(
                CATEGORY,
                "service_worker.never_cache_complete",
                value_bool=None,
                status="unavailable",
            )
        )

    scope_root = (
        bool(re.search(r"scope\s*:\s*['\"]/['\"]", reg.text)) if reg.status_code == 200 else False
    )
    measurements.append(
        lib.measurement(CATEGORY, "service_worker.scope_root", value_bool=scope_root)
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
        source_url=origin + "/sw.js",
        measurements=measurements,
        observations=observations,
        raw_json={
            "cache_version": cache_version,
            "edition": edition,
            "encodes_edition": encodes,
            "never_cache": never,
            "never_cache_prefix": never_prefix,
            "missing": missing,
        },
    )
