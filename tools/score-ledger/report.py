#!/usr/bin/env python3
"""Report generation: ASCII-only Markdown and a quiet, self-contained HTML file.

No external assets, no JavaScript, no tracking. One gather() read model feeds
both renderers.
"""

from __future__ import annotations

import html
import os

import compare
import lib

# ASCII direction markers (no unicode, for portability).
DIR_MARK = {
    "improved": "[+]",
    "declined": "[-]",
    "unchanged": "[=]",
    "new": "[new]",
    "missing": "[gone]",
    "not_comparable": "[~]",
    None: "[?]",
}

CATEGORIES = [
    "availability",
    "headers",
    "metadata",
    "structured_data",
    "trust_files",
    "content_consistency",
    "privacy",
    "links",
    "performance",
    "accessibility",
    "seo",
    "security",
    "tls",
    "release",
    "service_worker",
    "html",
    "css",
]

# Per-page categories shown in the page x category matrix; site-level categories
# render under the "(site)" column.
PAGE_CATEGORIES = [
    "availability",
    "performance",
    "accessibility",
    "seo",
    "html",
    "css",
    "metadata",
    "structured_data",
    "privacy",
    "links",
    "headers",
    "content_consistency",
    "security",
    "service_worker",
]
SITE_CATEGORIES = ["security", "tls", "trust_files", "release", "service_worker"]


def _disp(metric, value, grade=None):
    """One consistent display string for a metric value, computed from the
    numeric (never Lighthouse's displayValue), so current and all baselines read
    in the same unit."""
    if grade:
        return grade
    if value is None:
        return "-"
    leaf = metric.rsplit(".", 1)[-1]
    if metric in ("lighthouse.lcp_ms", "lighthouse.speed_index_ms") or leaf in (
        "fully_loaded_ms",
        "start_render_ms",
        "speed_index_ms",
    ):
        return f"{value / 1000:.2f}s"
    if leaf.endswith("_ms") or metric.endswith(".response_ms"):
        return f"{int(round(value))} ms"
    if metric.endswith(".cls"):
        return f"{value:.3f}"
    if leaf in ("bytes_in",) or metric.endswith("_bytes"):
        return f"{value / 1024:.0f} KiB"
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}"


# Site-level external integrations, shown in their own report section.
INTEGRATION_TOOLS = ["mozilla_observatory", "ssl_labs", "pagespeed", "webpagetest"]
INTEGRATION_LABELS = {
    "mozilla_observatory": "Mozilla Observatory",
    "ssl_labs": "SSL Labs",
    "pagespeed": "PageSpeed Insights",
    "webpagetest": "WebPageTest",
}


def _short_metric(metric):
    parts = metric.split(".")
    return ".".join(parts[2:]) if len(parts) > 2 else metric


# observation fingerprint prefix per integration (observations have no metric
# name column, so guidance notes are matched by fingerprint).
FP_PREFIX = {
    "mozilla_observatory": "observatory:",
    "ssl_labs": "ssl_labs:",
    "pagespeed": "pagespeed:",
    "webpagetest": "webpagetest:",
}


def _integration_rows(data):
    """For each site-level integration: (tool, label, status, result, source_url).

    `result` is the real metric values when ok, otherwise the guidance note
    (e.g. "needs an API key"). Synthetic `.note` anchor metrics are skipped.
    """
    tr_by_tool = {tr["tool"]: tr for tr in data["tool_results"] if tr["target_id"] is None}
    rows = []
    for tool in INTEGRATION_TOOLS:
        tr = tr_by_tool.get(tool)
        if not tr:
            continue
        vals = [
            f"{_short_metric(m['metric'])}={_fmt_val(m)}"
            for m in data["metrics"]
            if m["tool"] == tool
            and m["status"] not in ("manual",)
            and not m["metric"].endswith(".note")
        ]
        result = ", ".join(vals)
        if not result:
            prefix = FP_PREFIX.get(tool, "")
            note = next(
                (
                    lib.ascii_norm(o["title"])
                    for o in data["observations"]
                    if (o["fingerprint"] or "").startswith(prefix)
                ),
                None,
            )
            result = note or "-"
        rows.append(
            (tool, INTEGRATION_LABELS.get(tool, tool), tr["status"], result, tr["source_url"])
        )
    return rows


# ---------------------------------------------------------------------------
# Read model
# ---------------------------------------------------------------------------
def _run_row(conn, run_id):
    return conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()


def gather(conn, cfg, run_id):
    run = _run_row(conn, run_id)
    prev_run_id = conn.execute(
        "SELECT id FROM runs WHERE id < ? AND status = 'finished' ORDER BY id DESC LIMIT 1",
        (run_id,),
    ).fetchone()
    prev_run_id = prev_run_id["id"] if prev_run_id else None
    prev = _run_row(conn, prev_run_id) if prev_run_id else None

    metrics = conn.execute(
        """SELECT m.*, COALESCE(t.path, '(site)') AS path, t.page_key AS page_key,
                  tr.tool AS tool, tr.status AS tool_status
           FROM metrics m
           LEFT JOIN targets t ON t.id = m.target_id
           JOIN tool_results tr ON tr.id = m.tool_result_id
           WHERE m.run_id = ? ORDER BY path, tr.tool, m.metric""",
        (run_id,),
    ).fetchall()
    observations = conn.execute(
        """SELECT o.*, COALESCE(t.path, '(site)') AS path FROM observations o
           LEFT JOIN targets t ON t.id = o.target_id
           WHERE o.run_id = ? ORDER BY o.severity, path""",
        (run_id,),
    ).fetchall()
    tool_results = conn.execute(
        """SELECT tr.*, t.path AS path FROM tool_results tr
           LEFT JOIN targets t ON t.id = tr.target_id
           WHERE tr.run_id = ? ORDER BY t.path, tr.tool""",
        (run_id,),
    ).fetchall()
    targets = conn.execute(
        "SELECT * FROM targets WHERE run_id = ? ORDER BY path", (run_id,)
    ).fetchall()
    diffs = compare.diff_sets(conn, run_id, prev_run_id)

    # overview counts
    dir_counts = {k: 0 for k in DIR_MARK if k}
    for m in metrics:
        d = m["direction"] or "not_comparable"
        dir_counts[d] = dir_counts.get(d, 0) + 1
    dir_counts["missing"] = len(diffs["missing_metrics"])

    status_counts = {}
    for m in metrics:
        status_counts[m["status"]] = status_counts.get(m["status"], 0) + 1
    tool_status_counts = {}
    for tr in tool_results:
        tool_status_counts[tr["status"]] = tool_status_counts.get(tr["status"], 0) + 1

    obs_counts = {"new": 0, "still_present": 0, "changed": 0}
    obs_sev = {}
    for o in observations:
        s = o["status_vs_previous"] or "new"
        obs_counts[s] = obs_counts.get(s, 0) + 1
        obs_sev[o["severity"]] = obs_sev.get(o["severity"], 0) + 1
    obs_counts["fixed"] = len(diffs["fixed_observations"])

    actions = [
        dict(a)
        for a in conn.execute(
            "SELECT * FROM actions WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()
    ]

    data = {
        "run": run,
        "prev": prev,
        "prev_run_id": prev_run_id,
        "metrics": metrics,
        "observations": observations,
        "tool_results": tool_results,
        "targets": targets,
        "diffs": diffs,
        "dir_counts": dir_counts,
        "status_counts": status_counts,
        "tool_status_counts": tool_status_counts,
        "obs_counts": obs_counts,
        "obs_sev": obs_sev,
        "is_first": prev is None,
        "site_name": cfg.site_name,
        "actions": actions,
        "thresholds": cfg.raw.get("significance_thresholds") or {},
    }
    data["scorecards"] = _scorecards(data)
    data["headline"] = _headline(conn, cfg, run_id, data)
    data["diagnosis"] = _diagnosis(data)
    return data


def _fmt_val(m):
    if m["value_text"] is not None:
        return lib.ascii_norm(m["value_text"])
    if m["value_numeric"] is not None:
        n = m["value_numeric"]
        return str(int(n)) if float(n).is_integer() else str(n)
    if m["value_bool"] is not None:
        return "true" if m["value_bool"] else "false"
    if m["grade"] is not None:
        return m["grade"]
    return "-"


def _prev_val(m):
    if m["previous_value_text"] is not None:
        return lib.ascii_norm(m["previous_value_text"])
    if m["previous_value_numeric"] is not None:
        n = m["previous_value_numeric"]
        return str(int(n)) if float(n).is_integer() else str(n)
    return "-"


def _changes(data):
    """Return (improvements, declines, changed_values) lists of metric rows."""
    improvements, declines, changed = [], [], []
    for m in data["metrics"]:
        d = m["direction"]
        if d == "improved":
            improvements.append(m)
        elif d == "declined":
            declines.append(m)
        elif (
            d == "not_comparable"
            and m["comparison_mode"] in ("exact_match", "neutral")
            and m["previous_value_text"] is not None
            and m["previous_value_text"] != m["value_text"]
        ):
            changed.append(m)

    def keyf(m):
        return abs(m["delta_numeric"]) if m["delta_numeric"] is not None else 0

    improvements.sort(key=keyf, reverse=True)
    declines.sort(key=keyf, reverse=True)
    return improvements, declines, changed


# ---------------------------------------------------------------------------
# V2 decision-layer helpers (scorecards, next actions, trendlines)
# ---------------------------------------------------------------------------
RANK = {"high": 0, "medium": 1, "med": 1, "low": 2, None: 3}
STATUS_RANK = {"PASS": 0, "REVIEW": 1, "FAIL": 2}

HEADLINE_METRICS = [
    "lighthouse.performance.score",
    "lighthouse.accessibility.score",
    "lighthouse.seo.score",
    "lighthouse.best_practices.score",
    "lighthouse.lcp_ms",
    "lighthouse.tbt_ms",
    "lighthouse.cls",
    "security.observatory.score",
    "tls.ssl_labs.grade",
    "links.internal_broken.count",
    "html.errors.count",
]


def _by_metric(data):
    out = {}
    for m in data["metrics"]:
        out.setdefault(m["metric"], []).append(m)
    return out


def _worst(statuses):
    statuses = [s for s in statuses if s]
    if not statuses:
        return None
    return max(statuses, key=lambda s: STATUS_RANK.get(s, 0))


def _nums(rows, prev=False):
    col = "previous_value_numeric" if prev else "value_numeric"
    return [m[col] for m in rows if m[col] is not None]


def _scorecards(data):
    bm = _by_metric(data)

    def perf(scores):
        if not scores:
            return None
        lo = min(scores)
        return "FAIL" if lo < 50 else ("REVIEW" if lo < 90 else "PASS")

    def grade_status(rows, prev=False):
        col = "previous_value_text" if prev else "value_text"
        ranks = [lib.GRADE_RANK.get(m[col], 99) for m in rows if m[col]]
        if not ranks:
            return None
        worst = max(ranks)
        return (
            "FAIL"
            if worst > lib.GRADE_RANK["C"]
            else ("REVIEW" if worst > lib.GRADE_RANK["A"] else "PASS")
        )

    cards = []

    def add(name, status, prev_status, driver_rows, detail=""):
        direction = "unchanged"
        if status and prev_status:
            cur, pre = STATUS_RANK.get(status, 0), STATUS_RANK.get(prev_status, 0)
            direction = "improved" if cur < pre else "declined" if cur > pre else "unchanged"
        decl = [m for m in driver_rows if m["direction"] == "declined"]
        decl.sort(
            key=lambda m: abs(m["delta_numeric"]) if m["delta_numeric"] is not None else 0,
            reverse=True,
        )
        driver = "stable"
        if decl:
            m = decl[0]
            driver = (
                f"{m['path']} {_short_metric(m['metric']) or m['metric']} "
                f"{_prev_val(m)}->{_fmt_val(m)}"
            )
        cards.append(
            {
                "name": name,
                "status": status or "n/a",
                "prev_status": prev_status or "n/a",
                "direction": direction,
                "top_driver": driver,
                "detail": detail,
            }
        )

    def _page_scores(metric):
        rows = sorted(
            (m for m in bm.get(metric, []) if m["value_numeric"] is not None),
            key=lambda m: m["path"],
        )
        return ", ".join(f"{m['path']} {int(m['value_numeric'])}" for m in rows)

    # Performance
    perf_rows = bm.get("lighthouse.performance.score", [])
    add(
        "Performance",
        perf(_nums(perf_rows)),
        perf(_nums(perf_rows, prev=True)),
        perf_rows,
        detail=_page_scores("lighthouse.performance.score") or "no data",
    )

    # Publication Quality: html errors/warnings, jsonld valid, seo
    pub_rows = (
        bm.get("html.errors.count", [])
        + bm.get("html.warnings.count", [])
        + bm.get("lighthouse.seo.score", [])
        + bm.get("structured_data.jsonld.valid", [])
    )

    def pub(prev=False):
        col = "previous_value_numeric" if prev else "value_numeric"
        st = []
        errs = [m[col] for m in bm.get("html.errors.count", []) if m[col] is not None]
        if errs:
            st.append("FAIL" if max(errs) > 0 else "PASS")
        warns = [m[col] for m in bm.get("html.warnings.count", []) if m[col] is not None]
        if warns:
            st.append("REVIEW" if max(warns) > 0 else "PASS")
        seo = [m[col] for m in bm.get("lighthouse.seo.score", []) if m[col] is not None]
        if seo:
            st.append("REVIEW" if min(seo) < 90 else "PASS")
        # jsonld validity is bool-only (no prev column), same shape as the
        # tracking check in priv()
        if not prev and any(
            m["value_bool"] is False for m in bm.get("structured_data.jsonld.valid", [])
        ):
            st.append("FAIL")
        return _worst(st)

    _errs = max(
        [
            m["value_numeric"]
            for m in bm.get("html.errors.count", [])
            if m["value_numeric"] is not None
        ]
        or [0]
    )
    _warns = max(
        [
            m["value_numeric"]
            for m in bm.get("html.warnings.count", [])
            if m["value_numeric"] is not None
        ]
        or [0]
    )
    add(
        "Publication Quality",
        pub(),
        pub(prev=True),
        pub_rows,
        detail=f"{int(_errs)} HTML errors, {int(_warns)} warning(s)/page",
    )

    # Privacy
    priv_rows = bm.get("privacy.third_party_resources.count", []) + bm.get(
        "privacy.cookies.count", []
    )

    def priv(prev=False):
        col = "previous_value_numeric" if prev else "value_numeric"
        st = []
        # tracking is bool-only (no prev column), so the prev scorecard
        # carries the count-based checks below
        if not prev and any(m["value_bool"] for m in bm.get("privacy.tracking_detected", [])):
            st.append("FAIL")
        tp = [
            m[col] for m in bm.get("privacy.third_party_resources.count", []) if m[col] is not None
        ]
        if tp:
            st.append("REVIEW" if max(tp) > 0 else "PASS")
        ck = [m[col] for m in bm.get("privacy.cookies.count", []) if m[col] is not None]
        if ck:
            st.append("REVIEW" if max(ck) > 0 else "PASS")
        return _worst(st) or "PASS"

    _ck = max(
        [
            m["value_numeric"]
            for m in bm.get("privacy.cookies.count", [])
            if m["value_numeric"] is not None
        ]
        or [0]
    )
    _tp = max(
        [
            m["value_numeric"]
            for m in bm.get("privacy.third_party_resources.count", [])
            if m["value_numeric"] is not None
        ]
        or [0]
    )
    add(
        "Privacy",
        priv(),
        priv(prev=True),
        priv_rows,
        detail=f"{int(_ck)} cookies, {int(_tp)} third-party resources",
    )

    # Security (observatory grade + tests_failed)
    obs_rows = bm.get("security.observatory.grade", [])

    def sec(prev=False):
        col = "previous_value_numeric" if prev else "value_numeric"
        st = [grade_status(obs_rows, prev=prev)]
        tf = [m[col] for m in bm.get("security.observatory.tests_failed", []) if m[col] is not None]
        if tf:
            st.append("REVIEW" if max(tf) > 0 else "PASS")
        return _worst(st)

    _og = next((m["value_text"] for m in obs_rows if m["value_text"]), "?")
    _sg = next((m["value_text"] for m in bm.get("tls.ssl_labs.grade", []) if m["value_text"]), "?")
    add(
        "Security",
        sec(),
        sec(prev=True),
        obs_rows + bm.get("tls.ssl_labs.grade", []),
        detail=f"Observatory {_og}, SSL Labs {_sg}",
    )

    # Trust files (required files present + 200)
    REQUIRED = [
        "trust.integrity_json.status_code",
        "trust.integrity_json_sig.status_code",
        "trust.pgp_key.status_code",
        "trust.security_txt.status_code",
        "trust.robots_txt.status_code",
        "trust.sitemap_xml.status_code",
    ]
    trust_rows = [m for k in REQUIRED for m in bm.get(k, [])]

    def trust(prev=False):
        col = "previous_value_numeric" if prev else "value_numeric"
        codes = [m[col] for m in trust_rows if m[col] is not None]
        if not codes:
            return None
        return "FAIL" if any(c != 200 for c in codes) else "PASS"

    _present = sum(1 for m in trust_rows if m["value_numeric"] == 200)
    _total = len(trust_rows)
    _trust_detail = (
        "all core trust files present"
        if _total and _present == _total
        else f"{_present}/{_total} core trust files present"
    )
    add("Trust", trust(), trust(prev=True), trust_rows, detail=_trust_detail)

    return cards


def _next_actions(data, limit=6):
    """Top open actions by impact x actionability."""
    opens = [a for a in data["actions"] if a["status"] == "open"]
    opens.sort(key=lambda a: (RANK.get(a["impact"], 3), RANK.get(a["actionability"], 3)))
    return opens[:limit]


# --- sparklines (HTML only) --------------------------------------------------
def _spark_series(conn, run_id, key, comparison_mode, current_row):
    """Return (plot_values, annotation) for the last up-to-5 runs (incl current).
    Grades are plotted as inverted rank so A+ sits highest."""
    is_grade = comparison_mode == "grade_order"
    prior = list(reversed(compare.history(conn, run_id, key, 4)))  # ascending

    def plot(numeric, text, grade):
        if is_grade:
            g = grade or text
            return -lib.GRADE_RANK.get(g, 99) if g else None
        return numeric

    vals = []
    for r in prior:
        v = plot(r["value_numeric"], r["value_text"], r["grade"])
        if v is not None:
            vals.append(v)
    cur = plot(current_row["value_numeric"], current_row["value_text"], current_row["grade"])
    if cur is not None:
        vals.append(cur)
    return vals, is_grade


def _sparkline(values, comparison_mode):
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    rng = (hi - lo) or 1
    n, W, H, pad = len(values), 110, 22, 2
    invert = comparison_mode == "lower_better"
    pts = []
    for i, v in enumerate(values):
        x = pad + i * (W - 2 * pad) / (n - 1)
        norm = (v - lo) / rng
        if invert:
            norm = 1 - norm
        y = H - pad - norm * (H - 2 * pad)
        pts.append(f"{x:.1f},{y:.1f}")
    a, b = values[-2], values[-1]
    color = "#8a8378"
    if a != b:
        if comparison_mode == "higher_better":
            better = b > a
        elif comparison_mode == "lower_better":
            better = b < a
        else:
            better = None
        if better is not None:
            color = "#2f5d1e" if better else "#8a2b22"
    lx, ly = pts[-1].split(",")
    return (
        f"<svg viewBox='0 0 {W} {H}' width='{W}' height='{H}' class='spark'>"
        f"<polyline fill='none' stroke='{color}' stroke-width='1.5' "
        f"points='{' '.join(pts)}'/>"
        f"<circle cx='{lx}' cy='{ly}' r='1.8' fill='{color}'/></svg>"
    )


def _headline(conn, cfg, run_id, data):
    """Build headline-metric rows with baseline context + sparkline series."""
    modes = (cfg.raw.get("comparison") or {}).get(
        "baseline_modes", ["previous", "best", "rolling_median"]
    )
    rows = []
    for m in data["metrics"]:
        if m["metric"] not in HEADLINE_METRICS:
            continue
        key = (m["path"], m["tool"], m["category"], m["metric"])
        # current value rendered from the numeric via the shared formatter so it
        # matches the baselines exactly (no Lighthouse displayValue mixing).
        cur = _disp(m["metric"], m["value_numeric"], m["grade"] or m["value_text"])
        baselines = {}
        for mode in modes:
            bv = compare.baseline_value(conn, cfg, run_id, key, mode, m["comparison_mode"])
            if bv:
                baselines[mode] = _disp(
                    m["metric"], bv["value_numeric"], bv["grade"] or bv["value_text"]
                )
        series, _ = _spark_series(conn, run_id, key, m["comparison_mode"], m)
        rows.append(
            {
                "path": m["path"],
                "metric": m["metric"],
                "cur": cur,
                "comparison_mode": m["comparison_mode"],
                "direction": m["direction"],
                "baselines": baselines,
                "series": series,
            }
        )
    return rows


# --- significance, diagnosis, matrix, action board (V2.1) -------------------
def _significant(m, thresholds):
    """A numeric change counts as meaningful unless below its threshold."""
    t = thresholds.get(m["metric"])
    if t is None:
        return True
    d = m["delta_numeric"]
    if d is None:
        return True
    return abs(d) >= t


def _diagnosis(data):
    """One plain-English paragraph derived from scorecards + open actions."""
    cards = {c["name"]: c["status"] for c in data["scorecards"]}
    passing = [n for n, s in cards.items() if s == "PASS"]
    review = [n for n, s in cards.items() if s == "REVIEW"]
    fail = [n for n, s in cards.items() if s == "FAIL"]
    opens = [a for a in data["actions"] if a["status"] == "open"]
    highs = [a for a in opens if a["impact"] == "high"]

    if fail:
        lead = f"Attention needed: {', '.join(fail)} failing."
    elif review:
        lead = "The site is broadly healthy."
    else:
        lead = "The site is healthy."
    parts = [lead]
    if passing:
        parts.append(f"{', '.join(passing)} {'is' if len(passing) == 1 else 'are'} stable.")
    perf = next((c for c in data["scorecards"] if c["name"] == "Performance"), None)
    if perf and perf["status"] == "REVIEW":
        parts.append(f"The main area for improvement is performance ({perf['detail']}).")
    if highs:
        parts.append(f"{len(highs)} high-impact action(s) are open.")
    elif opens:
        parts.append(f"{len(opens)} small open action(s) remain; no high-impact issues.")
    else:
        parts.append("No open actions.")
    return lib.ascii_norm(" ".join(parts))


def _matrix(data):
    """Per-(page, category) PASS/REVIEW/FAIL. Returns (columns, rows-by-category)."""
    pages = [t["path"] for t in data["targets"]] + ["(site)"]
    cells = {}  # (category, column) -> status
    for m in data["metrics"]:
        cat = m["category"]
        col = m["path"] if m["path"] in pages else "(site)"
        st = {"ok": "PASS", "warning": "REVIEW", "error": "FAIL"}.get(m["status"])
        if st is None:
            continue
        prev = cells.get((cat, col))
        if prev is None or STATUS_RANK[st] > STATUS_RANK[prev]:
            cells[(cat, col)] = st
    rows = []
    seen = set()
    for cat in PAGE_CATEGORIES + SITE_CATEGORIES:
        if cat in seen:
            continue
        seen.add(cat)
        present = {c: cells.get((cat, c)) for c in pages}
        if any(present[c] for c in pages):
            rows.append((cat, present))
    return pages, rows


def _action_board(data):
    """Group actions: Fix now / Clean up soon / Known noise."""
    fix_now, soon, noise = [], [], []
    for a in data["actions"]:
        if a["status"] == "known_noise":
            noise.append(a)
        elif a["status"] != "open":
            continue  # acknowledged/ignored/fixed are not surfaced as work
        elif a["impact"] in ("high", "medium") and a["actionability"] == "high":
            fix_now.append(a)
        else:
            soon.append(a)

    def order(a):
        return (RANK.get(a["impact"], 3), RANK.get(a["actionability"], 3))

    fix_now.sort(key=order)
    soon.sort(key=order)
    return fix_now, soon, noise


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------
def render_markdown(data):
    run = data["run"]
    L = []
    L.append(f"# {data['site_name']} Score Ledger")
    L.append("")
    head = f"Run #{run['id']} - {run['started_at']}"
    if run["run_label"]:
        head += f" - label: {run['run_label']}"
    L.append(head)
    if data["is_first"]:
        L.append("")
        L.append("First run - establishing baseline. No previous run to compare against.")
    else:
        L.append(f"Compared to Run #{data['prev_run_id']} ({data['prev']['started_at']})")
    L.append("")
    urls = ", ".join(t["url"] for t in data["targets"])
    L.append(f"URLs checked: {urls}")
    L.append("")

    # Overview
    L.append("## Overview")
    L.append("")
    dc = data["dir_counts"]
    L.append(f"Metrics collected: {len(data['metrics'])}")
    L.append("")
    L.append("| direction | count |")
    L.append("| --- | --- |")
    for k in ["improved", "declined", "unchanged", "new", "missing", "not_comparable"]:
        L.append(f"| {k} | {dc.get(k, 0)} |")
    L.append("")
    L.append("| tool status | count |")
    L.append("| --- | --- |")
    for k, v in sorted(data["tool_status_counts"].items()):
        L.append(f"| {k} | {v} |")
    L.append("")
    oc = data["obs_counts"]
    L.append(
        f"Observations - new: {oc.get('new', 0)}, fixed: {oc.get('fixed', 0)}, "
        f"still present: {oc.get('still_present', 0)}, changed: {oc.get('changed', 0)}"
    )
    L.append("")

    # Current diagnosis (plain-English health read)
    L.append("## Current diagnosis")
    L.append("")
    L.append(data["diagnosis"])
    L.append("")

    # Next actions (the first actionable section)
    L.append("## Next actions")
    L.append("")
    nexts = _next_actions(data)
    if not nexts:
        L.append("No open actions - nothing flagged for follow-up this run.")
    else:
        for i, a in enumerate(nexts, 1):
            L.append(f"{i}. {lib.ascii_norm(a['title'])}  [{a['impact']} impact]")
            L.append(f"   page: {a['target_path']}  area: {a['suggested_area']}")
            if a["rationale"]:
                L.append(f"   evidence: {lib.ascii_norm(a['rationale'])}")
            L.append(f"   next step: {lib.ascii_norm(a['recommended_action'])}")
            L.append("")
    L.append("")

    # Scorecards
    L.append("## Scorecards")
    L.append("")
    L.append("| scorecard | status | detail | trend | top driver |")
    L.append("| --- | --- | --- | --- | --- |")
    for c in data["scorecards"]:
        L.append(
            f"| {c['name']} | {c['status']} | {lib.ascii_norm(c.get('detail', ''))} | "
            f"{DIR_MARK.get(c['direction'], '')} | {lib.ascii_norm(c['top_driver'])} |"
        )
    L.append("")

    # Page x category matrix (at-a-glance)
    L.append("## Page x category matrix")
    L.append("")
    pages, mrows = _matrix(data)
    L.append("| category | " + " | ".join(pages) + " |")
    L.append("| --- |" + " --- |" * len(pages))
    for cat, present in mrows:
        cells = " | ".join((present.get(p) or "-") for p in pages)
        L.append(f"| {cat} | {cells} |")
    L.append("")

    # Headline trends (text form; sparklines are HTML-only)
    if data["headline"]:
        L.append("## Headline metrics")
        L.append("")
        for h in data["headline"]:
            ctx = ", ".join(f"{k}={v}" for k, v in h["baselines"].items())
            L.append(f"- {h['path']} {h['metric']} = {h['cur']}" + (f"  ({ctx})" if ctx else ""))
        L.append("")

    # External integrations
    L.append("## External integrations")
    L.append("")
    L.append("| integration | status | result | source |")
    L.append("| --- | --- | --- | --- |")
    for _tool, label, status, vals, src in _integration_rows(data):
        L.append(f"| {label} | {status} | {vals or '-'} | {src or '-'} |")
    L.append("")

    # Top changes (meaningful vs minor, by significance threshold)
    L.append("## Top changes")
    L.append("")
    improvements, declines, changed = _changes(data)
    th = data["thresholds"]
    meaningful = [m for m in improvements + declines if _significant(m, th)]
    minor = [m for m in improvements + declines if not _significant(m, th)]
    meaningful.sort(
        key=lambda m: abs(m["delta_numeric"]) if m["delta_numeric"] is not None else 0, reverse=True
    )
    if data["is_first"]:
        L.append("None - baseline run.")
    elif not (meaningful or changed or data["diffs"]["fixed_observations"] or oc.get("new")):
        L.append("No meaningful changes since the previous run.")
    else:
        for m in meaningful[:20]:
            mark = DIR_MARK.get(m["direction"], "")
            L.append(f"- {mark} {m['path']} {m['metric']} {_prev_val(m)} -> {_fmt_val(m)}")
        for m in changed[:15]:
            L.append(f"- [changed] {m['path']} {m['metric']} (value changed)")
    L.append("")
    if minor:
        L.append(f"Minor changes (below significance thresholds): {len(minor)}")
        L.append("")

    # Action board: Fix now / Clean up soon / Known noise
    L.append("## Action board")
    L.append("")
    fix_now, soon, noise = _action_board(data)

    def _emit(title, items):
        L.append(f"### {title} ({len(items)})")
        if not items:
            L.append("- none")
        for a in items:
            L.append(
                f"- {a['suggested_area']} {a['target_path'] or '-'}: "
                f"{lib.ascii_norm(a['title'])} - {lib.ascii_norm(a['recommended_action'] or '')}"
            )
        L.append("")

    _emit("Fix now", fix_now)
    _emit("Clean up soon", soon)
    L.append(f"### Known validator noise ({len(noise)})")
    for a in noise:
        L.append(
            f"- {a['suggested_area']} {a['target_path']}: {lib.ascii_norm(a['title'])} "
            f"- {lib.ascii_norm(a['rationale'])}"
        )
    L.append("")

    # Observations diff
    L.append("## Observations")
    L.append("")
    new_obs = [o for o in data["observations"] if (o["status_vs_previous"] or "new") == "new"]
    L.append(f"### New ({len(new_obs)})")
    for o in new_obs:
        loc = f", line {o['line']}" if o["line"] else ""
        L.append(
            f"- {o['severity']} {o['path']} {lib.ascii_norm(o['title'])}{loc} ({o['fingerprint']})"
        )
    L.append("")
    fixed = data["diffs"]["fixed_observations"]
    L.append(f"### Fixed ({len(fixed)})")
    for o in fixed:
        L.append(f"- {o['path']} {o['fingerprint']}")
    L.append("")
    changed_obs = [o for o in data["observations"] if o["status_vs_previous"] == "changed"]
    L.append(f"### Changed ({len(changed_obs)})")
    for o in changed_obs:
        L.append(f"- {o['severity']} {o['path']} {lib.ascii_norm(o['title'])} ({o['fingerprint']})")
    L.append("")
    still = [o for o in data["observations"] if o["status_vs_previous"] == "still_present"]
    L.append(f"### Still present: {len(still)}")
    L.append("")

    # Per-category summary
    L.append("## Per-category summary")
    L.append("")
    by_cat = {}
    for m in data["metrics"]:
        by_cat.setdefault(m["category"], []).append(m)
    for cat in CATEGORIES:
        rows = by_cat.get(cat)
        if not rows:
            continue
        ok = sum(1 for m in rows if m["status"] == "ok")
        warn = sum(1 for m in rows if m["status"] == "warning")
        err = sum(1 for m in rows if m["status"] == "error")
        impr = sum(1 for m in rows if m["direction"] == "improved")
        decl = sum(1 for m in rows if m["direction"] == "declined")
        L.append(
            f"- {cat}: {len(rows)} metrics (ok {ok}, warning {warn}, "
            f"error {err}; improved {impr}, declined {decl})"
        )
    L.append("")

    # Per-page summary
    L.append("## Per-page summary")
    L.append("")
    for t in data["targets"]:
        page_metrics = [m for m in data["metrics"] if m["path"] == t["path"]]
        page_obs = [o for o in data["observations"] if o["path"] == t["path"]]
        L.append(f"### {t['path']}  ({t['url']})")
        sc = t["status_code"] if t["status_code"] is not None else "-"
        rm = f"{t['response_ms']:.0f} ms" if t["response_ms"] is not None else "-"
        L.append(
            f"- status {sc}, response {rm}, metrics {len(page_metrics)}, "
            f"observations {len(page_obs)}"
        )
        L.append("")

    # Manual / unavailable
    manual = [tr for tr in data["tool_results"] if tr["status"] in ("manual", "unavailable")]
    L.append("## Manual / unavailable checks")
    L.append("")
    if not manual:
        L.append("None.")
    else:
        L.append("| tool | path | status | source_url |")
        L.append("| --- | --- | --- | --- |")
        for tr in manual:
            L.append(
                f"| {tr['tool']} | {tr['path'] or '-'} | {tr['status']} | "
                f"{tr['source_url'] or '-'} |"
            )
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# HTML (quiet, self-contained, no JS)
# ---------------------------------------------------------------------------
CSS = """
body{font-family:Georgia,'Times New Roman',serif;max-width:60rem;margin:2rem auto;
padding:0 1.2rem;background:#fbf8f3;color:#1a1714;line-height:1.5}
h1,h2,h3{font-weight:600;line-height:1.2}
h1{font-size:1.6rem;border-bottom:1px solid #ddd4c6;padding-bottom:.4rem}
h2{font-size:1.2rem;margin-top:2rem}
h3{font-size:1rem;color:#5c564d}
table{border-collapse:collapse;margin:.6rem 0;font-size:.9rem}
th,td{border:1px solid #ddd4c6;padding:.25rem .6rem;text-align:left}
th{background:#f1ece2}
code,pre{font-family:'DejaVu Sans Mono',monospace;font-size:.82rem}
pre{background:#f1ece2;padding:.6rem;overflow:auto;border:1px solid #ddd4c6}
.chip{display:inline-block;padding:.05rem .4rem;border-radius:.2rem;font-size:.8rem;
font-family:monospace}
.improved{background:#dff0d8;color:#2f5d1e}
.declined{background:#f2dede;color:#8a2b22}
.unchanged{background:#eee;color:#555}
.new{background:#fcf3d4;color:#7a5a00}
.muted{color:#8a8378;font-size:.85rem}
details{margin:.4rem 0}summary{cursor:pointer}
ul{padding-left:1.2rem}
.sc-pass{color:#2f5d1e}.sc-review{color:#7a5a00}.sc-fail{color:#8a2b22}.sc-na{color:#8a8378}
.spark{vertical-align:middle;margin:0 .4rem}
.next{list-style:decimal;padding-left:1.4rem}
.next li{margin:.7rem 0}
.act{border-left:3px solid #ddd4c6;padding:.15rem .8rem;margin:.5rem 0}
.act-high{border-color:#8a2b22}.act-medium{border-color:#9a7b1f}.act-low{border-color:#c4bcae}
.tag{font-size:.72rem;color:#5c564d;font-family:monospace}
.noise{color:#8a8378}
.trend td{padding:.2rem .5rem;border:none}
"""


def _chip(direction):
    cls = direction if direction in ("improved", "declined", "unchanged", "new") else "unchanged"
    return f'<span class="chip {cls}">{html.escape(DIR_MARK.get(direction, "[?]"))}</span>'


def _sc_class(status):
    return {"PASS": "sc-pass", "REVIEW": "sc-review", "FAIL": "sc-fail"}.get(status, "sc-na")


def render_html(data):
    run = data["run"]
    e = html.escape
    P = []
    P.append("<!doctype html><html lang='en'><head><meta charset='utf-8'>")
    P.append(f"<title>{e(data['site_name'])} Score Ledger - Run #{run['id']}</title>")
    P.append(f"<style>{CSS}</style></head><body>")
    P.append(f"<h1>{e(data['site_name'])} Score Ledger</h1>")
    P.append(
        f"<p class='muted'>Run #{run['id']} - {e(run['started_at'])}"
        + (f" - label: {e(run['run_label'])}" if run["run_label"] else "")
        + "</p>"
    )
    if data["is_first"]:
        P.append("<p>First run - establishing baseline. No previous run to compare against.</p>")
    else:
        P.append(
            f"<p class='muted'>Compared to Run #{data['prev_run_id']} "
            f"({e(data['prev']['started_at'])})</p>"
        )

    # Overview
    P.append("<h2>Overview</h2>")
    dc = data["dir_counts"]
    P.append(f"<p>Metrics collected: <strong>{len(data['metrics'])}</strong></p>")
    P.append("<table><tr><th>direction</th><th>count</th></tr>")
    for k in ["improved", "declined", "unchanged", "new", "missing", "not_comparable"]:
        P.append(f"<tr><td>{_chip(k)} {k}</td><td>{dc.get(k, 0)}</td></tr>")
    P.append("</table>")
    oc = data["obs_counts"]
    P.append(
        f"<p>Observations - new: {oc.get('new', 0)}, fixed: {oc.get('fixed', 0)}, "
        f"still present: {oc.get('still_present', 0)}, changed: {oc.get('changed', 0)}</p>"
    )

    # Current diagnosis
    P.append("<h2>Current diagnosis</h2>")
    P.append(f"<p>{e(data['diagnosis'])}</p>")

    # Next actions
    P.append("<h2>Next actions</h2>")
    nexts = _next_actions(data)
    if not nexts:
        P.append("<p class='muted'>No open actions - nothing flagged for follow-up this run.</p>")
    else:
        P.append("<ol class='next'>")
        for a in nexts:
            P.append(
                f"<li class='act act-{a['impact'] or 'low'}'>"
                f"<strong>{e(lib.ascii_norm(a['title']))}</strong> "
                f"<span class='tag'>[{e(a['impact'] or '?')} impact / "
                f"{e(a['suggested_area'] or '?')} / {e(a['target_path'] or '-')}]</span>"
                + (
                    f"<br><span class='muted'>{e(lib.ascii_norm(a['rationale']))}</span>"
                    if a["rationale"]
                    else ""
                )
                + f"<br>{e(lib.ascii_norm(a['recommended_action'] or ''))}</li>"
            )
        P.append("</ol>")

    # Scorecards
    P.append("<h2>Scorecards</h2>")
    P.append(
        "<table><tr><th>scorecard</th><th>status</th><th>detail</th>"
        "<th>trend</th><th>top driver</th></tr>"
    )
    for c in data["scorecards"]:
        P.append(
            f"<tr><td>{e(c['name'])}</td>"
            f"<td class='{_sc_class(c['status'])}'>{e(c['status'])}</td>"
            f"<td class='muted'>{e(lib.ascii_norm(c.get('detail', '')))}</td>"
            f"<td>{_chip(c['direction'])}</td>"
            f"<td class='muted'>{e(lib.ascii_norm(c['top_driver']))}</td></tr>"
        )
    P.append("</table>")

    # Page x category matrix
    P.append("<h2>Page x category matrix</h2>")
    pages, mrows = _matrix(data)
    P.append("<table><tr><th>category</th>" + "".join(f"<th>{e(p)}</th>" for p in pages) + "</tr>")
    for cat, present in mrows:
        tds = "".join(
            (
                f"<td class='{_sc_class(present[p])}'>{e(present[p])}</td>"
                if present.get(p)
                else "<td class='muted'>-</td>"
            )
            for p in pages
        )
        P.append(f"<tr><td>{e(cat)}</td>{tds}</tr>")
    P.append("</table>")

    # Trends (inline SVG sparklines, no JS)
    if data["headline"]:
        P.append("<h2>Trends <span class='muted'>(last 5 runs)</span></h2>")
        P.append("<table class='trend'>")
        for h in data["headline"]:
            spark = _sparkline(h["series"], h["comparison_mode"])
            ctx = ", ".join(f"{k} {v}" for k, v in h["baselines"].items())
            P.append(
                f"<tr><td class='muted'>{e(h['path'])}</td>"
                f"<td><code>{e(h['metric'])}</code></td>"
                f"<td>{spark}</td>"
                f"<td><strong>{e(h['cur'])}</strong></td>"
                f"<td class='muted'>{e(ctx)}</td></tr>"
            )
        P.append("</table>")

    # External integrations
    P.append("<h2>External integrations</h2>")
    P.append("<table><tr><th>integration</th><th>status</th><th>result</th><th>source</th></tr>")
    for _tool, label, status, vals, src in _integration_rows(data):
        srccell = f"<a href='{e(src)}'>link</a>" if src else "-"
        P.append(
            f"<tr><td>{e(label)}</td><td>{e(status)}</td>"
            f"<td>{e(vals or '-')}</td><td>{srccell}</td></tr>"
        )
    P.append("</table>")

    # Top changes (meaningful vs minor)
    P.append("<h2>Top changes</h2>")
    improvements, declines, changed = _changes(data)
    th = data["thresholds"]
    meaningful = [m for m in improvements + declines if _significant(m, th)]
    minor = [m for m in improvements + declines if not _significant(m, th)]
    meaningful.sort(
        key=lambda m: abs(m["delta_numeric"]) if m["delta_numeric"] is not None else 0, reverse=True
    )
    if data["is_first"]:
        P.append("<p class='muted'>None - baseline run.</p>")
    elif not (meaningful or changed):
        P.append("<p class='muted'>No meaningful changes since the previous run.</p>")
    else:
        P.append("<ul>")
        for m in meaningful[:20]:
            P.append(
                f"<li>{_chip(m['direction'])} {e(m['path'])} "
                f"<code>{e(m['metric'])}</code> {e(_prev_val(m))} -&gt; {e(_fmt_val(m))}</li>"
            )
        for m in changed[:15]:
            P.append(
                f"<li><span class='chip new'>[changed]</span> {e(m['path'])} "
                f"<code>{e(m['metric'])}</code> value changed</li>"
            )
        P.append("</ul>")
    if minor:
        P.append(f"<p class='muted'>Minor changes below significance thresholds: {len(minor)}</p>")

    # Action board: Fix now / Clean up soon / Known noise
    P.append("<h2>Action board</h2>")
    fix_now, soon, noise = _action_board(data)

    def _board(title, items):
        P.append(f"<h3>{title} ({len(items)})</h3>")
        if not items:
            P.append("<p class='muted'>none</p>")
            return
        for a in items:
            P.append(
                f"<div class='act act-{a['impact'] or 'low'}'>"
                f"<strong>{e(lib.ascii_norm(a['title']))}</strong> "
                f"<span class='tag'>[{e(a['suggested_area'] or '?')} / "
                f"{e(a['target_path'] or '-')}]</span><br>"
                f"<span class='muted'>{e(lib.ascii_norm(a['recommended_action'] or ''))}</span></div>"
            )

    _board("Fix now", fix_now)
    _board("Clean up soon", soon)
    P.append(
        f"<details><summary class='noise'>Known validator noise "
        f"({len(noise)})</summary><ul class='noise'>"
    )
    for a in noise:
        P.append(
            f"<li>{e(a['suggested_area'])} {e(a['target_path'])} "
            f"{e(lib.ascii_norm(a['title']))} - {e(lib.ascii_norm(a['rationale']))}</li>"
        )
    P.append("</ul></details>")

    # Observations
    P.append("<h2>Observations</h2>")
    new_obs = [o for o in data["observations"] if (o["status_vs_previous"] or "new") == "new"]
    P.append(f"<h3>New ({len(new_obs)})</h3><ul>")
    for o in new_obs:
        loc = f", line {o['line']}" if o["line"] else ""
        P.append(
            f"<li>{e(o['severity'])} {e(o['path'])} {e(lib.ascii_norm(o['title']) or '')}{loc} "
            f"<span class='muted'>{e(o['fingerprint'] or '')}</span></li>"
        )
    P.append("</ul>")
    fixed = data["diffs"]["fixed_observations"]
    P.append(f"<h3>Fixed ({len(fixed)})</h3><ul>")
    for o in fixed:
        P.append(f"<li>{e(o['path'])} <span class='muted'>{e(o['fingerprint'] or '')}</span></li>")
    P.append("</ul>")
    # Changed observations — present in the Markdown report; was missing here,
    # so the HTML and Markdown editions of the same run disagreed. Kept in the
    # same New/Fixed/Changed/Still order as render_markdown.
    changed_obs = [o for o in data["observations"] if o["status_vs_previous"] == "changed"]
    P.append(f"<h3>Changed ({len(changed_obs)})</h3><ul>")
    for o in changed_obs:
        P.append(
            f"<li>{e(o['severity'])} {e(o['path'])} {e(lib.ascii_norm(o['title']) or '')} "
            f"<span class='muted'>{e(o['fingerprint'] or '')}</span></li>"
        )
    P.append("</ul>")
    still = [o for o in data["observations"] if o["status_vs_previous"] == "still_present"]
    P.append(f"<details><summary>Still present ({len(still)})</summary><ul>")
    for o in still:
        P.append(
            f"<li>{e(o['severity'])} {e(o['path'])} {e(lib.ascii_norm(o['title']) or '')}</li>"
        )
    P.append("</ul></details>")

    # Per-category
    P.append(
        "<h2>Per-category summary</h2><table>"
        "<tr><th>category</th><th>metrics</th><th>ok</th><th>warning</th>"
        "<th>error</th><th>improved</th><th>declined</th></tr>"
    )
    by_cat = {}
    for m in data["metrics"]:
        by_cat.setdefault(m["category"], []).append(m)
    for cat in CATEGORIES:
        rows = by_cat.get(cat)
        if not rows:
            continue
        ok = sum(1 for m in rows if m["status"] == "ok")
        warn = sum(1 for m in rows if m["status"] == "warning")
        err = sum(1 for m in rows if m["status"] == "error")
        impr = sum(1 for m in rows if m["direction"] == "improved")
        decl = sum(1 for m in rows if m["direction"] == "declined")
        P.append(
            f"<tr><td>{e(cat)}</td><td>{len(rows)}</td><td>{ok}</td>"
            f"<td>{warn}</td><td>{err}</td><td>{impr}</td><td>{decl}</td></tr>"
        )
    P.append("</table>")

    # Per-page
    P.append("<h2>Per-page summary</h2>")
    for t in data["targets"]:
        page_metrics = [m for m in data["metrics"] if m["path"] == t["path"]]
        page_obs = [o for o in data["observations"] if o["path"] == t["path"]]
        sc = t["status_code"] if t["status_code"] is not None else "-"
        rm = f"{t['response_ms']:.0f} ms" if t["response_ms"] is not None else "-"
        P.append(f"<h3>{e(t['path'])}</h3>")
        P.append(
            f"<p class='muted'>{e(t['url'])} - status {sc}, response {rm}, "
            f"metrics {len(page_metrics)}, observations {len(page_obs)}</p>"
        )

    # Manual / unavailable
    manual = [tr for tr in data["tool_results"] if tr["status"] in ("manual", "unavailable")]
    P.append("<h2>Manual / unavailable checks</h2>")
    if not manual:
        P.append("<p class='muted'>None.</p>")
    else:
        P.append("<table><tr><th>tool</th><th>path</th><th>status</th><th>source_url</th></tr>")
        for tr in manual:
            P.append(
                f"<tr><td>{e(tr['tool'])}</td><td>{e(tr['path'] or '-')}</td>"
                f"<td>{e(tr['status'])}</td><td>{e(tr['source_url'] or '-')}</td></tr>"
            )
        P.append("</table>")

    # Raw tool output (collapsed)
    P.append("<h2>Raw tool output</h2>")
    for tr in data["tool_results"]:
        if not tr["raw_json"]:
            continue
        label = f"{tr['tool']} @ {tr['path'] or '-'} ({tr['status']})"
        P.append(f"<details><summary>{e(label)}</summary><pre>{e(tr['raw_json'])}</pre></details>")

    P.append("</body></html>")
    return "".join(P)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def generate(conn, cfg, run_id):
    data = gather(conn, cfg, run_id)
    out_dir = cfg.reports_dir
    os.makedirs(out_dir, exist_ok=True)
    formats = cfg.reports.get("formats", ["md", "html"])
    written = []
    if "md" in formats:
        md = render_markdown(data)
        for name in (f"run-{run_id}.md", "latest.md"):
            path = os.path.join(out_dir, name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(md)
            written.append(path)
    if "html" in formats:
        page = render_html(data)
        for name in (f"run-{run_id}.html", "latest.html"):
            path = os.path.join(out_dir, name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(page)
            written.append(path)
    return written
