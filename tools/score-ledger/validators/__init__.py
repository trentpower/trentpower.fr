#!/usr/bin/env python3
"""Validator registry and the robust dispatch wrapper.

Each validator module exposes:
    TOOL = "<stable-name>"
    def run(target_url, cfg, http) -> dict   # a lib.result(...)-shaped dict

dispatch() guarantees a validator can never abort a run: any failure becomes an
unavailable/error/manual standard-result that is itself recorded as evidence.
"""

from __future__ import annotations

import time
import traceback
from urllib.parse import urlsplit

import lib
import requests

from . import (
    availability,
    content_anchors,
    content_integrity,
    csp_quality,
    css_w3c,
    headers,
    hreflang,
    html_w3c,
    lighthouse,
    links,
    manual,
    metadata,
    observatory,
    offline,
    pagespeed,
    privacy,
    release_archive,
    runtime_privacy,
    seo_semantics,
    service_worker,
    ssl_labs,
    structured_data,
    trust_files,
    webpagetest,
)

# `manual` and the external integrations are site-level (one call per run,
# target_id NULL) so they are intentionally NOT in REGISTRY / CHECK_TO_TOOL;
# the orchestrator calls site_level_results(cfg, http).

# integration key (config "integrations") -> real validator module
SITE_INTEGRATIONS = {
    "mozilla_observatory": observatory,
    "ssl_labs": ssl_labs,
    "pagespeed": pagespeed,
    "webpagetest": webpagetest,
}

REGISTRY = {
    availability.TOOL: availability,
    headers.TOOL: headers,
    metadata.TOOL: metadata,
    structured_data.TOOL: structured_data,
    trust_files.TOOL: trust_files,
    privacy.TOOL: privacy,
    links.TOOL: links,
    lighthouse.TOOL: lighthouse,
    html_w3c.TOOL: html_w3c,
    css_w3c.TOOL: css_w3c,
    content_integrity.TOOL: content_integrity,
    release_archive.TOOL: release_archive,
    csp_quality.TOOL: csp_quality,
    seo_semantics.TOOL: seo_semantics,
    hreflang.TOOL: hreflang,
    service_worker.TOOL: service_worker,
    content_anchors.TOOL: content_anchors,
}

# Browser-based validators (Playwright) run in a separate sequential pass, never
# concurrent with Lighthouse. Not in REGISTRY.
BROWSER_REGISTRY = {
    runtime_privacy.TOOL: runtime_privacy,
    offline.TOOL: offline,
}
BROWSER_CHECK_TO_TOOL = {
    "runtime_privacy": runtime_privacy.TOOL,
    "offline": offline.TOOL,
}

# Maps a config "checks" key to a validator TOOL name.
CHECK_TO_TOOL = {
    "availability": availability.TOOL,
    "headers": headers.TOOL,
    "metadata": metadata.TOOL,
    "structured_data": structured_data.TOOL,
    "trust_files": trust_files.TOOL,
    "privacy": privacy.TOOL,
    "links": links.TOOL,
    "lighthouse": lighthouse.TOOL,
    "html_w3c": html_w3c.TOOL,
    "css_w3c": css_w3c.TOOL,
    "content_integrity": content_integrity.TOOL,
    "release_archive": release_archive.TOOL,
    "csp_quality": csp_quality.TOOL,
    "seo_semantics": seo_semantics.TOOL,
    "hreflang": hreflang.TOOL,
    "service_worker": service_worker.TOOL,
    "content_anchors": content_anchors.TOOL,
}


def enabled(cfg):
    """Ordered list of validator TOOL names enabled in config and implemented."""
    out = []
    for check, tool in CHECK_TO_TOOL.items():
        if cfg.checks.get(check) and tool in REGISTRY:
            out.append(tool)
    return out


def _stamp(res, started, started_iso):
    res["started_at"] = started_iso
    res["finished_at"] = lib.now_utc_iso()
    res["duration_ms"] = int((time.monotonic() - started) * 1000)
    return res


def dispatch(tool, target_url, cfg, http):
    """Run a validator, mapping every failure mode to a standard result."""
    mod = REGISTRY[tool]
    started = time.monotonic()
    started_iso = lib.now_utc_iso()
    try:
        res = mod.run(target_url, cfg, http)
        return _stamp(res, started, started_iso)
    except lib.NotConfigured as e:
        res = lib.result(
            target_url,
            getattr(mod, "TOOL", tool),
            "manual",
            source_url=e.source_url,
            observations=[
                lib.observation(
                    metric=f"{tool}.manual",
                    severity="info",
                    observation_type="manual",
                    code="MANUAL_CHECK",
                    title="manual check required",
                    message=str(e),
                    url=target_url,
                    fingerprint=f"{tool}:manual:{urlsplit(target_url).path}",
                )
            ],
            raw_json={"reason": str(e)},
        )
        return _stamp(res, started, started_iso)
    except (lib.ToolMissing, requests.Timeout, requests.ConnectionError) as e:
        res = lib.result(
            target_url,
            getattr(mod, "TOOL", tool),
            "unavailable",
            raw_json={"error": type(e).__name__, "detail": str(e)},
        )
        return _stamp(res, started, started_iso)
    except Exception as e:  # last resort: never crash the run
        res = lib.result(
            target_url,
            getattr(mod, "TOOL", tool),
            "error",
            observations=[
                lib.observation(
                    metric=f"{tool}.internal_error",
                    severity="error",
                    observation_type="exception",
                    code="VALIDATOR_CRASH",
                    title="validator raised an exception",
                    message=repr(e),
                    url=target_url,
                    fingerprint=f"{tool}:crash:{urlsplit(target_url).path}",
                )
            ],
            raw_json={"traceback": traceback.format_exc()},
        )
        return _stamp(res, started, started_iso)


def _dispatch_site(key, mod, site, cfg, http):
    """Run one site-level integration validator, mapping failures to a standard
    result (unavailable/error) the same way dispatch() does for per-target ones."""
    started = time.monotonic()
    started_iso = lib.now_utc_iso()
    try:
        res = mod.run(site, cfg, http)
        return _stamp(res, started, started_iso)
    except lib.NotConfigured:
        return _stamp(manual.placeholder(cfg, key), started, started_iso)
    except (lib.ToolMissing, requests.Timeout, requests.ConnectionError) as e:
        res = lib.result(
            site,
            mod.TOOL,
            "unavailable",
            source_url=manual.source_url(cfg, key),
            raw_json={"error": type(e).__name__, "detail": str(e)},
        )
        return _stamp(res, started, started_iso)
    except Exception as e:
        res = lib.result(
            site,
            mod.TOOL,
            "error",
            source_url=manual.source_url(cfg, key),
            observations=[
                lib.observation(
                    metric=f"{key}.internal_error",
                    severity="error",
                    observation_type="exception",
                    code="VALIDATOR_CRASH",
                    title="integration raised an exception",
                    message=repr(e),
                    url=site,
                    fingerprint=f"{key}:crash",
                )
            ],
            raw_json={"traceback": traceback.format_exc()},
        )
        return _stamp(res, started, started_iso)


def site_level_results(cfg, http):
    """Results for the four external integrations: the real validator when the
    integration is enabled in config, otherwise a manual placeholder."""
    site = cfg.targets[0] if cfg.targets else "https://trentpower.fr/"
    out = []
    for key, mod in SITE_INTEGRATIONS.items():
        if cfg.integrations.get(key):
            out.append(_dispatch_site(key, mod, site, cfg, http))
        else:
            out.append(_stamp(manual.placeholder(cfg, key), time.monotonic(), lib.now_utc_iso()))
    return out


# ---------------------------------------------------------------------------
# Browser pass (Playwright validators) - same exception mapping as dispatch().
# ---------------------------------------------------------------------------
def browser_enabled(cfg):
    """Browser TOOL names enabled in config (gated by checks.browser_pass)."""
    if not cfg.checks.get("browser_pass"):
        return []
    return [
        tool
        for check, tool in BROWSER_CHECK_TO_TOOL.items()
        if cfg.checks.get(check, True) and tool in BROWSER_REGISTRY
    ]


def dispatch_browser(tool, target_url, cfg):
    """Run a browser validator; map failures to unavailable/error (non-fatal)."""
    mod = BROWSER_REGISTRY[tool]
    started = time.monotonic()
    started_iso = lib.now_utc_iso()
    try:
        return _stamp(mod.run(target_url, cfg, None), started, started_iso)
    except lib.ToolMissing as e:
        return _stamp(
            lib.result(
                target_url,
                mod.TOOL,
                "unavailable",
                raw_json={"error": "ToolMissing", "detail": str(e)},
            ),
            started,
            started_iso,
        )
    except Exception as e:
        return _stamp(
            lib.result(
                target_url,
                mod.TOOL,
                "error",
                observations=[
                    lib.observation(
                        metric=f"{tool}.internal_error",
                        severity="error",
                        observation_type="exception",
                        code="VALIDATOR_CRASH",
                        title="browser validator raised an exception",
                        message=repr(e),
                        url=target_url,
                        fingerprint=f"{tool}:crash:{urlsplit(target_url).path}",
                    )
                ],
                raw_json={"traceback": traceback.format_exc()},
            ),
            started,
            started_iso,
        )
