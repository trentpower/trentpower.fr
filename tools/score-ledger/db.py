#!/usr/bin/env python3
"""SQLite layer for the Score Ledger.

The schema is the engineering brief's DDL verbatim (plus a small meta table for
idempotent migration). This module is the ONLY place that writes metric,
observation and evidence rows: insert_standard_result() is the single choke
point translating a validator's standard-result dict into relational rows.
"""

from __future__ import annotations

import json
import os
import sqlite3

import lib

SCHEMA_VERSION = 2

# V2 derived decision layer. Kept as a named constant so it can live in both the
# idempotent base DDL (fresh installs) and MIGRATIONS (existing v1 databases).
ACTIONS_DDL = [
    """CREATE TABLE IF NOT EXISTS actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        target_path TEXT,
        category TEXT,
        source_tool TEXT,
        related_metric TEXT,
        observation_fingerprint TEXT,
        action_key TEXT NOT NULL,
        title TEXT,
        raw_severity TEXT,
        interpreted_severity TEXT,
        confidence TEXT,
        actionability TEXT,
        impact TEXT,
        suggested_area TEXT,
        recommended_action TEXT,
        status TEXT NOT NULL,
        rationale TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(run_id) REFERENCES runs(id)
    )""",
    "CREATE INDEX IF NOT EXISTS ix_actions_run ON actions(run_id)",
    "CREATE INDEX IF NOT EXISTS ix_actions_key ON actions(run_id, action_key)",
]

# Brief's DDL, verbatim, with a meta table appended.
DDL = [
    """CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        run_label TEXT,
        edition TEXT,
        environment TEXT,
        base_url TEXT,
        git_commit TEXT,
        notes TEXT,
        status TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS targets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        url TEXT NOT NULL,
        path TEXT,
        page_key TEXT,
        language TEXT,
        page_type TEXT,
        final_url TEXT,
        status_code INTEGER,
        content_type TEXT,
        response_ms REAL,
        checked_at TEXT,
        FOREIGN KEY(run_id) REFERENCES runs(id)
    )""",
    """CREATE TABLE IF NOT EXISTS tool_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        target_id INTEGER,
        tool TEXT NOT NULL,
        status TEXT NOT NULL,
        started_at TEXT,
        finished_at TEXT,
        duration_ms INTEGER,
        tool_version TEXT,
        source_url TEXT,
        raw_json TEXT,
        raw_text TEXT,
        FOREIGN KEY(run_id) REFERENCES runs(id),
        FOREIGN KEY(target_id) REFERENCES targets(id)
    )""",
    """CREATE TABLE IF NOT EXISTS metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        target_id INTEGER,
        tool_result_id INTEGER NOT NULL,
        category TEXT NOT NULL,
        metric TEXT NOT NULL,
        value_numeric REAL,
        value_text TEXT,
        value_bool INTEGER,
        unit TEXT NOT NULL,
        grade TEXT,
        normalised_score REAL,
        comparison_mode TEXT NOT NULL,
        status TEXT NOT NULL,
        previous_value_numeric REAL,
        previous_value_text TEXT,
        delta_numeric REAL,
        direction TEXT,
        checked_at TEXT NOT NULL,
        FOREIGN KEY(run_id) REFERENCES runs(id),
        FOREIGN KEY(target_id) REFERENCES targets(id),
        FOREIGN KEY(tool_result_id) REFERENCES tool_results(id)
    )""",
    """CREATE TABLE IF NOT EXISTS observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        target_id INTEGER,
        metric_id INTEGER NOT NULL,
        severity TEXT,
        observation_type TEXT,
        code TEXT,
        title TEXT,
        message TEXT,
        selector TEXT,
        line INTEGER,
        "column" INTEGER,
        url TEXT,
        fingerprint TEXT,
        status_vs_previous TEXT,
        FOREIGN KEY(run_id) REFERENCES runs(id),
        FOREIGN KEY(target_id) REFERENCES targets(id),
        FOREIGN KEY(metric_id) REFERENCES metrics(id)
    )""",
    """CREATE TABLE IF NOT EXISTS evidence (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        observation_id INTEGER NOT NULL,
        evidence_type TEXT,
        label TEXT,
        value TEXT,
        excerpt TEXT,
        source_url TEXT,
        raw_fragment TEXT,
        FOREIGN KEY(observation_id) REFERENCES observations(id)
    )""",
    """CREATE TABLE IF NOT EXISTS meta (
        key TEXT PRIMARY KEY,
        value TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS ix_metrics_match ON metrics(run_id, metric, category)",
    "CREATE INDEX IF NOT EXISTS ix_targets_run_path ON targets(run_id, path)",
    "CREATE INDEX IF NOT EXISTS ix_obs_fp ON observations(run_id, target_id, fingerprint)",
] + ACTIONS_DDL

# Ordered, versioned migrations applied to existing databases. Each key is the
# schema_version it brings the DB up to. Fresh installs get everything from DDL
# above; existing v1 databases get only the deltas here.
MIGRATIONS = {
    2: ACTIONS_DDL,
}


def connect(cfg) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(cfg.sqlite_path), exist_ok=True)
    conn = sqlite3.connect(cfg.sqlite_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate(conn):
    """Idempotent, versioned migration.

    Base DDL is always safe to re-run (CREATE IF NOT EXISTS). For existing
    databases we then apply any MIGRATIONS strictly newer than the recorded
    schema_version and bump the marker. A brand-new DB created from DDL is
    stamped at SCHEMA_VERSION directly.
    """
    fresh = (
        conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='meta'").fetchone()
        is None
    )
    for stmt in DDL:
        conn.execute(stmt)

    row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    if row is None:
        # Fresh DB built from current DDL is already at SCHEMA_VERSION; a legacy
        # DB with no marker is treated as version 1 (its tables predate meta).
        have = SCHEMA_VERSION if fresh else 1
        conn.execute("INSERT INTO meta(key, value) VALUES('schema_version', ?)", (str(have),))
    else:
        have = int(row["value"])

    for ver in range(have + 1, SCHEMA_VERSION + 1):
        for stmt in MIGRATIONS.get(ver, []):
            conn.execute(stmt)
        conn.execute("UPDATE meta SET value = ? WHERE key = 'schema_version'", (str(ver),))
    conn.commit()


# ---------------------------------------------------------------------------
# Run / target lifecycle
# ---------------------------------------------------------------------------
def create_run(conn, *, run_label, edition, environment, base_url, git_commit, notes):
    cur = conn.execute(
        """INSERT INTO runs(started_at, run_label, edition, environment,
                            base_url, git_commit, notes, status)
           VALUES(?,?,?,?,?,?,?,?)""",
        (
            lib.now_utc_iso(),
            run_label,
            edition,
            environment,
            base_url,
            git_commit,
            notes,
            "running",
        ),
    )
    conn.commit()
    return cur.lastrowid


def finish_run(conn, run_id, status="finished"):
    conn.execute(
        "UPDATE runs SET finished_at = ?, status = ? WHERE id = ?",
        (lib.now_utc_iso(), status, run_id),
    )
    conn.commit()


def create_target(conn, run_id, url, *, page_key, language, page_type):
    cur = conn.execute(
        """INSERT INTO targets(run_id, url, path, page_key, language,
                               page_type, checked_at)
           VALUES(?,?,?,?,?,?,?)""",
        (run_id, url, lib.path_of(url), page_key, language, page_type, lib.now_utc_iso()),
    )
    conn.commit()
    return cur.lastrowid


def update_target(conn, target_id, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(
        f"UPDATE targets SET {cols} WHERE id = ?",
        (*fields.values(), target_id),
    )
    conn.commit()


def previous_run_id(conn, before):
    cur = conn.execute(
        """SELECT id FROM runs
           WHERE id < ? AND finished_at IS NOT NULL AND status = 'finished'
           ORDER BY id DESC LIMIT 1""",
        (before,),
    )
    row = cur.fetchone()
    return row["id"] if row else None


# ---------------------------------------------------------------------------
# Action Register (V2 derived decision layer)
# ---------------------------------------------------------------------------
ACTION_FIELDS = [
    "target_path",
    "category",
    "source_tool",
    "related_metric",
    "observation_fingerprint",
    "action_key",
    "title",
    "raw_severity",
    "interpreted_severity",
    "confidence",
    "actionability",
    "impact",
    "suggested_area",
    "recommended_action",
    "status",
    "rationale",
]


def previous_actions(conn, prev_run_id):
    """Map action_key -> status for the previous run (for status carryover)."""
    if prev_run_id is None:
        return {}
    rows = conn.execute(
        "SELECT action_key, status FROM actions WHERE run_id = ?", (prev_run_id,)
    ).fetchall()
    return {r["action_key"]: r["status"] for r in rows}


def replace_actions(conn, run_id, actions):
    """Idempotently set the Action Register for a run (delete then insert)."""
    conn.execute("DELETE FROM actions WHERE run_id = ?", (run_id,))
    created_at = lib.now_utc_iso()
    cols = ", ".join(["run_id"] + ACTION_FIELDS + ["created_at"])
    placeholders = ", ".join(["?"] * (len(ACTION_FIELDS) + 2))
    for a in actions:
        values = [run_id] + [a.get(f) for f in ACTION_FIELDS] + [created_at]
        conn.execute(f"INSERT INTO actions({cols}) VALUES({placeholders})", values)
    conn.commit()


# ---------------------------------------------------------------------------
# Insert a standard-result dict
# ---------------------------------------------------------------------------
def _truncate(value, limit):
    if value is None:
        return None
    s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    if limit and len(s) > limit:
        return s[:limit] + f"\n...[truncated {len(s)} chars]"
    return s


def _resolve_measurements(cfg, result):
    """Resolve unit + comparison_mode for every measurement BEFORE any write.

    Returns the list with both fields filled. Raises UnregisteredMetric if a
    metric cannot resolve a stable comparison_mode (strict taxonomy), so the
    caller can record the tool_result as unavailable instead of guessing.
    """
    resolved = []
    strict = bool(cfg.taxonomy.get("strict_metric_names", True))
    for m in result["measurements"]:
        unit = m.get("unit")
        mode = m.get("comparison_mode")
        if unit is None or mode is None:
            try:
                r_unit, r_mode = lib.registry_lookup(cfg, m["metric"])
            except lib.UnregisteredMetric:
                if strict:
                    raise
                r_unit, r_mode = "unknown", "neutral"
            unit = unit or r_unit
            mode = mode or r_mode
        if unit not in lib.UNITS:
            raise ValueError(f"bad unit {unit!r} for {m['metric']}")
        if mode not in lib.CMP_MODES:
            raise ValueError(f"bad comparison_mode {mode!r} for {m['metric']}")
        mm = dict(m)
        mm["unit"] = unit
        mm["comparison_mode"] = mode
        resolved.append(mm)
    return resolved


def insert_standard_result(conn, cfg, run_id, target_id, result):
    """Translate a validator's standard-result dict into rows.

    All measurements are resolved against the registry first; if any metric
    lacks a stable comparison_mode this raises before writing anything.
    """
    if result["status"] not in lib.STATUS:
        raise ValueError(f"bad status {result['status']!r}")

    measurements = _resolve_measurements(cfg, result)
    limit = cfg.truncate_raw_after_chars
    checked_at = lib.now_utc_iso()

    cur = conn.execute(
        """INSERT INTO tool_results(run_id, target_id, tool, status, started_at,
                                    finished_at, duration_ms, tool_version,
                                    source_url, raw_json, raw_text)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            run_id,
            target_id,
            result["tool"],
            result["status"],
            result.get("started_at"),
            result.get("finished_at"),
            result.get("duration_ms"),
            result.get("tool_version"),
            result.get("source_url"),
            _truncate(result.get("raw_json"), limit),
            _truncate(result.get("raw_text"), limit),
        ),
    )
    tool_result_id = cur.lastrowid

    metric_ids = {}
    for m in measurements:
        mc = conn.execute(
            """INSERT INTO metrics(run_id, target_id, tool_result_id, category,
                                   metric, value_numeric, value_text, value_bool,
                                   unit, grade, normalised_score, comparison_mode,
                                   status, checked_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id,
                target_id,
                tool_result_id,
                m["category"],
                m["metric"],
                m["value_numeric"],
                m["value_text"],
                m["value_bool"],
                m["unit"],
                m["grade"],
                m["normalised_score"],
                m["comparison_mode"],
                m["status"],
                checked_at,
            ),
        )
        metric_ids.setdefault(m["metric"], mc.lastrowid)

    for o in result["observations"]:
        metric_id = metric_ids.get(o.get("metric"))
        if metric_id is None:
            # Observation references no inserted metric; anchor it on a synthetic
            # status metric so the NOT NULL FK holds and it stays queryable.
            mc = conn.execute(
                """INSERT INTO metrics(run_id, target_id, tool_result_id,
                                       category, metric, value_text, unit,
                                       comparison_mode, status, checked_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id,
                    target_id,
                    tool_result_id,
                    result["tool"],
                    f"{result['tool']}.note",
                    o.get("metric"),
                    "text",
                    "neutral",
                    "ok",
                    checked_at,
                ),
            )
            metric_id = mc.lastrowid
        oc = conn.execute(
            """INSERT INTO observations(run_id, target_id, metric_id, severity,
                                        observation_type, code, title, message,
                                        selector, line, "column", url, fingerprint)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id,
                target_id,
                metric_id,
                o.get("severity"),
                o.get("observation_type"),
                o.get("code"),
                o.get("title"),
                o.get("message"),
                o.get("selector"),
                o.get("line"),
                o.get("column"),
                o.get("url"),
                o.get("fingerprint"),
            ),
        )
        obs_id = oc.lastrowid
        for ev in o.get("evidence", []):
            conn.execute(
                """INSERT INTO evidence(observation_id, evidence_type, label,
                                        value, excerpt, source_url, raw_fragment)
                   VALUES(?,?,?,?,?,?,?)""",
                (
                    obs_id,
                    ev.get("evidence_type"),
                    ev.get("label"),
                    ev.get("value"),
                    _truncate(ev.get("excerpt"), limit),
                    ev.get("source_url"),
                    _truncate(ev.get("raw_fragment"), limit),
                ),
            )
    return tool_result_id
