#!/usr/bin/env python3
"""CSP quality validator.

Goes beyond "is a CSP present" (headers.py) to assess policy *quality*: no
unsafe-inline / unsafe-eval / wildcard sources, object-src 'none', base-uri
'self', frame-ancestors restriction, and require-trusted-types-for. Hash-based
inline allowances ('sha256-...') are NOT weaknesses - they are the intended,
safe mechanism, so they are never flagged. Per-target; category security.
"""

from __future__ import annotations

import lib

TOOL = "csp_quality"
CATEGORY = "security"

# fetch directives where a bare * / scheme wildcard would be a real weakness
_FETCH_DIRECTIVES = (
    "default-src",
    "script-src",
    "style-src",
    "img-src",
    "font-src",
    "connect-src",
    "frame-src",
    "child-src",
    "worker-src",
    "manifest-src",
    "object-src",
)


def _parse(policy):
    out = {}
    for part in policy.split(";"):
        toks = part.split()
        if toks:
            out[toks[0].lower()] = [t for t in toks[1:]]
    return out


def run(target_url, cfg, http):
    resp = lib.fetch(http, target_url, cfg, allow_redirects=True)
    present = {k.lower(): v for k, v in resp.headers.items()}
    csp = present.get("content-security-policy")
    path = lib.path_of(target_url)

    if not csp:
        return lib.result(
            target_url,
            TOOL,
            "warning",
            measurements=[lib.measurement(CATEGORY, "csp_quality.present", value_bool=False)],
            observations=[
                lib.observation(
                    metric="csp_quality.present",
                    severity="error",
                    observation_type="csp",
                    code="CSP_ABSENT",
                    title="no Content-Security-Policy header",
                    message="page served without a CSP",
                    url=target_url,
                    fingerprint=f"csp:absent:{path}",
                )
            ],
            raw_json={"present": False},
        )

    d = _parse(csp)
    blob = csp.lower()

    def has_wildcard():
        for name in _FETCH_DIRECTIVES:
            for src in d.get(name, []):
                s = src.strip("'\"").lower()
                if s in ("*", "http:", "https:", "data:", "http://*", "https://*"):
                    return True, f"{name} {src}"
        return False, None

    wild, wild_where = has_wildcard()
    checks = {
        "no_unsafe_inline": ("'unsafe-inline'" not in blob, "unsafe-inline present"),
        "no_unsafe_eval": ("'unsafe-eval'" not in blob, "unsafe-eval present"),
        "no_wildcard": (not wild, f"wildcard source: {wild_where}"),
        "object_src_none": (d.get("object-src") == ["'none'"], "object-src not 'none'"),
        "base_uri_self": (d.get("base-uri") == ["'self'"], "base-uri not 'self'"),
        "frame_ancestors_none": (
            bool(d.get("frame-ancestors")) and d.get("frame-ancestors") != ["*"],
            "frame-ancestors missing/permissive",
        ),
        "trusted_types_required": ("require-trusted-types-for" in d, "trusted-types not required"),
    }

    measurements = [lib.measurement(CATEGORY, "csp_quality.present", value_bool=True)]
    observations = []
    weaknesses = 0
    for key, (ok, why) in checks.items():
        measurements.append(lib.measurement(CATEGORY, f"csp_quality.{key}", value_bool=ok))
        if not ok:
            weaknesses += 1
            # unsafe-inline/eval are real breakage; the rest are weaknesses.
            sev = "error" if key in ("no_unsafe_inline", "no_unsafe_eval") else "warning"
            observations.append(
                lib.observation(
                    metric=f"csp_quality.{key}",
                    severity=sev,
                    observation_type="csp_weakness",
                    code=f"CSP_{key.upper()}",
                    title=f"CSP: {why}",
                    message=f"{why} in served CSP",
                    url=target_url,
                    fingerprint=f"csp:{key}:{path}",
                    evidence=[lib.evidence("header", "CSP", csp[:400], source_url=target_url)],
                )
            )
    measurements.append(
        lib.measurement(CATEGORY, "csp_quality.weaknesses.count", value_numeric=weaknesses)
    )

    # record trusted-types factually (not penalised beyond the boolean above)
    if "trusted-types" in d:
        measurements.append(
            lib.measurement(
                CATEGORY,
                "csp_quality.trusted_types.text",
                value_text=" ".join(d.get("trusted-types", [])) or "(default)",
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
        raw_json={"present": True, "weaknesses": weaknesses, "directives": list(d.keys())},
    )
