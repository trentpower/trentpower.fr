#!/usr/bin/env bash
# coverage_global.sh — the GLOBAL coverage number, via integration coverage.
#
# The build generators (generate_site, render_pages, generate_source_view, …) are
# never exercised by the unit suite, but the BUILD runs every one and the gate
# verifies their output. So measure them by running the build + every generator
# UNDER coverage (subprocess-captured) and combining with the unit-suite data.
# Real execution of real code paths, not hollow line-touching.
#
# Heavy + mutating: it runs a full build (mutating public/) and restores it.
#
# BEST-EFFORT DIAGNOSTIC, not the badge source. Subprocess coverage capture of
# the build is build-environment-dependent and not reliably reproducible across
# runs — the published Coverage badge uses the deterministic unit figure from
# coverage.sh (see docs/COVERAGE.md). Use this to SEE the generators exercised.
#
#   bash tools/quality/coverage_global.sh
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
mkdir -p .build/coverage .build/covsub

# subprocess capture: every python3 child auto-starts coverage in parallel mode.
printf 'import coverage\ncoverage.process_startup()\n' > .build/covsub/sitecustomize.py
cat > .build/coveragerc-global <<'EOF'
[run]
branch = True
parallel = True
source = tools
omit =
    tools/quality/tests/*
    */__pycache__/*
    # score-ledger is a LIVE-SITE network audit tool (W3C / SSL Labs / PageSpeed
    # over HTTP) — it exists to hit external services against the deployed site,
    # so unit-test coverage of it is meaningless. Excluded from the published
    # global, which measures the codebase's own unit-testable logic.
    tools/score-ledger/*
EOF

RC="$ROOT/.build/coveragerc-global"
export COVERAGE_PROCESS_START="$RC"
export PYTHONPATH="$ROOT/.build/covsub${PYTHONPATH:+:$PYTHONPATH}"
# parallel data files are written next to COVERAGE_FILE — point it under .build/
# so generator subprocesses (which chdir into public/) do NOT scatter
# .coverage.* into the published tree (where the gate would flag them).
mkdir -p "$ROOT/.build/cov"
export COVERAGE_FILE="$ROOT/.build/cov/.coverage"

python3 -m coverage erase
rm -rf "$ROOT/.build/cov"/.coverage* 2>/dev/null || true

run() { echo "  • $*"; "$@" >/dev/null 2>&1 || echo "    (non-zero — captured anyway)"; }

echo "→ unit suite under coverage"
python3 -m coverage run --parallel-mode --rcfile="$RC" -m unittest discover -s tools/quality/tests >/dev/null 2>&1 || true

echo "→ full build --check (publish-pipeline generators + gate)"
run bash tools/build/build.sh --check
echo "→ build --check --editorial (editorial generators)"
run bash tools/build/build.sh --check --editorial

echo "→ residual standalone generators (not run by the build)"
for g in _build_og_images _generate_architecture_svgs build_font_subsets \
         detect_edition_changes generate_qr generate_claims_md fetch_licensed_fonts; do
  [ -f "tools/build/$g.py" ] && run python3 "tools/build/$g.py" || true
done

echo "→ full gate WITH signature (covers inline_checks.check_gpg)"
run python3 tools/quality/gate.py --all

echo "→ combine + report"
python3 -m coverage combine --rcfile="$RC" >/dev/null 2>&1 || true
python3 -m coverage json --rcfile="$RC" -o .build/coverage/coverage.json >/dev/null 2>&1 || true
python3 -m coverage html --rcfile="$RC" >/dev/null 2>&1 || true
python3 -m coverage report --rcfile="$RC" --skip-empty 2>/dev/null | tail -1
GLOBAL="$(python3 -c "import json;print(round(json.load(open('.build/coverage/coverage.json'))['totals']['percent_covered'],1))" 2>/dev/null || echo '?')"
echo "GLOBAL: ${GLOBAL}%"

echo "→ restore the tree the build mutated"
git checkout -- public/ metadata/ tools/config/ .coveragerc 2>/dev/null || true
git clean -fdq public/ metadata/ 2>/dev/null || true
# belt-and-braces: remove any parallel data a subprocess scattered (gitignored,
# so git clean -fd would miss them; the validators walk the filesystem).
find "$ROOT" -path "$ROOT/.git" -prune -o -name '.coverage.*' -print -delete >/dev/null 2>&1 || true
# known mtime artifact: a build leaves integrity.json newer than its .sig.
touch public/integrity.json 2>/dev/null && sleep 1.1 && touch public/integrity.json.sig 2>/dev/null || true
echo "  restored: $(git status --porcelain public/ metadata/ tools/config/ | wc -l) dirty"
