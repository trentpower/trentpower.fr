#!/usr/bin/env python3
"""Qualys SSL Labs validator.

Calls the free public SSL Labs API (v3), polling until the assessment is READY,
and records the TLS grade. No API key required, but a full assessment can take a
few minutes; cached results return quickly. Site-level.
"""

from __future__ import annotations

import time
from urllib.parse import urlsplit

import lib

TOOL = "ssl_labs"
CATEGORY = "tls"
ENDPOINT = "https://api.ssllabs.com/api/v3/analyze"


def run(site_url, cfg, http):
    host = urlsplit(site_url).netloc
    src = f"https://www.ssllabs.com/ssltest/analyze.html?d={host}"
    settings = cfg.raw.get("integration_settings") or {}
    max_wait = float(settings.get("ssl_labs_max_wait_seconds", 180))
    poll = float(settings.get("ssl_labs_poll_seconds", 15))
    timeout = float(cfg.network.get("timeout_seconds", 30))

    params = {"host": host, "all": "done", "fromCache": "on", "maxAge": "24"}
    deadline = time.monotonic() + max_wait
    data = None
    while True:
        r = http.get(ENDPOINT, params=params, timeout=timeout)
        if r.status_code == 429:
            return lib.result(
                site_url,
                TOOL,
                "unavailable",
                source_url=src,
                raw_json={"reason": "rate limited (HTTP 429)"},
            )
        if r.status_code != 200:
            return lib.result(
                site_url,
                TOOL,
                "unavailable",
                source_url=src,
                raw_json={"http_status": r.status_code},
            )
        data = r.json()
        status = data.get("status")
        if status == "READY":
            break
        if status == "ERROR":
            return lib.result(
                site_url,
                TOOL,
                "unavailable",
                source_url=src,
                raw_json={"status": "ERROR", "message": data.get("statusMessage")},
            )
        if time.monotonic() > deadline:
            return lib.result(
                site_url,
                TOOL,
                "unavailable",
                source_url=src,
                raw_json={"reason": f"not READY within {max_wait}s", "last_status": status},
            )
        time.sleep(poll)

    endpoints = data.get("endpoints", [])
    grades = [e.get("grade") for e in endpoints if e.get("grade")]
    if not grades:
        return lib.result(
            site_url,
            TOOL,
            "unavailable",
            source_url=src,
            raw_json={"reason": "no endpoint grades", "endpoints": len(endpoints)},
        )
    # report the worst grade across endpoints (highest rank = worst)
    worst = max(grades, key=lambda g: lib.GRADE_RANK.get(g, 99))

    measurements = [
        lib.measurement(CATEGORY, "tls.ssl_labs.grade", value_text=worst, grade=worst),
        lib.measurement(CATEGORY, "tls.ssl_labs.endpoints.count", value_numeric=len(endpoints)),
    ]
    observations = []
    for e in endpoints:
        g = e.get("grade")
        if g and lib.GRADE_RANK.get(g, 99) > lib.GRADE_RANK.get("A", 1):
            observations.append(
                lib.observation(
                    metric="tls.ssl_labs.grade",
                    severity="warning",
                    observation_type="audit",
                    code="SSL_GRADE",
                    title=f"SSL Labs grade {g} on {e.get('ipAddress')}",
                    message=e.get("statusMessage", ""),
                    url=src,
                    fingerprint=f"ssl_labs:grade:{host}:{e.get('ipAddress')}",
                )
            )

    status = "ok" if lib.GRADE_RANK.get(worst, 99) <= lib.GRADE_RANK["A"] else "warning"
    return lib.result(
        site_url,
        TOOL,
        status,
        source_url=src,
        measurements=measurements,
        observations=observations,
        raw_json={"grade": worst, "grades": grades, "endpoints": len(endpoints)},
    )
