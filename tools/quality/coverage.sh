#!/usr/bin/env bash
# coverage.sh — three focused coverage reports (measure-only).
#
# The global tools/ number is meaningless as a target — it is dragged down by
# one-shot build generators that earn integration tests later, not unit tests
# now. So report three surfaces that DO matter, each with its own target, off a
# single suite run. Measurement only: no --fail-under here (the ratchet is wired
# once each surface is at target — see .coveragerc). JSON + HTML land under
# .build/ (gitignored, outside the git-metadata scan roots).
#
#   bash tools/quality/coverage.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
mkdir -p .build/coverage

python3 -m coverage erase
python3 -m coverage run --branch -m unittest discover -s tools/quality/tests

# (1) convergence + seal — signing-critical (the seal-immutability guard, the
# SRI-coherence gate, and the seams they cross). MUST be strong. Target 90%+.
# snapshot_tree (in public_tree.py) is covered by its own test; public_tree.py
# is excluded here because the file is dominated by the unrelated build-walker.
echo
echo "── (1) convergence + seal · signing-critical · target 90%+ ──"
python3 -m coverage report -m --include="tools/build/assert_seal_immutable.py,tools/quality/validate_sri_coherence.py,tools/lib/proc.py,tools/lib/repo.py,tools/lib/hashing.py"

# (2) ADR-0002 validators — policy-as-code; should prove clean + defect cases.
# Target 90%+ (ongoing ratchet as validators are hardened).
echo
echo "── (2) ADR-0002 validators · target 90%+ ──"
python3 -m coverage report --include="tools/quality/validate_*.py,tools/verify/validate_*.py" --omit="tools/quality/tests/*"

# (3) broad quality-policy — good discipline, advisory. Target 85%.
echo
echo "── (3) broad quality-policy · advisory · target 85% ──"
python3 -m coverage report --include="tools/quality/*.py,tools/lib/*.py,tools/verify/*.py" --omit="tools/quality/tests/*,tools/quality/gate.py,tools/quality/lint.py"

python3 -m coverage json -o .build/coverage/coverage.json
python3 -m coverage html
echo
echo "json: .build/coverage/coverage.json · html: .build/coverage/html/index.html"
