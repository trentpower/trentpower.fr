#!/usr/bin/env python3
"""W3C HTML validator (Nu) check.

Submits each page's HTML to the W3C Nu validator and records error/warning/info
counts plus one observation per validator message. If the service is unreachable
or rate-limits, the check is recorded unavailable (never fatal).
"""

from __future__ import annotations

import lib

TOOL = "html_w3c"
CATEGORY = "html"
ENDPOINT = "https://validator.w3.org/nu/?out=json"


def _classify(msg):
    mtype = msg.get("type")
    subtype = msg.get("subType")
    if mtype == "error":
        return "error"
    if mtype == "info" and subtype == "warning":
        return "warning"
    if mtype == "info":
        return "info"
    return "other"


def run(target_url, cfg, http):
    # fetch the live page first (validate exactly what is served)
    page = lib.fetch(http, target_url, cfg, allow_redirects=True)
    lib.polite_delay(cfg)
    headers = {
        "Content-Type": "text/html; charset=utf-8",
        "User-Agent": cfg.network.get("user_agent", "score-ledger"),
    }
    timeout = float(cfg.network.get("timeout_seconds", 30))
    resp = http.post(ENDPOINT, data=page.content, headers=headers, timeout=timeout)
    if resp.status_code != 200:
        return lib.result(
            target_url,
            TOOL,
            "unavailable",
            source_url=ENDPOINT,
            raw_json={"http_status": resp.status_code},
        )

    data = resp.json()
    messages = data.get("messages", [])
    path = lib.path_of(target_url)

    if any(m.get("type") == "non-document-error" for m in messages):
        return lib.result(
            target_url,
            TOOL,
            "unavailable",
            source_url=ENDPOINT,
            raw_json={"messages": messages[:5]},
        )

    errors = warnings = infos = 0
    observations = []
    for _i, m in enumerate(messages):
        cls = _classify(m)
        if cls == "error":
            errors += 1
            metric, severity = "html.errors.count", "error"
        elif cls == "warning":
            warnings += 1
            metric, severity = "html.warnings.count", "warning"
        elif cls == "info":
            infos += 1
            metric, severity = "html.info.count", "info"
        else:
            continue
        text = (m.get("message") or "").strip()
        line = m.get("lastLine")
        col = m.get("firstColumn") or m.get("lastColumn")
        extract = m.get("extract")
        fp_text = text[:60].lower().replace(" ", "-")
        observations.append(
            lib.observation(
                metric=metric,
                severity=severity,
                observation_type="validator_message",
                code=cls,
                title=text[:120],
                message=text,
                line=line,
                column=col,
                url=target_url,
                fingerprint=f"html:{cls}:{fp_text}:{path}",
                evidence=[
                    lib.evidence(
                        "extract",
                        "Extract",
                        (extract or "")[:200],
                        excerpt=extract,
                        source_url=target_url,
                    )
                ],
            )
        )

    measurements = [
        lib.measurement(CATEGORY, "html.errors.count", value_numeric=errors),
        lib.measurement(CATEGORY, "html.warnings.count", value_numeric=warnings),
        lib.measurement(CATEGORY, "html.info.count", value_numeric=infos),
    ]
    status = "error" if errors else ("warning" if warnings else "ok")
    return lib.result(
        target_url,
        TOOL,
        status,
        source_url=ENDPOINT,
        measurements=measurements,
        observations=observations,
        raw_json={
            "errors": errors,
            "warnings": warnings,
            "info": infos,
            "message_count": len(messages),
        },
    )
