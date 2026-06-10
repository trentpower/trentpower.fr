#!/usr/bin/env python3
"""check_report.py -- the neutral machine-readable report contract.

This module owns the JSON envelope shape the check runners write.
It is deliberately *neutral*: it knows nothing about checks or audits, only
about the envelope. Producers convert their own results into the small dict
shapes below and call the matching builder.

Two producers consume it today:
  - tools/lib/checks.py (via tools/gate.py and tools/lint.py) -> build_check_report
  - tools/score-ledger (post-deploy live audit)           -> build_audit_report

Keeping the envelope here -- rather than inside checks.py -- means the
score-ledger audit can share the exact same head (schema_version,
generated_at, command, status, summary) without depending on the check
runner. checks.py owns checks; score-ledger is not a check runner; the
contract belongs to neither and so lives on its own.

The canonical prose definition is docs/GATES-CHECKS-AND-QUALITY.md §5.

All reports are local-only runtime artefacts written under reports/checks/.
They carry a real wall-clock timestamp, are gitignored, and never enter
public/ or a release archive.
"""

from __future__ import annotations

import datetime
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string with a trailing Z (no micros)."""
    return datetime.datetime.now(datetime.UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_write_json(obj: Any, path: str | os.PathLike) -> Path:
    """Serialize obj to path as pretty JSON, atomically.

    Writes to a temp file in the same directory and os.replace()s it into
    place so a reader never observes a half-written report. Parent dirs are
    created as needed.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=p.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, p)
    except BaseException:
        # leave no partial file behind on any failure.
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    return p


def summarise_results(checks: Sequence[Mapping[str, Any]]) -> dict:
    """Roll a list of per-check dicts into the report summary.

    Each check dict is expected to carry: ``status`` ("passed"|"failed"),
    ``tier`` ("blocking"|"advisory") and ``duration_ms`` (number).

    A failed blocking check counts as ``failed`` (it would block a deploy);
    a failed advisory check counts as ``warnings`` (visible, never blocking).
    """
    passed = failed = warnings = 0
    duration_ms = 0
    for c in checks:
        duration_ms += int(c.get("duration_ms", 0) or 0)
        if c.get("status") == "passed":
            passed += 1
        elif c.get("tier") == "advisory":
            warnings += 1
        else:
            failed += 1
    return {
        "passed": passed,
        "failed": failed,
        "warnings": warnings,
        "duration_ms": duration_ms,
    }


def build_check_report(command: str, checks: Sequence[Mapping[str, Any]]) -> dict:
    """Build a gate/lint report envelope from per-check dicts.

    Top-level ``status`` is "failed" iff at least one *blocking* check failed;
    advisory failures surface as ``summary.warnings`` and never flip status.
    """
    summary = summarise_results(checks)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "command": command,
        "status": "failed" if summary["failed"] > 0 else "passed",
        "summary": summary,
        "checks": list(checks),
    }


def build_audit_report(
    command: str,
    run: Mapping[str, Any],
    scorecards: Sequence[Mapping[str, Any]],
    headline_metrics: Sequence[Mapping[str, Any]],
    open_actions: Sequence[Mapping[str, Any]],
) -> dict:
    """Build a post-deploy audit report envelope (score-ledger producer).

    The head (schema_version / generated_at / command / status / summary)
    matches build_check_report so every report reads the same way.
    ``status`` is "failed" iff any scorecard is FAIL -- but this is a *report*
    signal only; the audit is observational and never gates a deploy. Each
    scorecard dict carries ``status`` in {"PASS","REVIEW","FAIL"}.
    """
    passed = sum(1 for s in scorecards if str(s.get("status")).upper() == "PASS")
    warnings = sum(1 for s in scorecards if str(s.get("status")).upper() == "REVIEW")
    failed = sum(1 for s in scorecards if str(s.get("status")).upper() == "FAIL")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "command": command,
        "status": "failed" if failed > 0 else "passed",
        "summary": {"passed": passed, "failed": failed, "warnings": warnings},
        "run": dict(run),
        "scorecards": list(scorecards),
        "headline_metrics": list(headline_metrics),
        "open_actions": list(open_actions),
    }
