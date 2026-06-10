#!/usr/bin/env python3
"""Comparison engine: diff the latest run against the previous run.

Writes previous_value_*/delta_numeric/direction back onto the latest metric rows
and status_vs_previous onto the latest observation rows. "Missing" metrics and
"fixed" observations have no current row; they are recomputed on demand by
diff_sets() for the report layer rather than stored as ghost rows.
"""

from __future__ import annotations

import lib

NOT_COMPARABLE_STATUS = {"unavailable", "skipped", "manual", "error"}

# LEFT JOIN targets so site-level rows (target_id NULL, e.g. trust files and the
# external integrations) are included; their path collapses to '(site)'.
_METRIC_SQL = """
    SELECT m.id, m.metric, m.category, m.value_numeric, m.value_text,
           m.value_bool, m.grade, m.comparison_mode, m.status,
           COALESCE(t.path, '(site)') AS path, tr.tool AS tool
    FROM metrics m
    LEFT JOIN targets t ON t.id = m.target_id
    JOIN tool_results tr ON tr.id = m.tool_result_id
    WHERE m.run_id = ?
"""

_OBS_SQL = """
    SELECT o.id, o.fingerprint, o.message, o.severity,
           COALESCE(t.path, '(site)') AS path
    FROM observations o
    LEFT JOIN targets t ON t.id = o.target_id
    WHERE o.run_id = ?
"""


def _key(row):
    return (row["path"], row["tool"], row["category"], row["metric"])


def _comparable_value(row):
    if row["value_text"] is not None:
        return ("text", row["value_text"])
    if row["value_numeric"] is not None:
        return ("num", row["value_numeric"])
    if row["value_bool"] is not None:
        return ("bool", row["value_bool"])
    if row["grade"] is not None:
        return ("grade", row["grade"])
    return ("none", None)


def _classify(cur, prev, mode):
    if cur["status"] in NOT_COMPARABLE_STATUS or prev["status"] in NOT_COMPARABLE_STATUS:
        return "not_comparable"

    if mode in ("higher_better", "lower_better"):
        a, b = cur["value_numeric"], prev["value_numeric"]
        if a is None or b is None:
            return "not_comparable"
        if a == b:
            return "unchanged"
        better = a > b if mode == "higher_better" else a < b
        return "improved" if better else "declined"

    if mode == "boolean_pass":
        a, b = cur["value_bool"], prev["value_bool"]
        if a is None or b is None:
            return "not_comparable"
        if a == b:
            return "unchanged"
        return "improved" if a > b else "declined"

    if mode == "grade_order":
        a = lib.GRADE_RANK.get(cur["grade"])
        b = lib.GRADE_RANK.get(prev["grade"])
        if a is None or b is None:
            return "not_comparable"
        if a == b:
            return "unchanged"
        return "improved" if a < b else "declined"  # lower rank = better

    # exact_match / neutral: equal is unchanged, any difference is not_comparable
    # (a hash rotation must never read as "declined"; the change still surfaces in
    # the report's changed-values section via value_text difference).
    return "unchanged" if _comparable_value(cur) == _comparable_value(prev) else "not_comparable"


def compare_metrics(conn, run_id, prev_run_id):
    cur_rows = conn.execute(_METRIC_SQL, (run_id,)).fetchall()
    if prev_run_id is None:
        for r in cur_rows:
            conn.execute("UPDATE metrics SET direction = 'new' WHERE id = ?", (r["id"],))
        return

    prev = {_key(r): r for r in conn.execute(_METRIC_SQL, (prev_run_id,)).fetchall()}
    for cur in cur_rows:
        p = prev.get(_key(cur))
        if p is None:
            conn.execute(
                "UPDATE metrics SET direction = 'new', previous_value_numeric = NULL, "
                "previous_value_text = NULL, delta_numeric = NULL WHERE id = ?",
                (cur["id"],),
            )
            continue
        direction = _classify(cur, p, cur["comparison_mode"])
        delta = None
        if cur["value_numeric"] is not None and p["value_numeric"] is not None:
            delta = cur["value_numeric"] - p["value_numeric"]
        conn.execute(
            """UPDATE metrics SET previous_value_numeric = ?, previous_value_text = ?,
                   delta_numeric = ?, direction = ? WHERE id = ?""",
            (p["value_numeric"], p["value_text"], delta, direction, cur["id"]),
        )


def compare_observations(conn, run_id, prev_run_id):
    cur_rows = conn.execute(_OBS_SQL, (run_id,)).fetchall()
    if prev_run_id is None:
        for r in cur_rows:
            conn.execute(
                "UPDATE observations SET status_vs_previous = 'new' WHERE id = ?", (r["id"],)
            )
        return
    prev = {
        (r["path"], r["fingerprint"]): r for r in conn.execute(_OBS_SQL, (prev_run_id,)).fetchall()
    }
    for cur in cur_rows:
        p = prev.get((cur["path"], cur["fingerprint"]))
        if p is None:
            status = "new"
        elif p["message"] != cur["message"] or p["severity"] != cur["severity"]:
            status = "changed"
        else:
            status = "still_present"
        conn.execute(
            "UPDATE observations SET status_vs_previous = ? WHERE id = ?", (status, cur["id"])
        )


def diff_sets(conn, run_id, prev_run_id):
    """Recompute the sets that have no current row: metrics present last run but
    absent now ("missing"), and observations fixed since last run."""
    out = {"missing_metrics": [], "fixed_observations": []}
    if prev_run_id is None:
        return out
    cur_keys = {_key(r) for r in conn.execute(_METRIC_SQL, (run_id,)).fetchall()}
    for r in conn.execute(_METRIC_SQL, (prev_run_id,)).fetchall():
        if _key(r) not in cur_keys:
            out["missing_metrics"].append(dict(r))
    cur_fps = {(r["path"], r["fingerprint"]) for r in conn.execute(_OBS_SQL, (run_id,)).fetchall()}
    for r in conn.execute(_OBS_SQL, (prev_run_id,)).fetchall():
        if (r["path"], r["fingerprint"]) not in cur_fps:
            out["fixed_observations"].append(dict(r))
    return out


def run(conn, cfg, run_id, prev_run_id):
    compare_metrics(conn, run_id, prev_run_id)
    compare_observations(conn, run_id, prev_run_id)
    conn.commit()
    return diff_sets(conn, run_id, prev_run_id)


# ---------------------------------------------------------------------------
# V2: generalized comparison baselines (report-time only; stored metric rows
# always keep the previous-run comparison). Modes: previous | best |
# rolling_median | release_baseline. Reuses _classify direction semantics.
# ---------------------------------------------------------------------------
BASELINE_MODES = ("previous", "best", "rolling_median", "release_baseline")

_HISTORY_SQL = """
    SELECT m.value_numeric, m.value_text, m.grade, m.status, r.id AS run_id
    FROM metrics m
    JOIN runs r ON r.id = m.run_id
    LEFT JOIN targets t ON t.id = m.target_id
    JOIN tool_results tr ON tr.id = m.tool_result_id
    WHERE r.status = 'finished' AND r.id < ?
      AND COALESCE(t.path, '(site)') = ? AND tr.tool = ?
      AND m.category = ? AND m.metric = ?
    ORDER BY r.id DESC LIMIT ?
"""


def history(conn, run_id, key, limit):
    """Prior finished-run rows for a (path, tool, category, metric) key,
    newest first. Shared by baselines and the report's sparklines."""
    path, tool, category, metric = key
    return conn.execute(_HISTORY_SQL, (run_id, path, tool, category, metric, limit)).fetchall()


def _window(cfg):
    return int((cfg.raw.get("comparison") or {}).get("rolling_window", 5))


def _val(row):
    return {
        "value_numeric": row["value_numeric"],
        "value_text": row["value_text"],
        "grade": row["grade"],
    }


def baseline_value(conn, cfg, run_id, key, mode, comparison_mode):
    """Resolve a single baseline value dict {value_numeric, value_text, grade}
    for a metric key under `mode`, or None. Pure read, writes nothing."""
    window = _window(cfg)
    if mode == "previous":
        rows = history(conn, run_id, key, 1)
        return _val(rows[0]) if rows else None

    if mode in ("best", "rolling_median"):
        rows = history(conn, run_id, key, window)
        grades = [r["grade"] for r in rows if r["grade"]]
        nums = [r["value_numeric"] for r in rows if r["value_numeric"] is not None]
        if mode == "best":
            if grades:
                best = min(grades, key=lambda g: lib.GRADE_RANK.get(g, 99))
                return {"value_numeric": None, "value_text": best, "grade": best}
            if not nums:
                return None
            if comparison_mode == "higher_better":
                v = max(nums)
            elif comparison_mode == "lower_better":
                v = min(nums)
            else:
                return None
            return {"value_numeric": v, "value_text": None, "grade": None}
        # rolling_median
        if not nums:
            return None
        s = sorted(nums)
        mid = len(s) // 2
        med = s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2
        return {"value_numeric": med, "value_text": None, "grade": None}

    if mode == "release_baseline":
        label = (cfg.raw.get("comparison") or {}).get("release_baseline_label")
        if not label:
            return None
        r = conn.execute(
            """SELECT id FROM runs WHERE id < ? AND status = 'finished'
               AND (edition = ? OR run_label = ?) ORDER BY id DESC LIMIT 1""",
            (run_id, label, label),
        ).fetchone()
        if not r:
            return None
        path, tool, category, metric = key
        row = conn.execute(
            """SELECT m.value_numeric, m.value_text, m.grade FROM metrics m
               LEFT JOIN targets t ON t.id = m.target_id
               JOIN tool_results tr ON tr.id = m.tool_result_id
               WHERE m.run_id = ? AND COALESCE(t.path,'(site)') = ? AND tr.tool = ?
                 AND m.category = ? AND m.metric = ?""",
            (r["id"], path, tool, category, metric),
        ).fetchone()
        return _val(row) if row else None
    return None
