#!/usr/bin/env bash
# doctor.sh -- environment diagnostics cockpit for trentpower.fr.
#
# Ceremony only. tools/quality/doctor.py decides what is true and prints a
# machine-readable report (--json); this script renders it with the same term.sh
# visual system as build.sh. It runs no build/test/gate, installs nothing,
# downloads nothing — only version probes and file reads, in well under a second.
#
# Verdict (from doctor.py): full | partial | archive | blocked. Exit is 0 even
# with missing optional pieces; non-zero only when the doctor itself cannot run
# or the repo root cannot be identified (mode blocked).
set -euo pipefail

# ── flags ────────────────────────────────────────────────────────────────────
RENDER_FORCE=""
ASCII=0
VERBOSE=0
for arg in "$@"; do
  case "$arg" in
  --plain) RENDER_FORCE="plain" ;;
  --ascii) ASCII=1 ;;
  --verbose) VERBOSE=1 ;;
  *) ;;
  esac
done

# ── root resolution (this script lives in tools/quality/) ────────────────────
TOOLS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DOCTOR_PY="$TOOLS_DIR/quality/doctor.py"

# ── python3 must exist before anything else; fail plainly, never source-fail ──
if ! command -v python3 >/dev/null 2>&1; then
  printf 'doctor: python3 not found — cannot diagnose this environment.\n' >&2
  printf 'doctor: mode: blocked\n' >&2
  exit 3
fi

# ── render mode + presentation library ──────────────────────────────────────
# shellcheck source=tools/build/term.sh
source "$TOOLS_DIR/build/term.sh"
t_init "$RENDER_FORCE" "$ASCII" "$VERBOSE"

# ── run the diagnosis (capture stdout; stderr stays visible for real crashes) ─
JSON="$(python3 "$DOCTOR_PY" --json || true)"
if [ -z "$JSON" ]; then
  t_say fail "$(t_mark fail) doctor could not run — no report produced."
  t_say ink_dim "   the repo root may be unidentifiable, or doctor.py crashed (see above)."
  exit 3
fi

# ── flatten the report to a neutral line stream (the build.sh json_get pattern,
#    one python3 -c, no jq). Python emits SECTION/ROW/CAP/ACT/REC tokens; this
#    shell owns every tone decision below. ───────────────────────────────────
STREAM="$(printf '%s' "$JSON" | python3 -c '
import json, sys
r = json.load(sys.stdin)
sections = []
rows = {}
for c in r["checks"]:
    s = c["section"]
    if s not in rows:
        rows[s] = []
        sections.append(s)
    rows[s].append(c)
for i, s in enumerate(sections, 1):
    print("SECTION\t%02d\t%s" % (i, s))
    for c in rows[s]:
        print("ROW\t%s\t%s\t%s" % (c["name"], c["status"], c["detail"]))
print("CAP\tMode\t%s" % r["mode"])
print("CAP\tFull checks\t%s" % ("yes" if r["full_checks_available"] else "no"))
print("CAP\tArchive checks\t%s" % ("yes" if r["archive_checks_available"] else "no"))
for a in r["next_actions"]:
    print("ACT\t%s" % a)
print("REC\t%s" % r.get("recommended_next", ""))
')"

# ── status -> (mark, tone). Python emits neutral tokens; bash maps them. ──────
mark_for() {
  case "$1" in
  present | ok | available | plausible) printf 'pass' ;;
  missing | partial | unavailable | sot-unavailable) printf 'warn' ;;
  n/a) printf 'skip' ;;
  *) printf 'skip' ;;
  esac
}
tone_for() {
  case "$1" in
  present | ok | available | plausible) printf 'ok' ;;
  missing | partial | unavailable | sot-unavailable) printf 'warn' ;;
  n/a) printf 'ink_dim' ;;
  *) printf 'ink_dim' ;;
  esac
}
mode_tone() {
  case "$1" in
  full) printf 'ok' ;;
  partial | archive) printf 'warn' ;;
  *) printf 'fail' ;;
  esac
}

# ── render: a stage + checklist per section, then a Capability panel ──────────
t_say ox "environment diagnostics — trentpower.fr"

MODE="" FULL="" ARCHIVE="" REC=""
ACTIONS=()
while IFS=$'\t' read -r kind a b c; do
  case "$kind" in
  SECTION) t_stage "$a" "$b" ;;
  ROW)
    name="$a" status="$b" detail="$c"
    printf '   %s %s  %s\n' \
      "$(t_mark "$(mark_for "$status")")" \
      "$(t_seg "$(tone_for "$status")" "$name")" \
      "$(t_seg ink_dim "$detail")"
    ;;
  CAP)
    case "$a" in
    Mode) MODE="$b" ;;
    "Full checks") FULL="$b" ;;
    "Archive checks") ARCHIVE="$b" ;;
    esac
    ;;
  ACT) ACTIONS+=("$a") ;;
  REC) REC="$a" ;;
  esac
done <<<"$STREAM"

printf '\n'
t_panel_open "CAPABILITY"
t_panel_row "Mode" "$MODE" "$(mode_tone "$MODE")"
t_panel_row "Full checks" "$FULL"
t_panel_row "Archive checks" "$ARCHIVE"
t_panel_close

if [ "${#ACTIONS[@]}" -gt 0 ]; then
  printf '\n'
  t_say paper "Next actions"
  for act in "${ACTIONS[@]}"; do
    printf '   %s %s\n' "$(t_mark warn)" "$(t_seg ink "$act")"
  done
fi

if [ -n "$REC" ]; then
  printf '\n'
  printf '   %s %s\n' "$(t_seg ink_dim 'Recommended next command:')" "$(t_seg paper "$REC")"
fi

[ "$MODE" = "blocked" ] && exit 3
exit 0
