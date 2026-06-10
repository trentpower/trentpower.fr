#!/usr/bin/env python3
"""W3C CSS validator (Jigsaw) check.

Discovers the stylesheets referenced by each page and validates each unique sheet
once per run (a process-scoped cache dedupes shared stylesheets such as a common
styles.css). Per-page css.errors.count / css.warnings.count are the sum across
that page's stylesheets; each validator message becomes an observation.

If Jigsaw is unreachable the check is recorded unavailable (never fatal).
"""

from __future__ import annotations

from urllib.parse import urljoin

import lib
from bs4 import BeautifulSoup

TOOL = "css_w3c"
CATEGORY = "css"
ENDPOINT = "https://jigsaw.w3.org/css-validator/validator"
MAX_OBS_PER_SHEET = 40

# Process-scoped cache: one CLI invocation == one run, so module state is
# per-run. Maps stylesheet URL -> validated sub-result dict.
_CACHE = {}


def _validate_sheet(url, cfg, http):
    if url in _CACHE:
        return _CACHE[url]
    lib.polite_delay(cfg)
    timeout = float(cfg.network.get("timeout_seconds", 30))
    profile = (cfg.raw.get("css") or {}).get("profile", "css3")
    params = {"uri": url, "profile": profile, "output": "json"}
    try:
        resp = http.get(ENDPOINT, params=params, timeout=timeout)
        if resp.status_code != 200:
            out = {
                "status": "unavailable",
                "http_status": resp.status_code,
                "errorcount": None,
                "warningcount": None,
                "errors": [],
                "warnings": [],
            }
        else:
            data = resp.json().get("cssvalidation", {})
            result = data.get("result", {})
            out = {
                "status": "ok",
                "errorcount": int(result.get("errorcount", 0)),
                "warningcount": int(result.get("warningcount", 0)),
                "errors": data.get("errors", []),
                "warnings": data.get("warnings", []),
            }
    except Exception as e:
        out = {
            "status": "unavailable",
            "error": repr(e),
            "errorcount": None,
            "warningcount": None,
            "errors": [],
            "warnings": [],
        }
    _CACHE[url] = out
    return out


def _discover_sheets(soup, base):
    sheets = []
    for link in soup.find_all("link", rel=lambda v: v and "stylesheet" in v):
        href = link.get("href")
        if href:
            absolute = urljoin(base, href).split("#")[0]
            if absolute.startswith(("http://", "https://")) and absolute not in sheets:
                sheets.append(absolute)
    return sheets


def run(target_url, cfg, http):
    page = lib.fetch(http, target_url, cfg, allow_redirects=True)
    soup = BeautifulSoup(page.text, "lxml")
    base = page.url
    path = lib.path_of(target_url)
    sheets = _discover_sheets(soup, base)

    if not sheets:
        return lib.result(
            target_url,
            TOOL,
            "ok",
            source_url=ENDPOINT,
            measurements=[
                lib.measurement(CATEGORY, "css.errors.count", value_numeric=0),
                lib.measurement(CATEGORY, "css.warnings.count", value_numeric=0),
            ],
            raw_json={"stylesheets": []},
        )

    total_err = total_warn = 0
    observations = []
    any_unavailable = False
    raw_sheets = {}
    for sheet in sheets:
        res = _validate_sheet(sheet, cfg, http)
        raw_sheets[sheet] = {
            "status": res["status"],
            "errorcount": res["errorcount"],
            "warningcount": res["warningcount"],
        }
        if res["status"] != "ok":
            any_unavailable = True
            continue
        total_err += res["errorcount"]
        total_warn += res["warningcount"]
        for kind, metric, sev in [
            ("errors", "css.errors.count", "error"),
            ("warnings", "css.warnings.count", "warning"),
        ]:
            for m in res[kind][:MAX_OBS_PER_SHEET]:
                msg = (m.get("message") or "").strip()
                line = m.get("line")
                fp_text = msg[:50].lower().replace(" ", "-")
                observations.append(
                    lib.observation(
                        metric=metric,
                        severity=sev,
                        observation_type="validator_message",
                        code=kind[:-1],
                        title=f"{sheet.rsplit('/', 1)[-1]}: {msg[:100]}",
                        message=msg,
                        line=line,
                        url=sheet,
                        fingerprint=f"css:{kind[:-1]}:{sheet.rsplit('/', 1)[-1]}:{line}:{fp_text}",
                        evidence=[
                            lib.evidence(
                                "css",
                                "Stylesheet",
                                sheet,
                                excerpt=m.get("context"),
                                source_url=sheet,
                            )
                        ],
                    )
                )

    # If every sheet failed to validate, the metric is not trustworthy.
    if (
        any_unavailable
        and total_err == 0
        and total_warn == 0
        and all(raw_sheets[s]["status"] != "ok" for s in sheets)
    ):
        return lib.result(
            target_url,
            TOOL,
            "unavailable",
            source_url=ENDPOINT,
            raw_json={"stylesheets": raw_sheets},
        )

    measurements = [
        lib.measurement(CATEGORY, "css.errors.count", value_numeric=total_err),
        lib.measurement(CATEGORY, "css.warnings.count", value_numeric=total_warn),
    ]
    status = "error" if total_err else ("warning" if total_warn else "ok")
    return lib.result(
        target_url,
        TOOL,
        status,
        source_url=ENDPOINT,
        measurements=measurements,
        observations=observations,
        raw_json={"stylesheets": raw_sheets, "path": path},
    )
