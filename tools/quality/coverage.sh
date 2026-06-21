#!/usr/bin/env bash
# coverage.sh — broad quality-policy coverage report (measure-only).
#
# Runs the whole unittest suite under coverage.py and reports over the policy
# surface declared in .coveragerc (tools/build, quality, lib, verify; tests +
# gate/lint runners omitted). Reports only — no fail-under here; see the ratchet
# note in .coveragerc. HTML lands in reports/coverage/html (gitignored).
#
#   bash tools/quality/coverage.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

python3 -m coverage erase
python3 -m coverage run -m unittest discover -s tools/quality/tests
echo
echo "── broad quality-policy coverage (tools/build · quality · lib · verify) ──"
python3 -m coverage report
python3 -m coverage html
echo "html: reports/coverage/html/index.html"
