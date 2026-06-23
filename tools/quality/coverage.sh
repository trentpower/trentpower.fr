#!/usr/bin/env bash
# coverage.sh — three focused coverage surfaces, ENFORCED (the ratchet).
#
# This is the SINGLE test+coverage pass: it runs the whole unit suite under
# coverage (line below), so `set -euo pipefail` makes a failing test abort here
# before any floor report. CI and build.sh stage 02 rely on it alone — there is
# no separate bare `unittest` run. `make test` stays for the fast local loop.
#
# The global tools/ number is meaningless as a target — it is dragged down by
# one-shot build generators that earn integration tests later, not unit tests
# now. So measure three surfaces that DO matter, each with a floor it must not
# drop below. A surface below its floor fails the script (exit 1) so CI can gate
# on it. The per-file map in .build/coverage/coverage.json additionally feeds the
# changed-line ratchet (tools/quality/diff_coverage.py). JSON + HTML land under
# .build/ (gitignored, outside the git-metadata scan roots).
#
#   bash tools/quality/coverage.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" # tools/quality
ROOT="$(cd "$HERE/../.." && pwd)"                    # repo root
cd "$ROOT"
mkdir -p .build/coverage

# per-surface floors — single source of truth (sourced, not duplicated here).
# shellcheck source=tools/quality/coverage-floors.sh
. "$HERE/coverage-floors.sh"

# the count below measures the WORKING TREE; surface a dirty tree so the published
# counts are never silently off from what CI (a clean checkout) would measure.
DIRTY="$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
[ "${DIRTY:-0}" -gt 0 ] &&
  echo "note: measuring a dirty tree — ${DIRTY} uncommitted change(s); counts reflect the working tree, not HEAD"

python3 -m coverage erase
python3 -m coverage run --branch -m unittest discover -s tools/quality/tests

fail=0

echo
echo "── (1) convergence + seal · signing-critical · floor ${SEAL_MIN}% ──"
python3 -m coverage report --fail-under="$SEAL_MIN" \
  --include="tools/build/assert_seal_immutable.py,tools/quality/validate_sri_coherence.py,tools/lib/proc.py,tools/lib/repo.py,tools/lib/hashing.py" ||
  {
    echo "  ✗ below ${SEAL_MIN}% floor"
    fail=1
  }

echo
echo "── (2) ADR-0002 validators · floor ${ADR_MIN}% ──"
python3 -m coverage report --fail-under="$ADR_MIN" \
  --include="tools/quality/validate_*.py,tools/verify/validate_*.py" \
  --omit="tools/quality/tests/*" ||
  {
    echo "  ✗ below ${ADR_MIN}% floor"
    fail=1
  }

echo
echo "── (3) broad quality-policy · floor ${BROAD_MIN}% ──"
python3 -m coverage report --fail-under="$BROAD_MIN" \
  --include="tools/quality/*.py,tools/lib/*.py,tools/verify/*.py" \
  --omit="tools/quality/tests/*,tools/quality/gate.py,tools/quality/lint.py" ||
  {
    echo "  ✗ below ${BROAD_MIN}% floor"
    fail=1
  }

python3 -m coverage json -o .build/coverage/coverage.json
python3 -m coverage html

# Published TEST COVERAGE figure: the unit-testable-logic surface (same include/omit
# as surface 3 above) — NOT the raw global, which counts the integration-tested build
# generators. This single number drives the badge + docs (tools/badges/sync_coverage.py).
PUB_PCT="$(python3 -m coverage report \
  --include="tools/quality/*.py,tools/lib/*.py,tools/verify/*.py" \
  --omit="tools/quality/tests/*,tools/quality/gate.py,tools/quality/lint.py" \
  --format=total)"
# Source-derive the suite size + the floors in the same run, so the documented
# inventory and the advertised floor numbers (README.md + docs/*, gated by
# tools/badges/sync_coverage.py) cannot drift. The file set comes from `git
# ls-files` (TRACKED files), not a working-tree glob, so an uncommitted scratch
# test file never inflates the published count.
python3 - "$PUB_PCT" "$SEAL_MIN" "$ADR_MIN" "$BROAD_MIN" <<'PY'
import json, re, subprocess, sys
from pathlib import Path

pct = float(sys.argv[1])
seal, adr, broad = (int(sys.argv[i]) for i in (2, 3, 4))

tracked = subprocess.run(
    ["git", "ls-files", "tools/quality/tests/"],
    capture_output=True, text=True,
).stdout.splitlines()
files = sorted(
    Path(p) for p in tracked if p and Path(p).name.startswith("test_") and p.endswith(".py")
)
fn_re = re.compile(r"^\s*def test_", re.MULTILINE)
funcs = sum(len(fn_re.findall(f.read_text(encoding="utf-8"))) for f in files)

Path(".build/coverage/coverage-summary.json").write_text(
    json.dumps(
        {
            "test_coverage_pct": round(pct),
            "surface": "unit-testable-logic",
            "raw": round(pct, 2),
            "test_files": len(files),
            "test_functions": funcs,
            "floors": {"seal": seal, "adr": adr, "broad": broad},
        }
    )
    + "\n",
    encoding="utf-8",
)
PY
echo
echo "json: .build/coverage/coverage.json · html: .build/coverage/html/index.html"
echo "summary: .build/coverage/coverage-summary.json · TEST COVERAGE ${PUB_PCT}% (unit-testable-logic)"

if [ "$fail" -ne 0 ]; then
  echo "FAIL: a coverage surface dropped below its floor (see ✗ above)."
  exit 1
fi
echo "OK: all coverage surfaces at or above floor (${SEAL_MIN}/${ADR_MIN}/${BROAD_MIN})."
