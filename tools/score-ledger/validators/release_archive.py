#!/usr/bin/env python3
"""Release-archive completeness validator.

Confirms the current edition's signed release exists and is well-formed against
the live published artifacts: release.json (+ .sig), SHA256SUMS, the expected
manifest keys, the detached-signature validity, and whether a signed
TESTRESULTS.txt has been published into the release yet.

Site-level: runs once per run (at the root target only, like trust_files).
"""

from __future__ import annotations

import os
import shutil
import tempfile
from urllib.parse import urlsplit, urlunsplit

import attest
import lib

TOOL = "release_archive"
CATEGORY = "release"
EXPECTED_MANIFESTS = {"exclusions", "integrity_redistributable", "archive_checksums"}


def _origin(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, "", "", ""))


def _status(http, url, cfg):
    try:
        return lib.fetch(http, url, cfg, allow_redirects=True)
    except Exception:
        return None


def run(target_url, cfg, http):
    if lib.path_of(target_url) != "/":
        return lib.result(
            target_url,
            TOOL,
            "skipped",
            raw_json={"reason": "release archive checked at site root only"},
        )

    origin = _origin(target_url)
    # edition comes from the live signed integrity manifest
    edition = None
    try:
        man = lib.fetch(http, origin + "/integrity.json", cfg)
        if man.status_code == 200:
            edition = man.json().get("edition")
    except Exception:
        edition = None
    if not edition:
        return lib.result(
            target_url,
            TOOL,
            "unavailable",
            raw_json={"reason": "could not resolve edition from integrity.json"},
        )

    base = f"{origin}/integrity/releases/{edition}"
    rel = _status(http, f"{base}/release.json", cfg)
    sig = _status(http, f"{base}/release.json.sig", cfg)
    sums = _status(http, f"{base}/SHA256SUMS", cfg)
    tr = _status(http, f"{base}/TESTRESULTS.txt", cfg)
    trsig = _status(http, f"{base}/TESTRESULTS.txt.sig", cfg)

    def code(resp):
        return resp.status_code if resp is not None else 0

    measurements = [
        lib.measurement(CATEGORY, "release.edition", value_text=edition),
        lib.measurement(
            CATEGORY,
            "release.release_json.status_code",
            value_numeric=code(rel),
            value_text=str(code(rel)),
            status="ok" if code(rel) == 200 else "warning",
        ),
        lib.measurement(
            CATEGORY,
            "release.release_json_sig.status_code",
            value_numeric=code(sig),
            value_text=str(code(sig)),
            status="ok" if code(sig) == 200 else "warning",
        ),
        lib.measurement(
            CATEGORY,
            "release.archive_checksums.status_code",
            value_numeric=code(sums),
            value_text=str(code(sums)),
            status="ok" if code(sums) == 200 else "warning",
        ),
    ]
    observations = []

    # manifests completeness
    manifests_complete = False
    if rel is not None and rel.status_code == 200:
        try:
            keys = set((rel.json().get("manifests") or {}).keys())
            manifests_complete = EXPECTED_MANIFESTS.issubset(keys)
            if not manifests_complete:
                observations.append(
                    lib.observation(
                        metric="release.manifests_complete",
                        severity="warning",
                        observation_type="release",
                        code="MANIFESTS_INCOMPLETE",
                        title="release.json manifests block incomplete",
                        message=f"missing: {sorted(EXPECTED_MANIFESTS - keys)}",
                        url=f"{base}/release.json",
                        fingerprint=f"release:manifests:{edition}",
                    )
                )
        except Exception:
            pass
    measurements.append(
        lib.measurement(CATEGORY, "release.manifests_complete", value_bool=manifests_complete)
    )

    # detached-signature validity (verify against published key)
    if shutil.which("gpg") is None:
        measurements.append(
            lib.measurement(
                CATEGORY, "release.signature_valid", value_bool=None, status="unavailable"
            )
        )
    elif rel is not None and rel.status_code == 200 and sig is not None and sig.status_code == 200:
        ok = False
        with tempfile.TemporaryDirectory() as tmp:
            jp = os.path.join(tmp, "release.json")
            sp = os.path.join(tmp, "release.json.sig")
            with open(jp, "wb") as fh:
                fh.write(rel.content)
            with open(sp, "wb") as fh:
                fh.write(sig.content)
            ok, msg = attest.verify_file(cfg, jp, sp)
        measurements.append(lib.measurement(CATEGORY, "release.signature_valid", value_bool=ok))
        if not ok:
            observations.append(
                lib.observation(
                    metric="release.signature_valid",
                    severity="error",
                    observation_type="release",
                    code="RELEASE_SIG_INVALID",
                    title=f"release.json.sig does not verify for {edition}",
                    message=msg,
                    url=f"{base}/release.json.sig",
                    fingerprint=f"release:sig-invalid:{edition}",
                )
            )
    else:
        measurements.append(
            lib.measurement(CATEGORY, "release.signature_valid", value_bool=False, status="warning")
        )

    # TESTRESULTS presence (a published, signed attestation in the release)
    tr_present = code(tr) == 200
    trsig_present = code(trsig) == 200
    measurements.append(
        lib.measurement(CATEGORY, "release.testresults_present", value_bool=tr_present)
    )
    measurements.append(
        lib.measurement(CATEGORY, "release.testresults_sig_present", value_bool=trsig_present)
    )
    if not tr_present:
        observations.append(
            lib.observation(
                metric="release.testresults_present",
                severity="info",
                observation_type="release",
                code="TESTRESULTS_ABSENT",
                title=f"TESTRESULTS.txt not yet published in release {edition}",
                message=(
                    "Generate a signed TESTRESULTS.txt for this edition and add "
                    "it (with its .sig) to the release folder and manifest."
                ),
                url=f"{base}/",
                fingerprint=f"release:testresults-absent:{edition}",
            )
        )

    if any(o["severity"] == "error" for o in observations):
        status = "error"
    elif any(o["severity"] == "warning" for o in observations):
        status = "warning"
    else:
        status = "ok"
    return lib.result(
        target_url,
        TOOL,
        status,
        source_url=f"{base}/release.json",
        measurements=measurements,
        observations=observations,
        raw_json={
            "edition": edition,
            "release_json": code(rel),
            "release_json_sig": code(sig),
            "sha256sums": code(sums),
            "manifests_complete": manifests_complete,
            "testresults_present": tr_present,
        },
    )
