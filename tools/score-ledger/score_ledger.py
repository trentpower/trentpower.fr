#!/usr/bin/env python3
"""trentpower.fr Score Ledger - CLI orchestrator.

Thin entrypoint only: it loads config, drives the run loop, then delegates to
db / validators / compare / report. No validation logic lives here.

Commands:
    run [--label "..."]   collect a new timestamped run and write reports
    report [--latest]     regenerate Markdown + HTML for the latest run
    compare [--latest]    print the latest run's changes vs the previous run
    history               list past runs
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from urllib.parse import urlsplit, urlunsplit

import attest
import compare
import db
import lib
import report
import triage
import validators

# The check report contract lives in tools/lib/check_report.py. Import it so
# the post-deploy audit emits the same envelope as gate/lint. See
# docs/GATES-CHECKS-AND-QUALITY.md §5.
sys.path.insert(0, os.path.join(os.path.dirname(lib.HERE), "lib"))
import check_report  # noqa: E402

_REPO_ROOT = os.path.dirname(os.path.dirname(lib.HERE))
_DEFAULT_AUDIT_JSON = os.path.join(_REPO_ROOT, "reports", "checks", "last-audit.json")


def _page_meta(path):
    seg = [s for s in path.split("/") if s]
    if not seg:
        return "root", "en", "home"
    key = seg[0]
    language = "fr" if key == "fr" else ("en" if key in ("en-au", "en") else key)
    return key, language, "edition"


def _origin(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, "", "", ""))


def _git_commit():
    try:
        out = subprocess.run(
            ["git", "-C", lib.HERE, "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def _availability_into_target(conn, target_id, result):
    """Mirror availability headline values onto the target row."""
    fields = {}
    for m in result.get("measurements", []):
        if m["metric"] == "availability.status_code":
            fields["status_code"] = (
                int(m["value_numeric"]) if m["value_numeric"] is not None else None
            )
        elif m["metric"] == "availability.response_ms":
            fields["response_ms"] = m["value_numeric"]
        elif m["metric"] == "availability.content_type":
            fields["content_type"] = m["value_text"]
        elif m["metric"] == "availability.final_url":
            fields["final_url"] = m["value_text"]
    if fields:
        db.update_target(conn, target_id, **fields)


def execute_run(cfg, conn, label):
    base_url = _origin(cfg.targets[0]) if cfg.targets else None
    run_id = db.create_run(
        conn,
        run_label=label,
        edition=label,
        environment="production",
        base_url=base_url,
        git_commit=_git_commit(),
        notes=f"python={sys.version.split()[0]}; validators={','.join(validators.enabled(cfg))}",
    )

    http = lib.http_session(cfg)
    tools = validators.enabled(cfg)
    print(f"Run #{run_id} - {len(cfg.targets)} targets x {len(tools)} validators")

    for url in cfg.targets:
        page_key, language, page_type = _page_meta(lib.path_of(url))
        target_id = db.create_target(
            conn, run_id, url, page_key=page_key, language=language, page_type=page_type
        )
        print(f"  {url}")
        for tool in tools:
            res = validators.dispatch(tool, url, cfg, http)
            if tool == validators.availability.TOOL:
                _availability_into_target(conn, target_id, res)
            try:
                db.insert_standard_result(conn, cfg, run_id, target_id, res)
                mark = res["status"]
            except (lib.UnregisteredMetric, ValueError) as e:
                # cannot produce a clean shape -> record unavailable, do not guess
                fallback = lib.result(
                    url,
                    tool,
                    "unavailable",
                    raw_json={"insert_error": type(e).__name__, "detail": str(e)},
                )
                fallback.update(
                    {k: res.get(k) for k in ("started_at", "finished_at", "duration_ms")}
                )
                db.insert_standard_result(conn, cfg, run_id, target_id, fallback)
                mark = "unavailable(schema)"
            print(f"    - {tool}: {mark}")
        conn.commit()  # per-target commit isolates partial failures

    # site-level external integrations (real validator if enabled, else manual)
    if cfg.checks.get("manual", True):
        print("  integrations (site-level):")
        site_results = validators.site_level_results(cfg, http)
        for res in site_results:
            db.insert_standard_result(conn, cfg, run_id, None, res)
            print(f"    - {res['tool']}: {res['status']}")
        conn.commit()

    # browser pass (Playwright): sequential, after Lighthouse has finished, never
    # concurrent. Each validator runs per target; one Chromium at a time.
    browser_tools = validators.browser_enabled(cfg)
    if browser_tools:
        print("  browser pass (sequential):")
        target_ids = {
            r["url"]: r["id"]
            for r in conn.execute(
                "SELECT id, url FROM targets WHERE run_id = ?", (run_id,)
            ).fetchall()
        }
        for url in cfg.targets:
            tid = target_ids.get(url)
            for tool in browser_tools:
                res = validators.dispatch_browser(tool, url, cfg)
                db.insert_standard_result(conn, cfg, run_id, tid, res)
                print(f"    - {tool} {lib.path_of(url)}: {res['status']}")
            conn.commit()

    db.finish_run(conn, run_id)
    prev_run_id = db.previous_run_id(conn, run_id)
    compare.run(conn, cfg, run_id, prev_run_id)  # must precede triage
    actions = triage.run(conn, cfg, run_id, prev_run_id)
    print(
        f"  actions: {sum(1 for a in actions if a['status'] != 'known_noise')} actionable, "
        f"{sum(1 for a in actions if a['status'] == 'known_noise')} known-noise"
    )
    written = report.generate(conn, cfg, run_id)
    print(f"Run #{run_id} finished. Reports: " + ", ".join(written))
    return run_id


def _latest_run_id(conn):
    row = conn.execute(
        "SELECT id FROM runs WHERE status = 'finished' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return row["id"] if row else None


def cmd_run(args):
    cfg = lib.load_config(args.config)
    conn = db.connect(cfg)
    db.migrate(conn)
    execute_run(cfg, conn, args.label)
    conn.close()
    return 0


def _audit_report(conn, cfg, run_id):
    """Build the audit envelope from report.gather (read-only).

    Reuses the data report.py already assembles -- scorecards, headline metrics
    (with previous/best/rolling_median baselines), open actions and run
    metadata -- and serializes it through check_report.build_audit_report so
    the post-deploy audit reads identically to gate/lint. Observational only:
    the envelope status never gates a deploy.
    """
    data = report.gather(conn, cfg, run_id)
    run = data["run"]
    run_meta = {
        "run_id": run_id,
        "started_at": run["started_at"],
        "finished_at": run["finished_at"],
        "git_commit": run["git_commit"],
        "label": run["run_label"],
        "targets": [t["url"] for t in data["targets"]],
    }
    scorecards = [
        {
            "name": c["name"],
            "status": c["status"],
            "direction": c["direction"],
            "top_driver": c["top_driver"],
        }
        for c in data["scorecards"]
    ]
    headline = []
    for h in data["headline"]:
        b = h.get("baselines", {})
        headline.append(
            {
                "metric": h["metric"],
                "path": h["path"],
                "value": h["cur"],
                "previous": b.get("previous"),
                "best": b.get("best"),
                "rolling_median": b.get("rolling_median"),
                "comparison_mode": h["comparison_mode"],
                "direction": h["direction"],
            }
        )
    action_keys = (
        "action_key",
        "impact",
        "confidence",
        "actionability",
        "status",
        "title",
        "summary",
        "recommendation",
        "detail",
    )
    open_actions = [
        {k: a[k] for k in action_keys if k in a.keys()}
        for a in report._next_actions(data, limit=20)
    ]
    return check_report.build_audit_report("audit", run_meta, scorecards, headline, open_actions)


def cmd_report(args):
    cfg = lib.load_config(args.config)
    conn = db.connect(cfg)
    db.migrate(conn)
    run_id = _latest_run_id(conn)
    if run_id is None:
        print("No finished runs yet.")
        return 1
    written = report.generate(conn, cfg, run_id)
    print("Wrote: " + ", ".join(written))
    if getattr(args, "json", None) is not None:
        out = _DEFAULT_AUDIT_JSON if args.json == "__DEFAULT__" else args.json
        check_report.atomic_write_json(_audit_report(conn, cfg, run_id), out)
        print(f"Audit report: {out}")
    conn.close()
    return 0


def cmd_compare(args):
    cfg = lib.load_config(args.config)
    conn = db.connect(cfg)
    db.migrate(conn)
    run_id = _latest_run_id(conn)
    if run_id is None:
        print("No finished runs yet.")
        return 1
    data = report.gather(conn, cfg, run_id)
    improvements, declines, changed = report._changes(data)
    print(
        f"Run #{run_id} vs Run #{data['prev_run_id']}"
        if data["prev_run_id"]
        else f"Run #{run_id} (baseline, no previous run)"
    )
    if data["is_first"]:
        print("Baseline run - nothing to compare.")
        conn.close()
        return 0
    print(
        f"improved {data['dir_counts'].get('improved', 0)}, "
        f"declined {data['dir_counts'].get('declined', 0)}, "
        f"unchanged {data['dir_counts'].get('unchanged', 0)}, "
        f"new {data['dir_counts'].get('new', 0)}, "
        f"missing {data['dir_counts'].get('missing', 0)}"
    )
    for m in improvements[:20]:
        print(f"  [+] {m['path']} {m['metric']} {report._prev_val(m)} -> {report._fmt_val(m)}")
    for m in declines[:20]:
        print(f"  [-] {m['path']} {m['metric']} {report._prev_val(m)} -> {report._fmt_val(m)}")
    for m in changed[:20]:
        print(f"  [changed] {m['path']} {m['metric']}")
    conn.close()
    return 0


def cmd_history(args):
    cfg = lib.load_config(args.config)
    conn = db.connect(cfg)
    db.migrate(conn)
    rows = conn.execute(
        """SELECT r.id, r.started_at, r.finished_at, r.run_label, r.status,
                  (SELECT COUNT(*) FROM metrics m WHERE m.run_id = r.id) AS metric_count
           FROM runs r ORDER BY r.id DESC"""
    ).fetchall()
    if not rows:
        print("No runs yet.")
        return 0
    print(f"{'run':>4}  {'started_at':<20}  {'status':<10}  {'metrics':>7}  label")
    for r in rows:
        print(
            f"{r['id']:>4}  {r['started_at']:<20}  {r['status']:<10}  "
            f"{r['metric_count']:>7}  {r['run_label'] or ''}"
        )
    conn.close()
    return 0


def _latest_or_exit(conn):
    rid = _latest_run_id(conn)
    if rid is None:
        print("No finished runs yet.")
    return rid


def cmd_testresults(args):
    cfg = lib.load_config(args.config)
    conn = db.connect(cfg)
    db.migrate(conn)
    run_id = args.run if getattr(args, "run", None) else _latest_run_id(conn)
    if run_id is None:
        print("No finished runs yet.")
        return 1
    text = attest.build_testresults(conn, cfg, run_id, args.edition)
    out = args.out or os.path.join(cfg.reports_dir, "TESTRESULTS.txt")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    conn.close()
    edition = args.edition or "<edition>"
    print(f"Wrote {out}")
    print("")
    print("To sign:    python3 score_ledger.py sign-testresults --file " + out)
    print("To publish in a release (manual, deliberate step):")
    print(f"  cp {out} {out}.sig  public/integrity/releases/{edition}/")
    print("  add TESTRESULTS.txt + TESTRESULTS.txt.sig to that release's")
    print("  release.json manifests{} and to metadata/archive-baseline.json")
    print("  (the score-ledger never writes into public/ itself).")
    return 0


def cmd_sign_testresults(args):
    cfg = lib.load_config(args.config)
    try:
        sig = attest.sign_file(cfg, args.file)
    except Exception as e:
        print(f"Signing failed (TESTRESULTS.txt left intact): {e}")
        return 1
    print(f"Signed -> {sig}")
    return 0


def cmd_verify_testresults(args):
    cfg = lib.load_config(args.config)
    ok, msg = attest.verify_file(cfg, args.file, args.sig)
    print(("OK: " if ok else "FAIL: ") + msg)
    return 0 if ok else 1


def main(argv=None):
    parser = argparse.ArgumentParser(prog="score_ledger", description="trentpower.fr Score Ledger")
    parser.add_argument("--config", default=None, help="path to config.yml")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="collect a new run")
    p_run.add_argument("--label", default=None, help="human label for this run")
    p_run.set_defaults(func=cmd_run)

    p_rep = sub.add_parser("report", help="regenerate reports for the latest run")
    p_rep.add_argument("--latest", action="store_true", help="(default) latest run")
    p_rep.add_argument(
        "--json",
        nargs="?",
        const="__DEFAULT__",
        default=None,
        metavar="PATH",
        help="also write the audit report (default: reports/checks/last-audit.json)",
    )
    p_rep.set_defaults(func=cmd_report)

    p_cmp = sub.add_parser("compare", help="print latest vs previous changes")
    p_cmp.add_argument("--latest", action="store_true", help="(default) latest run")
    p_cmp.set_defaults(func=cmd_compare)

    p_his = sub.add_parser("history", help="list past runs")
    p_his.set_defaults(func=cmd_history)

    p_tr = sub.add_parser("testresults", help="generate a signed-attestation TESTRESULTS.txt")
    p_tr.add_argument("--latest", action="store_true", help="(default) latest run")
    p_tr.add_argument("--run", type=int, default=None, help="pin a specific run id")
    p_tr.add_argument("--edition", default=None, help="edition label, e.g. 2026-05-29")
    p_tr.add_argument("--out", default=None, help="output path (default reports/TESTRESULTS.txt)")
    p_tr.set_defaults(func=cmd_testresults)

    p_sg = sub.add_parser("sign-testresults", help="GPG detach-sign a TESTRESULTS.txt")
    p_sg.add_argument("--file", required=True, help="path to TESTRESULTS.txt")
    p_sg.set_defaults(func=cmd_sign_testresults)

    p_vf = sub.add_parser("verify-testresults", help="verify a TESTRESULTS.txt signature")
    p_vf.add_argument("--file", required=True, help="path to TESTRESULTS.txt")
    p_vf.add_argument("--sig", required=True, help="path to TESTRESULTS.txt.sig")
    p_vf.set_defaults(func=cmd_verify_testresults)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
