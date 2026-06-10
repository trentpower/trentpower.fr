#!/usr/bin/env python3
"""Triage / Action Register - the V2 decision layer.

Derives a focused list of actions from the run's metrics and observations AFTER
comparison has annotated them. Raw observations are never mutated; interpreted
severity and the decision fields live only on `actions` rows.

Design choices (deliberately conservative):
- Only significant metric regressions and a small set of known observation types
  become actions. Everything else stays in the raw evidence layer.
- Known validator noise (e.g. Jigsaw rejecting modern CSS) is recorded as a
  `known_noise` action so it stays visible but visually subordinate - never as an
  urgent finding.
- Action status carries across runs by a stable action_key; the operator can
  override status via `action_overrides` in the gitignored config.local.yml.
"""

from __future__ import annotations

import lib

# --- queries (reuse compare's path/tool joins) ------------------------------
_METRIC_SQL = """
    SELECT m.metric, m.category, m.value_numeric, m.value_text, m.grade,
           m.previous_value_numeric, m.previous_value_text, m.delta_numeric,
           m.direction, m.comparison_mode, m.status,
           COALESCE(t.path, '(site)') AS path, tr.tool AS tool
    FROM metrics m
    LEFT JOIN targets t ON t.id = m.target_id
    JOIN tool_results tr ON tr.id = m.tool_result_id
    WHERE m.run_id = ?
"""

_OBS_SQL = """
    SELECT o.id, o.severity, o.observation_type, o.code, o.title, o.message,
           o.fingerprint, o.status_vs_previous,
           COALESCE(t.path, '(site)') AS path, tr.tool AS tool,
           m.metric AS metric, m.category AS category
    FROM observations o
    LEFT JOIN targets t ON t.id = o.target_id
    JOIN metrics m ON m.id = o.metric_id
    JOIN tool_results tr ON tr.id = m.tool_result_id
    WHERE o.run_id = ?
"""

AREA_BY_TOOL = {
    "css_w3c": "css",
    "html_w3c": "html",
    "lighthouse": "performance",
    "links": "links",
    "privacy": "privacy",
    "headers": "security",
    "metadata": "metadata",
    "structured_data": "metadata",
    "trust_files": "trust",
    "availability": "performance",
}

# --- default rules (config can extend/override by id) ------------------------
# Noise: matched observations become subordinate known_noise actions. Specific
# property names are used (not a broad "doesn't exist") to avoid hiding real typos.
DEFAULT_NOISE_RULES = [
    {
        "id": "css_modern_mask",
        "tool": "css_w3c",
        "title_contains": "mask-image",
        "interpreted_severity": "info",
        "actionability": "low",
        "confidence": "high",
        "reason": "Modern CSS property not recognised by W3C Jigsaw css3 profile.",
    },
    {
        "id": "css_modern_pointer",
        "tool": "css_w3c",
        "title_contains": "pointer-events",
        "interpreted_severity": "info",
        "actionability": "low",
        "confidence": "high",
        "reason": "Validator profile limitation (pointer-events).",
    },
    {
        "id": "css_modern_anim",
        "tool": "css_w3c",
        "title_contains": "animation-timeline",
        "interpreted_severity": "info",
        "actionability": "low",
        "confidence": "high",
        "reason": "Modern CSS not recognised by W3C Jigsaw.",
    },
    {
        "id": "css_modern_textrender",
        "tool": "css_w3c",
        "title_contains": "text-rendering",
        "interpreted_severity": "info",
        "actionability": "low",
        "confidence": "high",
        "reason": "Modern CSS not recognised by W3C Jigsaw.",
    },
    {
        "id": "css_variables",
        "tool": "css_w3c",
        "title_contains": "variables are currently not",
        "interpreted_severity": "info",
        "actionability": "low",
        "confidence": "high",
        "reason": "Known W3C CSS validator limitation (CSS variables not statically checked).",
    },
    {
        "id": "lh_bf_cache",
        "tool": "lighthouse",
        "code": "bf-cache",
        "interpreted_severity": "info",
        "actionability": "low",
        "confidence": "medium",
        "reason": "Back/forward-cache eligibility is informational for a static site.",
    },
]

# Action rules. Thresholds are intentionally conservative so minor fluctuations
# (e.g. a few ms of response time, a 1-2 point Lighthouse wobble) do not surface.
DEFAULT_ACTION_RULES = [
    # metric-scope: drop tiny response-time changes outright
    {
        "id": "response_ms_noise",
        "scope": "metric",
        "drop": True,
        "when": {"metric": "availability.response_ms", "delta_below": 50},
    },
    {
        "id": "perf_regression",
        "scope": "metric",
        "when": {
            "tool": "lighthouse",
            "metric": "lighthouse.performance.score",
            "direction": "declined",
            "delta_at_least": 10,
        },
        "impact": "high",
        "confidence": "high",
        "actionability": "high",
        "suggested_area": "performance",
        "interpreted_severity": "high",
        "recommended_action": (
            "Investigate the regressed page's Total Blocking Time, "
            "main-thread work and forced-reflow audits; defer "
            "non-essential JavaScript and reduce layout reads after "
            "DOM mutation."
        ),
    },
    {
        "id": "tbt_regression",
        "scope": "metric",
        "when": {
            "tool": "lighthouse",
            "metric": "lighthouse.tbt_ms",
            "direction": "declined",
            "delta_at_least": 200,
        },
        "impact": "medium",
        "confidence": "high",
        "actionability": "high",
        "suggested_area": "performance",
        "interpreted_severity": "medium",
        "recommended_action": (
            "Reduce main-thread blocking: inspect long tasks and "
            "script bootstrap on the affected page."
        ),
    },
    {
        "id": "broken_links",
        "scope": "metric",
        "when": {"metric": "links.internal_broken.count", "value_at_least": 1},
        "impact": "high",
        "confidence": "high",
        "actionability": "high",
        "suggested_area": "links",
        "interpreted_severity": "high",
        "recommended_action": "Fix or remove broken internal links before release.",
    },
    {
        "id": "html_errors",
        "scope": "metric",
        "when": {"metric": "html.errors.count", "value_at_least": 1},
        "impact": "medium",
        "confidence": "high",
        "actionability": "high",
        "suggested_area": "html",
        "interpreted_severity": "medium",
        "recommended_action": "Resolve W3C HTML validation errors on the affected page.",
    },
    {
        "id": "observatory_regression",
        "scope": "metric",
        "when": {"metric": "security.observatory.grade", "direction": "declined"},
        "impact": "high",
        "confidence": "high",
        "actionability": "medium",
        "suggested_area": "security",
        "interpreted_severity": "high",
        "recommended_action": (
            "Security headers regressed - review CSP, HSTS and permissions policy."
        ),
    },
    {
        "id": "ssl_regression",
        "scope": "metric",
        "when": {"metric": "tls.ssl_labs.grade", "direction": "declined"},
        "impact": "high",
        "confidence": "high",
        "actionability": "medium",
        "suggested_area": "security",
        "interpreted_severity": "high",
        "recommended_action": "TLS configuration regressed - review protocols and ciphers.",
    },
    # observation-scope
    {
        "id": "html_heading",
        "scope": "observation",
        "when": {"tool": "html_w3c", "title_contains": "lacks heading"},
        "impact": "medium",
        "confidence": "medium",
        "actionability": "high",
        "suggested_area": "html",
        "interpreted_severity": "medium",
        "recommended_action": "Add a top-level heading to the flagged article/section landmark.",
    },
    {
        "id": "aria_hidden",
        "scope": "observation",
        "when": {"tool": "html_w3c", "title_contains": "aria-hidden"},
        "impact": "low",
        "confidence": "medium",
        "actionability": "high",
        "suggested_area": "accessibility",
        "interpreted_severity": "low",
        "recommended_action": "Remove redundant aria-hidden from an already-hidden element.",
    },
    {
        "id": "label_mismatch",
        "scope": "observation",
        "when": {"tool": "lighthouse", "code": "label-content-name-mismatch"},
        "impact": "medium",
        "confidence": "medium",
        "actionability": "medium",
        "suggested_area": "accessibility",
        "interpreted_severity": "medium",
        "recommended_action": (
            "Make each control's visible label match its accessible name (aria-label / text)."
        ),
    },
    {
        "id": "mirror_hash_mismatch",
        "scope": "observation",
        "when": {"tool": "content_integrity", "code": "MIRROR_HASH_MISMATCH"},
        "impact": "high",
        "confidence": "high",
        "actionability": "high",
        "suggested_area": "trust",
        "interpreted_severity": "high",
        "recommended_action": (
            "Source mirror no longer matches the integrity manifest "
            "- regenerate mirrors and re-sign the release."
        ),
    },
    {
        "id": "release_sig_invalid",
        "scope": "observation",
        "when": {"tool": "release_archive", "code": "RELEASE_SIG_INVALID"},
        "impact": "high",
        "confidence": "high",
        "actionability": "high",
        "suggested_area": "trust",
        "interpreted_severity": "high",
        "recommended_action": "release.json signature failed to verify - re-sign the release.",
    },
    {
        "id": "testresults_absent",
        "scope": "observation",
        "when": {"tool": "release_archive", "code": "TESTRESULTS_ABSENT"},
        "impact": "low",
        "confidence": "high",
        "actionability": "high",
        "suggested_area": "release_process",
        "interpreted_severity": "low",
        "recommended_action": (
            "Generate a signed TESTRESULTS.txt for this edition and "
            "publish it into the release folder + manifest."
        ),
    },
    # Phase 3 - high-confidence site-specific regressions
    {
        "id": "csp_unsafe_inline",
        "scope": "observation",
        "when": {"tool": "csp_quality", "code": "CSP_NO_UNSAFE_INLINE"},
        "impact": "high",
        "confidence": "high",
        "actionability": "high",
        "suggested_area": "security",
        "interpreted_severity": "high",
        "recommended_action": "Remove 'unsafe-inline' from the CSP; use hashes/nonces.",
    },
    {
        "id": "csp_unsafe_eval",
        "scope": "observation",
        "when": {"tool": "csp_quality", "code": "CSP_NO_UNSAFE_EVAL"},
        "impact": "high",
        "confidence": "high",
        "actionability": "high",
        "suggested_area": "security",
        "interpreted_severity": "high",
        "recommended_action": "Remove 'unsafe-eval' from the CSP.",
    },
    {
        "id": "hreflang_canonical_leak",
        "scope": "observation",
        "when": {"tool": "hreflang", "code": "CANONICAL_ROOT_LEAK"},
        "impact": "high",
        "confidence": "high",
        "actionability": "high",
        "suggested_area": "metadata",
        "interpreted_severity": "high",
        "recommended_action": "Set the sub-edition canonical to itself, not root.",
    },
    {
        "id": "hreflang_not_reciprocal",
        "scope": "observation",
        "when": {"tool": "hreflang", "code": "HREFLANG_NOT_RECIPROCAL"},
        "impact": "medium",
        "confidence": "high",
        "actionability": "high",
        "suggested_area": "metadata",
        "interpreted_severity": "medium",
        "recommended_action": "Make hreflang alternates reciprocal between editions.",
    },
    {
        "id": "sitemap_missing_target",
        "scope": "observation",
        "when": {"tool": "seo_semantics", "code": "TARGET_NOT_IN_SITEMAP"},
        "impact": "medium",
        "confidence": "high",
        "actionability": "high",
        "suggested_area": "metadata",
        "interpreted_severity": "medium",
        "recommended_action": "Add the missing target URL(s) to sitemap.xml.",
    },
    {
        "id": "sw_edition_stale",
        "scope": "observation",
        "when": {"tool": "service_worker", "code": "SW_EDITION_STALE"},
        "impact": "high",
        "confidence": "high",
        "actionability": "high",
        "suggested_area": "service_worker",
        "interpreted_severity": "high",
        "recommended_action": "Bump the service-worker cache version to the current edition.",
    },
    {
        "id": "sw_never_cache",
        "scope": "observation",
        "when": {"tool": "service_worker", "code": "NEVER_CACHE_INCOMPLETE"},
        "impact": "high",
        "confidence": "high",
        "actionability": "high",
        "suggested_area": "service_worker",
        "interpreted_severity": "high",
        "recommended_action": "Add the missing sensitive path(s) to the SW NEVER_CACHE list.",
    },
    {
        "id": "edition_inconsistent",
        "scope": "observation",
        "when": {"tool": "content_anchors", "code": "EDITION_INCONSISTENT"},
        "impact": "high",
        "confidence": "high",
        "actionability": "high",
        "suggested_area": "metadata",
        "interpreted_severity": "high",
        "recommended_action": "Reconcile the edition string across meta/footer/body and site-metadata.",
    },
    {
        "id": "fr_disclosure_missing",
        "scope": "observation",
        "when": {"tool": "content_anchors", "code": "FR_DISCLOSURE_MISSING"},
        "impact": "medium",
        "confidence": "high",
        "actionability": "high",
        "suggested_area": "metadata",
        "interpreted_severity": "medium",
        "recommended_action": "Restore the French machine-translation disclosure on /fr/.",
    },
    {
        "id": "runtime_third_party",
        "scope": "observation",
        "when": {"tool": "runtime_privacy", "code": "RUNTIME_THIRD_PARTY"},
        "impact": "high",
        "confidence": "high",
        "actionability": "high",
        "suggested_area": "privacy",
        "interpreted_severity": "high",
        "recommended_action": "Remove the third-party request; keep the site first-party only.",
    },
    {
        "id": "unapproved_storage_key",
        "scope": "observation",
        "when": {"tool": "runtime_privacy", "code": "UNAPPROVED_STORAGE_KEY"},
        "impact": "high",
        "confidence": "high",
        "actionability": "high",
        "suggested_area": "privacy",
        "interpreted_severity": "high",
        "recommended_action": "Remove or add to the approved allowlist the unexpected storage key.",
    },
    {
        "id": "offline_render_failed",
        "scope": "observation",
        "when": {"tool": "offline", "code": "OFFLINE_RENDER_FAILED"},
        "impact": "high",
        "confidence": "high",
        "actionability": "high",
        "suggested_area": "service_worker",
        "interpreted_severity": "high",
        "recommended_action": "Service worker activated but offline render failed - check the precache list.",
    },
]


# --- predicate matching ------------------------------------------------------
def _match(when, row):
    """AND-semantics predicate. row is a plain dict. Unknown row keys -> no match."""
    for k, v in when.items():
        if k == "tool" and row.get("tool") != v:
            return False
        if k == "metric" and row.get("metric") != v:
            return False
        if k == "category" and row.get("category") != v:
            return False
        if k == "direction" and row.get("direction") != v:
            return False
        if k == "status_vs_previous" and row.get("status_vs_previous") != v:
            return False
        if k == "severity" and row.get("severity") != v:
            return False
        if k == "code" and row.get("code") != v:
            return False
        if k == "code_in" and row.get("code") not in v:
            return False
        if k == "title_contains" and v.lower() not in (row.get("title") or "").lower():
            return False
        if k == "delta_at_least":
            d = row.get("delta_numeric")
            if d is None or abs(d) < v:
                return False
        if k == "delta_below":
            d = row.get("delta_numeric")
            if d is None or abs(d) >= v:
                return False
        if k == "value_at_least":
            x = row.get("value_numeric")
            if x is None or x < v:
                return False
        if k == "value_below":
            x = row.get("value_numeric")
            if x is None or x >= v:
                return False
    return True


def _merge_rules(defaults, extra):
    """Merge config rules over code defaults, keyed by id (config replaces;
    new ids append; order: defaults first then new)."""
    by_id = {r["id"]: dict(r) for r in defaults}
    appended = []
    for r in extra or []:
        rid = r.get("id")
        if rid in by_id:
            by_id[rid] = dict(r)
        else:
            appended.append(dict(r))
    return list(by_id.values()) + appended


def _fmt(v):
    if v is None:
        return "-"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


# --- builders ----------------------------------------------------------------
def _metric_actions(rows, rules):
    drops = [r for r in rules if r.get("scope") == "metric" and r.get("drop")]
    metric_rules = [r for r in rules if r.get("scope") == "metric" and not r.get("drop")]
    out = []
    for row in rows:
        d = dict(row)
        if any(_match(r["when"], d) for r in drops):
            continue
        for rule in metric_rules:
            if not _match(rule["when"], d):
                continue
            cur = d.get("value_text") or _fmt(d.get("value_numeric"))
            prev = d.get("previous_value_text") or _fmt(d.get("previous_value_numeric"))
            rationale = f"{d['metric']} {prev} -> {cur}"
            if d.get("delta_numeric") is not None:
                rationale += f" (delta {_fmt(d['delta_numeric'])})"
            out.append(
                {
                    "target_path": d["path"],
                    "category": d["category"],
                    "source_tool": d["tool"],
                    "related_metric": d["metric"],
                    "observation_fingerprint": None,
                    "action_key": _key(d["path"], d["tool"], d["metric"], "", rule["id"]),
                    "title": f"{d['metric']} on {d['path']}",
                    "raw_severity": None,
                    "interpreted_severity": rule.get("interpreted_severity"),
                    "confidence": rule.get("confidence"),
                    "actionability": rule.get("actionability"),
                    "impact": rule.get("impact"),
                    "suggested_area": rule.get("suggested_area"),
                    "recommended_action": rule.get("recommended_action"),
                    "rationale": rationale,
                    "_base_status": "open",
                }
            )
    return out


def _observation_actions(rows, noise_rules, action_rules):
    obs_rules = [r for r in action_rules if r.get("scope") == "observation"]
    out = []
    for row in rows:
        d = dict(row)
        noise = next((r for r in noise_rules if _match(_noise_when(r), d)), None)
        if noise:
            out.append(
                {
                    "target_path": d["path"],
                    "category": d["category"],
                    "source_tool": d["tool"],
                    "related_metric": d["metric"],
                    "observation_fingerprint": d["fingerprint"],
                    "action_key": _key(
                        d["path"], d["tool"], d["metric"], d["fingerprint"], noise["id"]
                    ),
                    "title": d.get("title") or d["metric"],
                    "raw_severity": d.get("severity"),
                    "interpreted_severity": noise.get("interpreted_severity", "info"),
                    "confidence": noise.get("confidence", "high"),
                    "actionability": noise.get("actionability", "low"),
                    "impact": "low",
                    "suggested_area": AREA_BY_TOOL.get(d["tool"], "release_process"),
                    "recommended_action": noise.get("reason", "Known validator noise."),
                    "rationale": noise.get("reason", "Known validator noise."),
                    "_base_status": "known_noise",
                }
            )
            continue
        for rule in obs_rules:
            if not _match(rule["when"], d):
                continue
            out.append(
                {
                    "target_path": d["path"],
                    "category": d["category"],
                    "source_tool": d["tool"],
                    "related_metric": d["metric"],
                    "observation_fingerprint": d["fingerprint"],
                    "action_key": _key(
                        d["path"], d["tool"], d["metric"], d["fingerprint"], rule["id"]
                    ),
                    "title": d.get("title") or d["metric"],
                    "raw_severity": d.get("severity"),
                    "interpreted_severity": rule.get("interpreted_severity"),
                    "confidence": rule.get("confidence"),
                    "actionability": rule.get("actionability"),
                    "impact": rule.get("impact"),
                    "suggested_area": rule.get("suggested_area"),
                    "recommended_action": rule.get("recommended_action"),
                    "rationale": (d.get("message") or d.get("title") or "")[:300],
                    "_base_status": "open",
                }
            )
    return out


def _noise_when(rule):
    """A noise rule's match predicate is its tool/code/title_contains keys."""
    return {k: rule[k] for k in ("tool", "code", "code_in", "title_contains") if k in rule}


def _key(path, tool, metric, fingerprint, rule_id):
    raw = f"{path}|{tool}|{metric}|{fingerprint}|{rule_id}"
    return lib.sha256_bytes(raw.encode("utf-8"))


# --- entry point -------------------------------------------------------------
def run(conn, cfg, run_id, prev_run_id):
    """Derive and persist the Action Register for run_id. Idempotent."""
    import db

    noise_rules = _merge_rules(DEFAULT_NOISE_RULES, cfg.raw.get("noise_rules"))
    action_rules = _merge_rules(DEFAULT_ACTION_RULES, cfg.raw.get("action_rules"))

    metric_rows = conn.execute(_METRIC_SQL, (run_id,)).fetchall()
    obs_rows = conn.execute(_OBS_SQL, (run_id,)).fetchall()

    candidates = _metric_actions(metric_rows, action_rules)
    candidates += _observation_actions(obs_rows, noise_rules, action_rules)

    # dedup by action_key (first wins)
    seen, actions = set(), []
    for a in candidates:
        if a["action_key"] in seen:
            continue
        seen.add(a["action_key"])
        actions.append(a)

    # status: override > carryover(manual) > base
    overrides = cfg.raw.get("action_overrides") or {}
    carried = db.previous_actions(conn, prev_run_id)
    for a in actions:
        key = a["action_key"]
        base = a.pop("_base_status")
        if key in overrides:
            a["status"] = overrides[key]
        elif carried.get(key) in ("acknowledged", "ignored", "fixed"):
            a["status"] = carried[key]
        else:
            a["status"] = base

    db.replace_actions(conn, run_id, actions)
    return actions
