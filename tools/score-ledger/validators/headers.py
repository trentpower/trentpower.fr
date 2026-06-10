#!/usr/bin/env python3
"""Security/response header presence validator."""

from __future__ import annotations

import lib

TOOL = "headers"
CATEGORY = "headers"

# metric suffix -> (header names that satisfy it, severity if missing)
HEADER_CHECKS = [
    ("csp", ["content-security-policy"], "warning"),
    ("hsts", ["strict-transport-security"], "warning"),
    ("referrer_policy", ["referrer-policy"], "info"),
    ("permissions_policy", ["permissions-policy"], "info"),
    ("coop", ["cross-origin-opener-policy"], "info"),
    ("coep", ["cross-origin-embedder-policy"], "info"),
    ("corp", ["cross-origin-resource-policy"], "info"),
    ("x_content_type_options", ["x-content-type-options"], "warning"),
    ("frame_protection", ["x-frame-options", "content-security-policy"], "warning"),
]


def run(target_url, cfg, http):
    resp = lib.fetch(http, target_url, cfg, allow_redirects=True)
    # case-insensitive header view
    present = {k.lower(): v for k, v in resp.headers.items()}

    measurements = []
    observations = []
    captured = {}
    for key, names, severity in HEADER_CHECKS:
        # frame_protection is satisfied by X-Frame-Options OR a CSP frame-ancestors
        if key == "frame_protection":
            xfo = present.get("x-frame-options")
            csp = present.get("content-security-policy", "")
            is_present = bool(xfo) or ("frame-ancestors" in csp.lower())
            value = xfo or ("frame-ancestors(csp)" if "frame-ancestors" in csp.lower() else None)
        else:
            value = next((present.get(n) for n in names if present.get(n)), None)
            is_present = value is not None
        captured[key] = value
        measurements.append(
            lib.measurement(
                CATEGORY,
                f"headers.{key}.present",
                value_bool=is_present,
                value_text=(value if isinstance(value, str) else None),
            )
        )
        if not is_present:
            observations.append(
                lib.observation(
                    metric=f"headers.{key}.present",
                    severity=severity,
                    observation_type="missing_header",
                    code=f"MISSING_{key.upper()}",
                    title=f"missing header: {key}",
                    message=f"{names[0]} not present on {target_url}",
                    url=target_url,
                    fingerprint=f"headers:missing:{key}:{lib.path_of(target_url)}",
                    evidence=[lib.evidence("header", "Header", names[0], source_url=target_url)],
                )
            )

    raw = {"checked": {k: captured[k] for k, _, _ in HEADER_CHECKS}}
    status = "warning" if any(o["severity"] == "warning" for o in observations) else "ok"
    return lib.result(
        target_url, TOOL, status, measurements=measurements, observations=observations, raw_json=raw
    )
