#!/usr/bin/env python3
"""Mozilla (MDN) HTTP Observatory validator.

Calls the free public Observatory v2 API and records the security grade, score
and test pass/fail counts. No API key required. Site-level.
"""

from __future__ import annotations

from urllib.parse import urlsplit

import lib

TOOL = "mozilla_observatory"
CATEGORY = "security"
ENDPOINT = "https://observatory-api.mdn.mozilla.net/api/v2/scan"


def run(site_url, cfg, http):
    host = urlsplit(site_url).netloc
    src = f"https://developer.mozilla.org/en-US/observatory/analyze?host={host}"
    timeout = float(cfg.network.get("timeout_seconds", 30))
    resp = http.post(ENDPOINT, params={"host": host}, timeout=timeout)
    if resp.status_code != 200:
        return lib.result(
            site_url,
            TOOL,
            "unavailable",
            source_url=src,
            raw_json={"http_status": resp.status_code, "body": resp.text[:500]},
        )
    data = resp.json()
    if data.get("error"):
        return lib.result(
            site_url, TOOL, "unavailable", source_url=src, raw_json={"error": data.get("error")}
        )

    grade = data.get("grade")
    score = data.get("score")
    failed = data.get("tests_failed")
    passed = data.get("tests_passed")
    version = str(data.get("algorithm_version") or "")

    measurements = [
        lib.measurement(CATEGORY, "security.observatory.grade", value_text=grade, grade=grade),
        lib.measurement(
            CATEGORY, "security.observatory.score", value_numeric=score, normalised_score=score
        ),
        lib.measurement(CATEGORY, "security.observatory.tests_failed", value_numeric=failed),
        lib.measurement(CATEGORY, "security.observatory.tests_passed", value_numeric=passed),
    ]
    observations = []
    if failed:
        observations.append(
            lib.observation(
                metric="security.observatory.tests_failed",
                severity="warning" if (grade or "").startswith(("A", "B")) else "error",
                observation_type="audit",
                code="OBSERVATORY_FAIL",
                title=f"Observatory: {failed} test(s) failed (grade {grade})",
                message=f"score {score}, {failed} failed, {passed} passed",
                url=src,
                fingerprint=f"observatory:tests-failed:{host}",
                evidence=[
                    lib.evidence("url", "Details", data.get("details_url") or src, source_url=src)
                ],
            )
        )

    return lib.result(
        site_url,
        TOOL,
        "ok",
        tool_version=version,
        source_url=src,
        measurements=measurements,
        observations=observations,
        raw_json={
            "grade": grade,
            "score": score,
            "tests_failed": failed,
            "tests_passed": passed,
            "details_url": data.get("details_url"),
        },
    )
