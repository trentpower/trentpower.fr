#!/usr/bin/env bash
# coverage.sh — three focused coverage surfaces, ENFORCED (the ratchet).
#
# The global tools/ number is meaningless as a target — it is dragged down by
# one-shot build generators that earn integration tests later, not unit tests
# now. So measure three surfaces that DO matter, each with a floor it must not
# drop below. A surface below its floor fails the script (exit 1) so CI can gate
# on it. JSON + HTML land under .build/ (gitignored, outside the git-metadata
# scan roots).
#
#   bash tools/quality/coverage.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
mkdir -p .build/coverage

# per-surface floors (the ratchet). raise these as coverage climbs; never lower.
SEAL_MIN=90    # convergence + seal — signing-critical (currently ~98%)
ADR_MIN=90     # ADR-0002 validators (currently ~98%)
BROAD_MIN=85   # broad quality-policy (currently ~94%)

python3 -m coverage erase
python3 -m coverage run --branch -m unittest discover -s tools/quality/tests

fail=0

echo
echo "── (1) convergence + seal · signing-critical · floor ${SEAL_MIN}% ──"
python3 -m coverage report --fail-under="$SEAL_MIN" \
  --include="tools/build/assert_seal_immutable.py,tools/quality/validate_sri_coherence.py,tools/lib/proc.py,tools/lib/repo.py,tools/lib/hashing.py" \
  || { echo "  ✗ below ${SEAL_MIN}% floor"; fail=1; }

echo
echo "── (2) ADR-0002 validators · floor ${ADR_MIN}% ──"
python3 -m coverage report --fail-under="$ADR_MIN" \
  --include="tools/quality/validate_*.py,tools/verify/validate_*.py" \
  --omit="tools/quality/tests/*" \
  || { echo "  ✗ below ${ADR_MIN}% floor"; fail=1; }

echo
echo "── (3) broad quality-policy · floor ${BROAD_MIN}% ──"
python3 -m coverage report --fail-under="$BROAD_MIN" \
  --include="tools/quality/*.py,tools/lib/*.py,tools/verify/*.py" \
  --omit="tools/quality/tests/*,tools/quality/gate.py,tools/quality/lint.py" \
  || { echo "  ✗ below ${BROAD_MIN}% floor"; fail=1; }

python3 -m coverage json -o .build/coverage/coverage.json
python3 -m coverage html

# Published TEST COVERAGE figure: the unit-testable-logic surface (same include/omit
# as surface 3 above) — NOT the raw global, which counts the integration-tested build
# generators. This single number drives the badge + docs (tools/badges/sync_coverage.py).
PUB_PCT="$(python3 -m coverage report \
  --include="tools/quality/*.py,tools/lib/*.py,tools/verify/*.py" \
  --omit="tools/quality/tests/*,tools/quality/gate.py,tools/quality/lint.py" \
  --format=total)"
python3 -c "import json,sys;p=float(sys.argv[1]);open('.build/coverage/coverage-summary.json','w').write(json.dumps({'test_coverage_pct':round(p),'surface':'unit-testable-logic','raw':round(p,2)})+'\n')" "$PUB_PCT"
echo
echo "json: .build/coverage/coverage.json · html: .build/coverage/html/index.html"
echo "summary: .build/coverage/coverage-summary.json · TEST COVERAGE ${PUB_PCT}% (unit-testable-logic)"

if [ "$fail" -ne 0 ]; then
  echo "FAIL: a coverage surface dropped below its floor (see ✗ above)."
  exit 1
fi
echo "OK: all coverage surfaces at or above floor (${SEAL_MIN}/${ADR_MIN}/${BROAD_MIN})."
