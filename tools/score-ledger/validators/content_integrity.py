#!/usr/bin/env python3
"""Content-consistency validator (source mirrors vs the integrity manifest).

For each canonical page it confirms, against the live published artifacts:
  - the page is listed in /integrity.json
  - its source mirror (/source/<path>index.html.txt) is listed too
  - the live source mirror hashes to the manifest's recorded sha256
  - the /verify/ data references that source mirror

The live canonical HTML is deliberately NOT hashed: it carries an injected
footer sha + verification SRI and legitimately drifts from the build-time hash.
The static source-mirror .txt is the stable anchor. Per-target; /integrity.json
and the verify data are fetched once per run (process-scoped cache).
"""

from __future__ import annotations

import base64
import hashlib
from urllib.parse import urlsplit, urlunsplit

import lib

TOOL = "content_integrity"
CATEGORY = "content_consistency"

# process scope == one run; reset implicitly per CLI invocation
_CACHE = {}


def _origin(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, "", "", ""))


def _manifest(origin, cfg, http):
    if ("manifest", origin) not in _CACHE:
        try:
            r = lib.fetch(http, origin + "/integrity.json", cfg, allow_redirects=True)
            _CACHE[("manifest", origin)] = r.json() if r.status_code == 200 else None
        except Exception:
            _CACHE[("manifest", origin)] = None
    return _CACHE[("manifest", origin)]


def _verify_data(origin, cfg, http):
    if ("verify", origin) not in _CACHE:
        try:
            r = lib.fetch(http, origin + "/verify/verification-data.js", cfg, allow_redirects=True)
            _CACHE[("verify", origin)] = r.text if r.status_code == 200 else ""
        except Exception:
            _CACHE[("verify", origin)] = ""
    return _CACHE[("verify", origin)]


def _keys(path):
    """(canonical_key, mirror_key, mirror_path) for a target path."""
    seg = "/".join(s for s in path.split("/") if s)
    if seg:
        return f"{seg}/index.html", f"source/{seg}/index.html.txt", f"/source/{seg}/index.html.txt"
    return "index.html", "source/index.html.txt", "/source/index.html.txt"


def _sri(body):
    return "sha256-" + base64.b64encode(hashlib.sha256(body).digest()).decode("ascii")


def run(target_url, cfg, http):
    origin = _origin(target_url)
    path = lib.path_of(target_url)
    manifest = _manifest(origin, cfg, http)
    if not manifest or "files" not in manifest:
        return lib.result(
            target_url, TOOL, "unavailable", raw_json={"reason": "integrity.json unavailable"}
        )

    files = manifest.get("files", {})
    canonical_key, mirror_key, mirror_path = _keys(path)
    canonical_in = canonical_key in files
    mirror_in = mirror_key in files

    hash_match = None
    expected = files.get(mirror_key)
    actual = None
    if mirror_in:
        try:
            r = lib.fetch(http, origin + mirror_path, cfg, allow_redirects=True)
            if r.status_code == 200:
                actual = _sri(r.content or b"")
                hash_match = actual == expected
        except Exception:
            hash_match = None

    verify_text = _verify_data(origin, cfg, http)
    verify_links = mirror_path in verify_text if verify_text else False

    measurements = [
        lib.measurement(
            CATEGORY, "content_consistency.canonical_in_manifest", value_bool=canonical_in
        ),
        lib.measurement(
            CATEGORY, "content_consistency.source_mirror_in_manifest", value_bool=mirror_in
        ),
        lib.measurement(
            CATEGORY, "content_consistency.verify_links_source", value_bool=verify_links
        ),
    ]
    if hash_match is not None:
        measurements.append(
            lib.measurement(
                CATEGORY, "content_consistency.source_mirror_hash_match", value_bool=hash_match
            )
        )

    observations = []
    if not canonical_in:
        observations.append(
            lib.observation(
                metric="content_consistency.canonical_in_manifest",
                severity="error",
                observation_type="integrity",
                code="CANONICAL_ABSENT",
                title=f"{canonical_key} missing from integrity.json",
                message=f"{canonical_key} not listed in the signed integrity manifest",
                url=target_url,
                fingerprint=f"content:canonical-absent:{path}",
            )
        )
    if not mirror_in:
        observations.append(
            lib.observation(
                metric="content_consistency.source_mirror_in_manifest",
                severity="warning",
                observation_type="integrity",
                code="MIRROR_ABSENT",
                title=f"{mirror_key} missing from integrity.json",
                message=f"source mirror {mirror_key} not in the integrity manifest",
                url=target_url,
                fingerprint=f"content:mirror-absent:{path}",
            )
        )
    if hash_match is False:
        observations.append(
            lib.observation(
                metric="content_consistency.source_mirror_hash_match",
                severity="error",
                observation_type="integrity",
                code="MIRROR_HASH_MISMATCH",
                title=f"source mirror hash mismatch for {mirror_path}",
                message=f"expected {expected}, served {actual}",
                url=origin + mirror_path,
                fingerprint=f"content:mirror-hash:{path}",
                evidence=[
                    lib.evidence("hash", "expected", expected or "-"),
                    lib.evidence("hash", "served", actual or "-", source_url=origin + mirror_path),
                ],
            )
        )
    if not verify_links:
        observations.append(
            lib.observation(
                metric="content_consistency.verify_links_source",
                severity="warning",
                observation_type="integrity",
                code="VERIFY_NO_LINK",
                title=f"verify data does not reference {mirror_path}",
                message="the /verify/ data did not reference this page's source mirror",
                url=target_url,
                fingerprint=f"content:verify-link:{path}",
            )
        )

    if observations and any(o["severity"] == "error" for o in observations):
        status = "error"
    elif observations:
        status = "warning"
    else:
        status = "ok"
    return lib.result(
        target_url,
        TOOL,
        status,
        source_url=origin + "/integrity.json",
        measurements=measurements,
        observations=observations,
        raw_json={
            "canonical_key": canonical_key,
            "mirror_key": mirror_key,
            "canonical_in": canonical_in,
            "mirror_in": mirror_in,
            "expected": expected,
            "actual": actual,
            "hash_match": hash_match,
            "verify_links": verify_links,
        },
    )
