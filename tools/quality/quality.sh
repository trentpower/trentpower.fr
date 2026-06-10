#!/usr/bin/env bash
# tools/quality/quality.sh — umbrella code-quality runner for the trentpower.fr sources.
#
# Scope is SOURCE only (never the generated/signed public/ tree):
#   python  tools/**/*.py            ruff (format + lint)
#   shell   tools/**/*.sh, hooks     shfmt (format) + shellcheck (lint)
#   js      templates/*.template.js  eslint (lint only)  + public/verify/verify.js
#   css     styles/*.src.css         stylelint (lint only)
#   data    content/*.yml, docs/*.md prettier (format)
#
# Modes:
#   --check  (default)  formatters run in check mode; nothing is written
#   --fix               formatters rewrite in place; linters still only report
#
# Linters always report-only (they never rewrite code). Missing tools are
# skipped with a notice, so a partial local toolchain still works; CI installs
# the full set. QUALITY_ENFORCE=1 makes any issue fatal (exit 1); the default
# QUALITY_ENFORCE=0 warns only (used during the gradual rollout).

set -uo pipefail

MODE="check"
case "${1:-}" in
--check | "") MODE="check" ;;
--fix) MODE="fix" ;;
-h | --help)
  sed -n '2,28p' "$0" | sed 's/^# \?//'
  exit 0
  ;;
*)
  echo "usage: quality.sh [--check|--fix]" >&2
  exit 2
  ;;
esac

ENFORCE="${QUALITY_ENFORCE:-0}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
cd "$ROOT" || exit 1

issues=0
have() { command -v "$1" >/dev/null 2>&1; }
node_bin() { [ -x "node_modules/.bin/$1" ]; }

note() { printf '── %s\n' "$1"; }
skip() { printf '── %s — skipped (%s)\n' "$1" "$2"; }
report() {
  printf '   x %s reported issues\n' "$1"
  issues=$((issues + 1))
}

# the shell scripts we own (lint + format targets).
shell_targets() {
  find tools -maxdepth 2 -name '*.sh' -print
  [ -f tools/hooks/pre-commit ] && echo tools/hooks/pre-commit
}

# ── python: ruff ────────────────────────────────────────────────────────────
if have ruff; then
  if [ "$MODE" = "fix" ]; then
    note "ruff format (write)"
    ruff format tools || report "ruff format"
  else
    note "ruff format (check)"
    ruff format --check tools || report "ruff format"
  fi
  note "ruff check (lint)"
  ruff check tools || report "ruff check"
else
  skip "ruff (python)" "not installed — see docs/GATES-CHECKS-AND-QUALITY.md"
fi

# ── shell: shfmt + shellcheck ───────────────────────────────────────────────
mapfile -t SH < <(shell_targets)
if [ "${#SH[@]}" -gt 0 ]; then
  if have shfmt; then
    if [ "$MODE" = "fix" ]; then
      note "shfmt (write)"
      shfmt -w -ln bash -i 2 "${SH[@]}" || report "shfmt"
    else
      note "shfmt (check)"
      shfmt -d -ln bash -i 2 "${SH[@]}" || report "shfmt"
    fi
  else
    skip "shfmt (shell format)" "not installed"
  fi
  if have shellcheck; then
    note "shellcheck (lint)"
    shellcheck "${SH[@]}" || report "shellcheck"
  else
    skip "shellcheck (shell lint)" "not installed"
  fi
fi

# ── data: prettier (hand-authored yaml/json/md only) ────────────────────────
if node_bin prettier; then
  PRETTIER_ARGS=("content/**/*.{yml,yaml}" "docs/**/*.md" "./*.md" "./package.json" --no-error-on-unmatched-pattern)
  if [ "$MODE" = "fix" ]; then
    note "prettier (write)"
    node_modules/.bin/prettier --write "${PRETTIER_ARGS[@]}" || report "prettier"
  else
    note "prettier (check)"
    node_modules/.bin/prettier --check "${PRETTIER_ARGS[@]}" || report "prettier"
  fi
else
  skip "prettier (data format)" "run npm install"
fi

# ── js: eslint (lint only) ──────────────────────────────────────────────────
if node_bin eslint; then
  note "eslint (lint)"
  node_modules/.bin/eslint . || report "eslint"
else
  skip "eslint (js lint)" "run npm install"
fi

# ── css: stylelint (lint only) ──────────────────────────────────────────────
if node_bin stylelint; then
  note "stylelint (lint)"
  node_modules/.bin/stylelint "styles/*.src.css" || report "stylelint"
else
  skip "stylelint (css lint)" "run npm install"
fi

echo
if [ "$issues" -eq 0 ]; then
  echo "OK: quality clean (mode=$MODE)"
  exit 0
fi
echo "quality: $issues check(s) reported issues (mode=$MODE, enforce=$ENFORCE)"
if [ "$ENFORCE" = "1" ]; then
  echo "FAIL: QUALITY_ENFORCE=1 — blocking."
  exit 1
fi
echo "(advisory: QUALITY_ENFORCE=0 — not blocking. set QUALITY_ENFORCE=1 to enforce.)"
exit 0
