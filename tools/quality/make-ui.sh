#!/usr/bin/env bash
# make-ui.sh — the terminal ceremony for `make`. Wraps each developer activity in
# the same term.sh presentation as build.sh: the trentpower.fr wordmark on top,
# then a summary panel (default) or a full per-file table (DETAIL=full) for the
# runners, or a spinner + result for the quieter ones.
#
# Presentation only: it runs the SAME underlying scripts CI runs and preserves
# their exit codes, so "green locally == green in CI" is unchanged. Python decides
# truth (and emits JSON); this shell renders it.
#
#   bash tools/quality/make-ui.sh <activity>          # summary
#   DETAIL=full bash tools/quality/make-ui.sh <activity>
set -uo pipefail

ACTIVITY="${1:-}"
DETAIL="${DETAIL:-summary}"
RENDER_FORCE=""
ASCII=0
for arg in "$@"; do
  case "$arg" in
  --plain) RENDER_FORCE="plain" ;;
  --ascii) ASCII=1 ;;
  esac
done

TOOLS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$TOOLS_DIR/.." && pwd)"
cd "$REPO_ROOT" || exit 1
PY="python3"

# ── render mode + presentation library (mirrors build.sh / doctor.sh) ────────
# shellcheck source=tools/build/term.sh
. "$TOOLS_DIR/build/term.sh"
t_init "$RENDER_FORCE" "$ASCII" 0

ms() { # pretty-print milliseconds
  local n="$1"
  if [ "$n" -ge 1000 ]; then printf '%d.%01ds' $((n / 1000)) $(((n % 1000) / 100)); else printf '%dms' "$n"; fi
}

# ── shared renderer for gate.py / lint.py JSON reports ───────────────────────
render_checks() { # $1=report.json  $2=title
  local report="$1" title="$2"
  local stream
  stream="$(
    $PY - "$report" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
s = r["summary"]
print("SUM\t%d\t%d\t%d\t%d" % (s["passed"], s["failed"], s.get("warnings", 0), s["duration_ms"]))
for c in r["checks"]:
    st = "passed" if c["status"] == "passed" else ("warn" if c.get("tier") == "advisory" else "failed")
    print("ROW\t%s\t%s\t%s\t%d" % (c.get("category", ""), c.get("id", ""), st, c.get("duration_ms", 0)))
PY
  )"
  local passed=0 failed=0 warns=0 dur=0
  while IFS=$'\t' read -r kind a b c d; do
    [ "$kind" = SUM ] && {
      passed="$a"
      failed="$b"
      warns="$c"
      dur="$d"
    }
  done <<<"$stream"

  if [ "$DETAIL" = full ]; then
    printf '\n'
    t_table_open "Category" "Check" "Status" "Time"
    while IFS=$'\t' read -r kind a b c d; do
      [ "$kind" = ROW ] && t_table_row "$a" "$b" "$c" "$(ms "$d")"
    done <<<"$stream"
    t_table_close
  fi

  # failing rows always called out
  while IFS=$'\t' read -r kind a b c d; do
    [ "$kind" = ROW ] && [ "$c" = failed ] && t_say fail "   $(t_mark fail) ${a} · ${b}"
  done <<<"$stream"

  printf '\n'
  t_panel_open "$title"
  t_panel_row "Passed" "$passed" ok
  [ "$warns" -gt 0 ] && t_panel_row "Warnings" "$warns" warn
  t_panel_row "Failed" "$failed" "$([ "$failed" -gt 0 ] && echo fail || echo ink_dim)"
  t_panel_row "Time" "$(ms "$dur")"
  t_panel_close
}

# ── shared renderer for run_suite.py JSON reports ────────────────────────────
render_tests() { # $1=report.json  $2=title
  local report="$1" title="$2" stream
  stream="$(
    $PY - "$report" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
s = r["summary"]
print("SUM\t%d\t%d\t%d\t%d" % (s["tests"], s["passed"], s["failed"] + s["errors"], s["ms"]))
for f in r["files"]:
    bad = f["failed"] + f["errors"]
    print("ROW\t%s\t%d\t%d\t%s\t%d" % (f["file"], f["tests"], f["passed"], ("fail" if bad else "pass"), f["ms"]))
PY
  )"
  local tests=0 passed=0 failed=0 dur=0
  while IFS=$'\t' read -r kind a b c d; do
    [ "$kind" = SUM ] && {
      tests="$a"
      passed="$b"
      failed="$c"
      dur="$d"
    }
  done <<<"$stream"

  if [ "$DETAIL" = full ]; then
    printf '\n'
    t_table_open "Test file" "Tests" "Pass" "Status" "Time"
    while IFS=$'\t' read -r kind a b c st d; do
      [ "$kind" = ROW ] && t_table_row "$a" "$b" "$c" "$st" "$(ms "$d")"
    done <<<"$stream"
    t_table_close
  else
    while IFS=$'\t' read -r kind a b c st d; do
      [ "$kind" = ROW ] && [ "$st" = fail ] && t_say fail "   $(t_mark fail) ${a}"
    done <<<"$stream"
  fi

  printf '\n'
  t_panel_open "$title"
  t_panel_row "Tests" "$tests"
  t_panel_row "Passed" "$passed" ok
  t_panel_row "Failed" "$failed" "$([ "$failed" -gt 0 ] && echo fail || echo ink_dim)"
  t_panel_row "Time" "$(ms "$dur")"
  t_panel_close
}

# ── coverage table from the coverage.json the run already wrote ──────────────
render_coverage() {
  local cov=".build/coverage/coverage.json" sum=".build/coverage/coverage-summary.json"
  [ -f "$sum" ] || return 0
  if [ "$DETAIL" = full ] && [ -f "$cov" ]; then
    printf '\n'
    t_table_open "Source file" "Stmts" "Miss" "Cover"
    while IFS=$'\t' read -r f st miss pct; do
      t_table_row "$f" "$st" "$miss" "${pct}%"
    done < <(
      $PY - "$cov" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
rows = []
for path, fd in d.get("files", {}).items():
    s = fd["summary"]
    rows.append((s["percent_covered"], path, s["num_statements"], s["missing_lines"]))
for pct, path, st, miss in sorted(rows):
    print("%s\t%d\t%d\t%d" % (path, st, miss, round(pct)))
PY
    )
    t_table_close
  fi
  printf '\n'
  local pct files funcs
  pct="$($PY -c "import json;print(json.load(open('$sum'))['test_coverage_pct'])" 2>/dev/null || echo '?')"
  files="$($PY -c "import json;print(json.load(open('$sum'))['test_files'])" 2>/dev/null || echo '?')"
  funcs="$($PY -c "import json;print(json.load(open('$sum'))['test_functions'])" 2>/dev/null || echo '?')"
  t_panel_open "COVERAGE"
  t_panel_row "TEST COVERAGE" "${pct}%" ok
  t_panel_row "Suite" "${funcs} tests · ${files} files"
  t_panel_sub "floors"
  t_panel_row "seal / ADR / broad" "${SEAL_MIN}/${ADR_MIN}/${BROAD_MIN}" ok
  t_panel_close
}

# ── generic wrap: spinner around a command, output shown only on failure ─────
generic() { # $1=label  rest=command
  local label="$1"
  shift
  t_run "$label" -- "$@"
}

header() { # $1=subtitle
  t_logo
  printf '\n'
  t_banner "MAKE · ${1}" "trentpower.fr developer commands"
  printf '\n'
}

rc=0
case "$ACTIVITY" in
test | test-fast)
  fast=""
  [ "$ACTIVITY" = test-fast ] && fast="--fast"
  header "${ACTIVITY}"
  report="$(mktemp)"
  t_spin_start "running the unit suite${fast:+ (fast tier)}"
  out="$($PY tools/quality/tests/run_suite.py $fast --json "$report" 2>&1)"
  rc=$?
  t_spin_stop "$([ "$rc" -eq 0 ] && echo pass || echo fail)" "unit suite"
  render_tests "$report" "UNIT TESTS"
  [ "$rc" -ne 0 ] && [ -n "$out" ] && printf '%s\n' "$out"
  rm -f "$report"
  ;;
gate | lint)
  prog="gate.py"
  title="BLOCKING GATE"
  [ "$ACTIVITY" = lint ] && {
    prog="lint.py"
    title="ADVISORY LINT"
  }
  header "${ACTIVITY}"
  report="$(mktemp)"
  t_spin_start "running ${ACTIVITY}"
  out="$($PY "tools/quality/${prog}" --json "$report" 2>&1)"
  rc=$?
  t_spin_stop "$([ "$rc" -eq 0 ] && echo pass || echo fail)" "${ACTIVITY}"
  if [ -s "$report" ]; then
    render_checks "$report" "$title"
  else
    printf '%s\n' "$out"
  fi
  rm -f "$report"
  ;;
coverage)
  header "coverage"
  # shellcheck source=tools/quality/coverage-floors.sh
  . "$TOOLS_DIR/quality/coverage-floors.sh"
  t_spin_start "measuring coverage (single pass)"
  out="$(bash tools/quality/coverage.sh 2>&1)"
  rc=$?
  t_spin_stop "$([ "$rc" -eq 0 ] && echo pass || echo fail)" "coverage ratchet"
  render_coverage
  [ "$rc" -ne 0 ] && printf '%s\n' "$out" | sed 's/^/   /' | tail -8
  ;;
preflight)
  header "preflight"
  base="${PREFLIGHT_BASE:-origin/main}"
  steps=(
    "format + lint|QUALITY_ENFORCE=1 bash tools/quality/quality.sh --check"
    "fast tier (seam guard)|$PY tools/quality/tests/run_suite.py --fast"
    "coverage ratchet|bash tools/quality/coverage.sh"
    "diff coverage|$PY tools/quality/diff_coverage.py --base $base"
    "badge + docs lock-step|$PY tools/badges/sync_coverage.py --check"
    "docs freshness|$PY tools/quality/validate_docs_freshness.py"
    "docs links|$PY tools/quality/validate_docs_links.py"
    "secret scan|$PY tools/verify/scan_git_history.py --strict"
    "repo hygiene|$PY tools/quality/validate_repository_hygiene.py"
    "blocking gate|$PY tools/quality/gate.py"
  )
  n=0
  for step in "${steps[@]}"; do
    n=$((n + 1))
    label="${step%%|*}"
    cmd="${step#*|}"
    t_stage "$(printf '%02d' "$n")" "${label}"
    if t_run "${label}" -- bash -c "$cmd"; then :; else
      rc=1
      t_say fail "   $(t_mark fail) preflight halted at: ${label}"
      break
    fi
  done
  printf '\n'
  if [ "$rc" -eq 0 ]; then
    t_say ok "$(t_mark pass) preflight green — every locally-runnable CI check passed"
    t_say ink_dim "   CI-only (not run here): sca · reuse · release-gate (full build + fonts)"
  fi
  ;;
verify)
  header "verify"
  generic "release gate + signature verification" $PY tools/verify/validate_release.py
  rc=$?
  ;;
diff-coverage)
  header "diff-coverage"
  generic "changed-line coverage ratchet" $PY tools/quality/diff_coverage.py --base "${PREFLIGHT_BASE:-origin/main}"
  rc=$?
  ;;
privacy-check)
  header "privacy-check"
  generic "storage keys" $PY tools/quality/validate_storage_keys.py &&
    generic "runtime contamination" $PY tools/quality/validate_no_runtime_contamination.py &&
    generic "trusted types" $PY tools/quality/validate_trusted_types.py
  rc=$?
  ;;
provenance-check)
  header "provenance-check"
  generic "claims parity" $PY tools/verify/validate_claims_parity.py
  rc=$?
  ;;
claims)
  header "claims"
  generic "regenerate CLAIMS.md" $PY tools/build/generate_claims_md.py &&
    generic "claims parity gate" $PY tools/verify/validate_claims_parity.py
  rc=$?
  ;;
integrity)
  header "integrity"
  generic "regenerate the integrity manifest" $PY tools/build/generate_integrity.py
  rc=$?
  ;;
release-check)
  # build.sh renders its own full ceremony (logo + 14 stages); pass through.
  exec bash tools/build/build.sh --check
  ;;
doctor)
  # doctor.sh self-renders; pass through.
  exec bash tools/quality/doctor.sh
  ;;
*)
  printf 'make-ui: unknown activity %q\n' "$ACTIVITY" >&2
  exit 2
  ;;
esac

exit "$rc"
