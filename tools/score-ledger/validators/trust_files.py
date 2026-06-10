#!/usr/bin/env python3
"""Trust-file validator: status, content type, size, sha256 and JSON validity for
the site's well-known and trust files.

These are site-level, so the checks run only against the root target ("/"); for
the language editions the validator returns a skipped result to avoid triplicate
fetches of the same files.
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit, urlunsplit

import lib

TOOL = "trust_files"
CATEGORY = "trust_files"


def _origin(url):
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def run(target_url, cfg, http):
    if lib.path_of(target_url) != "/":
        return lib.result(
            target_url,
            TOOL,
            "skipped",
            raw_json={"reason": "trust files checked at site root only"},
        )

    origin = _origin(target_url)
    json_files = set(cfg.trust_json_files)
    measurements = []
    observations = []
    raw = {}

    for key, path in cfg.trust_paths.items():
        url = origin + path
        lib.polite_delay(cfg)
        try:
            resp = lib.fetch(http, url, cfg, allow_redirects=True)
        except Exception as e:  # one missing file must not sink the others
            observations.append(
                lib.observation(
                    metric=f"trust.{key}.status_code",
                    severity="warning",
                    observation_type="fetch_error",
                    code="FETCH_ERROR",
                    title=f"could not fetch {path}",
                    message=repr(e),
                    url=url,
                    fingerprint=f"trust:fetch-error:{key}",
                )
            )
            measurements.append(
                lib.measurement(
                    CATEGORY,
                    f"trust.{key}.status_code",
                    value_numeric=0,
                    value_text="error",
                    status="error",
                )
            )
            raw[key] = {"error": repr(e)}
            continue

        body = resp.content or b""
        ctype = resp.headers.get("Content-Type", "")
        size = len(body)
        digest = lib.sha256_bytes(body)
        ok = resp.status_code == 200

        measurements.append(
            lib.measurement(
                CATEGORY,
                f"trust.{key}.status_code",
                value_numeric=resp.status_code,
                value_text=str(resp.status_code),
                status="ok" if ok else "warning",
            )
        )
        measurements.append(
            lib.measurement(CATEGORY, f"trust.{key}.content_type", value_text=ctype)
        )
        measurements.append(
            lib.measurement(CATEGORY, f"trust.{key}.size_bytes", value_numeric=size)
        )
        measurements.append(lib.measurement(CATEGORY, f"trust.{key}.sha256", value_text=digest))

        entry = {
            "status_code": resp.status_code,
            "content_type": ctype,
            "size_bytes": size,
            "sha256": digest,
        }

        if key in json_files:
            valid_json = False
            if ok:
                try:
                    json.loads(body.decode("utf-8", "replace"))
                    valid_json = True
                except json.JSONDecodeError as e:
                    observations.append(
                        lib.observation(
                            metric=f"trust.{key}.valid_json",
                            severity="error",
                            observation_type="parse_error",
                            code="JSON_INVALID",
                            title=f"{path} is not valid JSON",
                            message=str(e),
                            url=url,
                            fingerprint=f"trust:json-invalid:{key}",
                        )
                    )
            measurements.append(
                lib.measurement(CATEGORY, f"trust.{key}.valid_json", value_bool=valid_json)
            )
            entry["valid_json"] = valid_json

        if not ok:
            observations.append(
                lib.observation(
                    metric=f"trust.{key}.status_code",
                    severity="warning",
                    observation_type="status",
                    code=f"HTTP_{resp.status_code}",
                    title=f"{path} returned {resp.status_code}",
                    message=f"expected 200 for {path}",
                    url=url,
                    fingerprint=f"trust:status:{key}:{resp.status_code}",
                )
            )
        raw[key] = entry

    status = "warning" if any(o["severity"] in ("warning", "error") for o in observations) else "ok"
    return lib.result(
        target_url, TOOL, status, measurements=measurements, observations=observations, raw_json=raw
    )
