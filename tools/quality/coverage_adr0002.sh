#!/usr/bin/env bash
# coverage_adr0002.sh — focused coverage for the ADR-0002 surface (measure-only).
#
# Narrows the report to the modules whose coverage actually matters for the
# migration's intent: the ADR-0002 validators (the deep modules tested through
# evaluate()), the injected seams they cross, and the convergence-critical
# guards. This is where a coverage ratchet (90%+) will eventually bite — kept
# report-only until the numbers are known, to avoid coverage theatre.
#
#   bash tools/quality/coverage_adr0002.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# the ADR-0002 surface: every migrated validator + the Repo/Proc seams + the
# convergence-critical guards (seal immutability, SRI coherence). NOT the whole
# tools/ tree — wrappers and one-off scripts are out of scope on purpose.
INCLUDE="tools/quality/validate_*.py,tools/verify/validate_*.py,tools/lib/repo.py,tools/lib/proc.py,tools/lib/public_tree.py,tools/build/assert_seal_immutable.py"

python3 -m coverage erase
python3 -m coverage run -m unittest discover -s tools/quality/tests
echo
echo "── ADR-0002 validators + seams + convergence guards ──"
python3 -m coverage report --include="$INCLUDE"
