#!/usr/bin/env python3
"""Lighthouse validator: runs the local Lighthouse CLI via npx and records
category scores, key timings and failed audits.

If the CLI (or a usable Chrome) is unavailable the validator raises ToolMissing
so the run records an `unavailable` tool_result rather than failing.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess

import lib

TOOL = "lighthouse"

# Lighthouse category id -> (our metric, ledger category)
CATEGORY_METRICS = {
    "performance": ("lighthouse.performance.score", "performance"),
    "accessibility": ("lighthouse.accessibility.score", "accessibility"),
    "best-practices": ("lighthouse.best_practices.score", "best_practices"),
    "seo": ("lighthouse.seo.score", "seo"),
}

# audit id -> (metric, ledger category, unit hint)
TIMING_AUDITS = {
    "largest-contentful-paint": ("lighthouse.lcp_ms", "performance"),
    "cumulative-layout-shift": ("lighthouse.cls", "performance"),
    "total-blocking-time": ("lighthouse.tbt_ms", "performance"),
    "speed-index": ("lighthouse.speed_index_ms", "performance"),
}

# Declarative evidence extraction for the diagnostic / insight audits. Field
# paths confirmed against Lighthouse 13.3.0.
#   shape: items  -> details.items[] rows (url/value fields)
#          node   -> details.items[].node.* (+ item-level scalar fields)
#          nested -> details.items[outer].items[] rows (e.g. forced-reflow)
#   always: emit an observation even when the audit "passes" (insight audits
#           often have score None) so the engineer always sees the detail.
AUDIT_EXTRACT = {
    "mainthread-work-breakdown": {
        "shape": "items",
        "area": "performance",
        "fields": ["groupLabel", "duration"],
        "always": True,
        "culprit": lambda i: f"{i.get('groupLabel')} {round(i.get('duration', 0))}ms",
    },
    "render-blocking-insight": {
        "shape": "items",
        "area": "performance",
        "fields": ["url", "totalBytes", "wastedMs"],
        "always": True,
        "culprit": lambda i: f"{i.get('url')} (~{round(i.get('wastedMs', 0))}ms)",
    },
    "cache-insight": {
        "shape": "items",
        "area": "performance",
        "fields": ["url", "cacheLifetimeMs", "totalBytes", "wastedBytes"],
        "always": True,
        "culprit": lambda i: i.get("url"),
    },
    "long-tasks": {
        "shape": "items",
        "area": "performance",
        "fields": ["url", "duration", "startTime"],
        "always": True,
        "culprit": lambda i: f"{i.get('url')} ({round(i.get('duration', 0))}ms)",
    },
    "bootup-time": {
        "shape": "items",
        "area": "performance",
        "fields": ["url", "total", "scripting", "scriptParseCompile"],
        "always": True,
        "culprit": lambda i: f"{i.get('url')} ({round(i.get('total', 0))}ms)",
    },
    "layout-shifts": {
        "shape": "node",
        "area": "performance",
        "node_fields": ["selector", "nodeLabel", "snippet"],
        "item_fields": ["score"],
        "always": True,
        "culprit": lambda i: (i.get("node") or {}).get("selector"),
    },
    "label-content-name-mismatch": {
        "shape": "node",
        "area": "accessibility",
        "node_fields": ["selector", "nodeLabel", "snippet", "explanation"],
        "always": False,
        "culprit": lambda i: (i.get("node") or {}).get("selector"),
    },
    "bf-cache": {
        "shape": "items",
        "area": "performance",
        "fields": ["reason", "failureType", "protocolReason"],
        "always": False,
        "culprit": lambda i: i.get("reason"),
    },
    "forced-reflow-insight": {
        "shape": "nested",
        "area": "performance",
        "fields": ["source.value", "reflowTime"],
        "always": True,
        "culprit": lambda i: f"{_dig(i, 'source.value')} ({round(i.get('reflowTime', 0))}ms)",
    },
}


def _dig(obj, dotted):
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _audit_evidence_rows(audit, spec, source_url):
    """Build evidence rows from one audit's details per its shape spec."""
    details = audit.get("details") or {}
    items = details.get("items") or []
    rows = []
    if spec["shape"] == "nested":
        inner = (items[0].get("items") if items and isinstance(items[0], dict) else None) or []
        for it in inner[:25]:
            vals = {f: _dig(it, f) for f in spec["fields"]}
            label = lib.ascii_norm(str(vals.get("source.value") or "reflow"))
            rows.append(
                lib.evidence(
                    "audit",
                    label,
                    "; ".join(f"{k}={v}" for k, v in vals.items() if v is not None),
                    source_url=source_url,
                )
            )
    elif spec["shape"] == "node":
        for it in items[:25]:
            node = it.get("node") or {}
            parts = [f"{f}={node.get(f)}" for f in spec.get("node_fields", []) if node.get(f)]
            parts += [
                f"{f}={it.get(f)}" for f in spec.get("item_fields", []) if it.get(f) is not None
            ]
            sel = lib.ascii_norm(str(node.get("selector") or node.get("nodeLabel") or "node"))
            rows.append(
                lib.evidence(
                    "node",
                    sel,
                    lib.ascii_norm("; ".join(parts))[:300],
                    excerpt=lib.ascii_norm(node.get("snippet")),
                    source_url=source_url,
                )
            )
    else:  # items
        for it in items[:25]:
            parts = [f"{f}={it.get(f)}" for f in spec["fields"] if it.get(f) is not None]
            label = lib.ascii_norm(
                str(it.get("url") or it.get("groupLabel") or it.get("reason") or "item")
            )
            rows.append(
                lib.evidence(
                    "audit",
                    label[:120],
                    lib.ascii_norm("; ".join(parts))[:300],
                    source_url=source_url,
                )
            )
    return rows


def _chrome_path():
    for c in (
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
    ):
        if os.path.exists(c):
            return c
    return None


def _invoke(url, cfg):
    if shutil.which("npx") is None:
        raise lib.ToolMissing("npx not on PATH")
    cmd = [
        "npx",
        "--no-install",
        "lighthouse",
        url,
        "--output=json",
        "--output-path=stdout",
        "--quiet",
        "--only-categories=performance,accessibility,best-practices,seo",
        "--chrome-flags=--headless --no-sandbox --disable-gpu",
    ]
    env = dict(os.environ)
    chrome = _chrome_path()
    if chrome:
        env["CHROME_PATH"] = chrome
    timeout = float(cfg.network.get("lighthouse_timeout_seconds", 120))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    except FileNotFoundError as e:
        raise lib.ToolMissing(f"lighthouse CLI not runnable: {e}") from e
    except subprocess.TimeoutExpired:
        raise lib.ToolMissing(f"lighthouse timed out after {timeout}s") from None
    out = proc.stdout or ""
    start = out.find("{")
    if start < 0:
        raise lib.ToolMissing(
            f"lighthouse produced no JSON (exit {proc.returncode}): {(proc.stderr or '')[-300:]}"
        )
    return json.loads(out[start:])


def run(target_url, cfg, http):
    data = _invoke(target_url, cfg)
    version = data.get("lighthouseVersion")
    audits = data.get("audits", {})
    path = lib.path_of(target_url)

    measurements = []
    observations = []

    for cat_id, (metric, category) in CATEGORY_METRICS.items():
        cat = data.get("categories", {}).get(cat_id)
        if not cat or cat.get("score") is None:
            continue
        score = round(cat["score"] * 100)
        measurements.append(
            lib.measurement(category, metric, value_numeric=score, normalised_score=score)
        )

    for audit_id, (metric, _category) in TIMING_AUDITS.items():
        a = audits.get(audit_id)
        if not a or a.get("numericValue") is None:
            continue
        val = a["numericValue"]
        # cls is a ratio; the timings are milliseconds
        val = round(val, 3) if audit_id == "cumulative-layout-shift" else round(val, 1)
        measurements.append(
            lib.measurement(
                "performance",
                metric,
                value_numeric=val,
                value_text=lib.ascii_norm(a.get("displayValue")),
            )
        )

    tbw = audits.get("total-byte-weight", {})
    if tbw.get("numericValue") is not None:
        measurements.append(
            lib.measurement(
                "performance",
                "lighthouse.total_page_weight_bytes",
                value_numeric=round(tbw["numericValue"]),
            )
        )
    netreq = audits.get("network-requests", {})
    items = (netreq.get("details") or {}).get("items")
    if isinstance(items, list):
        measurements.append(
            lib.measurement("performance", "lighthouse.request_count", value_numeric=len(items))
        )

    # accessibility "second lens" - discrete axe-category metrics from the bundled
    # axe-core audits (kept separate from lighthouse.accessibility.score). These
    # are metrics only; no new actions are minted here (label-content-name-mismatch
    # already has its own action via the AUDIT_EXTRACT/observation path) to avoid
    # duplicating the same finding.
    def _violations(audit_id):
        a = audits.get(audit_id) or {}
        return len((a.get("details") or {}).get("items") or [])

    def _passed(audit_id):
        a = audits.get(audit_id)
        return None if not a or a.get("score") is None else (a["score"] >= 1)

    for audit_id, leaf in [
        ("color-contrast", "color_contrast"),
        ("heading-order", "heading_order"),
        ("label", "label"),
        ("image-alt", "image_alt"),
    ]:
        p = _passed(audit_id)
        if p is not None:
            measurements.append(
                lib.measurement("accessibility", f"accessibility.{leaf}.pass", value_bool=p)
            )
    if audits.get("color-contrast"):
        measurements.append(
            lib.measurement(
                "accessibility",
                "accessibility.color_contrast.violations",
                value_numeric=_violations("color-contrast"),
            )
        )
    aria_violations = sum(_violations(aid) for aid in audits if aid.startswith("aria-"))
    if any(aid.startswith("aria-") for aid in audits):
        measurements.append(
            lib.measurement(
                "accessibility", "accessibility.aria.violations", value_numeric=aria_violations
            )
        )

    # rich diagnostic / insight audits -> observation + detailed evidence rows
    for audit_id, spec in AUDIT_EXTRACT.items():
        a = audits.get(audit_id)
        if not a:
            continue
        score = a.get("score")
        if not spec["always"] and (score is None or score >= 1):
            continue
        ev_rows = _audit_evidence_rows(a, spec, target_url)
        culprit = None
        items = (a.get("details") or {}).get("items") or []
        if items:
            first = items[0]
            if spec["shape"] == "nested":
                inner = (first.get("items") if isinstance(first, dict) else None) or []
                first = inner[0] if inner else {}
            try:
                culprit = spec.get("culprit", lambda i: None)(first)
            except Exception:
                culprit = None
        title = a.get("title", audit_id)
        msg = a.get("displayValue") or a.get("description", "")
        if culprit:
            msg = f"{title} on {path}: {lib.ascii_norm(str(culprit))}. {msg}"
        if score is None:
            severity = "info"
        elif score < 0.5:
            severity = "error"
        elif score < 1:
            severity = "warning"
        else:
            severity = "info"
        observations.append(
            lib.observation(
                metric="lighthouse.performance.score"
                if spec["area"] == "performance"
                else "lighthouse.accessibility.score",
                severity=severity,
                observation_type="audit",
                code=audit_id,
                title=title,
                message=lib.ascii_norm(msg),
                url=target_url,
                fingerprint=f"lighthouse:{audit_id}:{path}",
                evidence=ev_rows
                or [
                    lib.evidence(
                        "audit",
                        "Score",
                        str(score),
                        excerpt=a.get("displayValue"),
                        source_url=target_url,
                    )
                ],
            )
        )

    # remaining failed audits not covered above -> observations (fallback)
    for audit_id, a in audits.items():
        if audit_id in AUDIT_EXTRACT:
            continue
        score = a.get("score")
        if score is None or score >= 1:
            continue
        if a.get("scoreDisplayMode") in ("notApplicable", "informative", "manual"):
            continue
        cat = _audit_category(data, audit_id)
        observations.append(
            lib.observation(
                metric=CATEGORY_METRICS.get(cat, (f"lighthouse.{cat}.score",))[0]
                if cat
                else "lighthouse.performance.score",
                severity="warning" if score >= 0.5 else "error",
                observation_type="audit",
                code=audit_id,
                title=a.get("title", audit_id),
                message=a.get("description", ""),
                url=target_url,
                fingerprint=f"lighthouse:{audit_id}:{path}",
                evidence=[
                    lib.evidence(
                        "audit",
                        "Score",
                        str(round(score, 2)),
                        excerpt=a.get("displayValue"),
                        source_url=target_url,
                    )
                ],
            )
        )

    raw = {
        "lighthouseVersion": version,
        "categories": {
            k: (v.get("score") if v else None) for k, v in data.get("categories", {}).items()
        },
        "finalUrl": data.get("finalUrl") or data.get("finalDisplayedUrl"),
    }
    return lib.result(
        target_url,
        TOOL,
        "ok",
        tool_version=version,
        measurements=measurements,
        observations=observations,
        raw_json=raw,
    )


def _audit_category(data, audit_id):
    """Find which category an audit belongs to (for metric attribution)."""
    for cat_id, cat in data.get("categories", {}).items():
        for ref in cat.get("auditRefs", []):
            if ref.get("id") == audit_id:
                return cat_id
    return None
