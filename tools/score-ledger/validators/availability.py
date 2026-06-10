#!/usr/bin/env python3
"""Availability validator: reachability, redirects, timing, content type/size."""

from __future__ import annotations

import time

import lib

TOOL = "availability"
CATEGORY = "availability"


def run(target_url, cfg, http):
    t0 = time.monotonic()
    resp = lib.fetch(http, target_url, cfg, allow_redirects=True)
    response_ms = (time.monotonic() - t0) * 1000.0

    redirect_count = len(resp.history)
    final_url = resp.url
    content_type = resp.headers.get("Content-Type", "")
    body = resp.content or b""
    clen_header = resp.headers.get("Content-Length")
    content_length = int(clen_header) if (clen_header and clen_header.isdigit()) else len(body)

    status = "ok" if resp.status_code == 200 else ("warning" if resp.ok else "error")

    measurements = [
        lib.measurement(
            CATEGORY,
            "availability.status_code",
            value_numeric=resp.status_code,
            value_text=str(resp.status_code),
            status=status,
        ),
        lib.measurement(CATEGORY, "availability.response_ms", value_numeric=round(response_ms, 1)),
        lib.measurement(CATEGORY, "availability.redirect_count", value_numeric=redirect_count),
        lib.measurement(CATEGORY, "availability.final_url", value_text=final_url),
        lib.measurement(CATEGORY, "availability.content_type", value_text=content_type),
        lib.measurement(
            CATEGORY, "availability.content_length_bytes", value_numeric=content_length
        ),
    ]

    observations = []
    if resp.status_code != 200:
        observations.append(
            lib.observation(
                metric="availability.status_code",
                severity="error",
                observation_type="status",
                code=f"HTTP_{resp.status_code}",
                title=f"unexpected status {resp.status_code}",
                message=f"{target_url} returned {resp.status_code}",
                url=target_url,
                fingerprint=f"availability:status:{resp.status_code}:{lib.path_of(target_url)}",
                evidence=[
                    lib.evidence(
                        "http_status", "Status", str(resp.status_code), source_url=target_url
                    )
                ],
            )
        )
    if redirect_count:
        chain = " -> ".join([h.url for h in resp.history] + [final_url])
        observations.append(
            lib.observation(
                metric="availability.redirect_count",
                severity="info",
                observation_type="redirect",
                code="REDIRECT",
                title=f"{redirect_count} redirect(s)",
                message=chain,
                url=target_url,
                fingerprint=f"availability:redirect:{lib.path_of(target_url)}",
                evidence=[lib.evidence("chain", "Redirect chain", chain, source_url=target_url)],
            )
        )

    raw = {
        "status_code": resp.status_code,
        "final_url": final_url,
        "response_ms": round(response_ms, 1),
        "redirect_count": redirect_count,
        "content_type": content_type,
        "content_length_bytes": content_length,
        "history": [h.status_code for h in resp.history],
    }
    return lib.result(
        target_url, TOOL, status, measurements=measurements, observations=observations, raw_json=raw
    )
