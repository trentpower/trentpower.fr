#!/usr/bin/env bash
# trentpower.fr — single-command publication build.
#
# Run from anywhere:
#     bash tools/build.sh
#
# This is the existing build pipeline, framed as a deliberate publication
# ceremony (BUILD_RENDER_BRIEF.md): an operator-driven sequence of numbered
# stages with colour, markers, spinners and prompts when run on a TTY, that
# degrades to a clean, colourless, box-free transcript when piped / NO_COLOR /
# not a TTY. The build *logic* is unchanged — only the operator experience.
#
# Modes:
#     bash tools/build.sh                 # full build + sign + release archives + gate
#     bash tools/build.sh --check         # generators + gate only, no signing/archives — fast inner loop
#     bash tools/build.sh --no-sign       # full build + verify, but skip signing/archives/deploy (CI without key)
#     bash tools/build.sh --editorial     # also regenerate editorial review exports (md/html/docx/pdf)
#     bash tools/build.sh --public-check  # --check plus the public-readiness gate (secret scan + posture)
#     bash tools/build.sh --public-release # full ceremony, then stage 14: flip the GitHub repo public
#     bash tools/build.sh --yes-public    # pre-approve stage 14 (or env PUBLIC_RELEASE_APPROVED=1)
#     bash tools/build.sh --no-push       # in the ship ritual, commit only — never push or deploy
#     bash tools/build.sh --skip-coverage # dev only: skip the stage-02 coverage ratchet (refused for public builds)
#     bash tools/build.sh --plain         # force the plain transcript even on a TTY
#     bash tools/build.sh --ascii         # ascii markers ([ok]/[x]) instead of glyphs
#     bash tools/build.sh --verbose       # echo each underlying command beneath its activity
#     bash tools/build.sh --help          # this message
#
# Produces a verified-good local tree. Pushing to the live host is a separate,
# deliberate act inside the ship ritual (stages 10–13); off a TTY nothing is
# committed, pushed or deployed automatically.
#
# Pipeline order matters because three things mutate HTML in-place:
#   generate_site.py        — sweeps data-edition, asset-version, etc.
#   generate_sri.py         — sweeps SHA-384 SRI hashes
#   (none after this)
# …and three things produce the JS/CSS bytes that SRI hashes:
#   generate_site.py        — writes app.js, verify-modal.js
#   generate_sw.py          — writes sw.js
#   generate_verification_map.py — writes verify/verification-data.js
#
# Therefore: run SRI ONCE at the very end of the byte-mutating phase, AFTER
# verification-data.js is finalized, but BEFORE the final integrity manifest
# hashes the tree. Stages [3] and [7] both call generate_integrity.py: the
# preliminary pass feeds the verification map; the final pass hashes the
# post-SRI tree so the signature signs the bytes the world sees.

set -euo pipefail

# ── argument parsing ────────────────────────────────────────────────────────
MODE="full"
MODE_EXPLICIT=0
EDITORIAL=0
RENDER_FORCE=""
ASCII=0
VERBOSE=0
PUBLIC_RELEASE=0
PUBLIC_APPROVED="${PUBLIC_RELEASE_APPROVED:-0}"
NO_PUSH=0
SKIP_COVERAGE=0
for arg in "$@"; do
  case "$arg" in
  --check)
    MODE="check"
    MODE_EXPLICIT=1
    ;;
  --no-sign)
    MODE="nosign"
    MODE_EXPLICIT=1
    ;;
  --public-check)
    MODE="publiccheck"
    MODE_EXPLICIT=1
    ;;
  --public-release)
    PUBLIC_RELEASE=1
    MODE_EXPLICIT=1
    ;;
  --yes-public) PUBLIC_APPROVED=1 ;;
  --no-push) NO_PUSH=1 ;;
  --skip-coverage) SKIP_COVERAGE=1 ;;
  --editorial) EDITORIAL=1 ;;
  --plain) RENDER_FORCE="plain" ;;
  --ascii) ASCII=1 ;;
  --verbose) VERBOSE=1 ;;
  --help | -h)
    sed -n '2,37p' "$0" | sed 's/^# \?//'
    exit 0
    ;;
  *)
    echo "build.sh: unknown argument '$arg' (try --help)" >&2
    exit 2
    ;;
  esac
done

# --skip-coverage is a dev-only inner-loop affordance; a public build must always
# enforce the coverage ratchet.
if [ "$SKIP_COVERAGE" -eq 1 ] && { [ "$MODE" = "publiccheck" ] || [ "$PUBLIC_RELEASE" -eq 1 ]; }; then
  echo "build.sh: --skip-coverage cannot be combined with a public build (--public-check/--public-release)" >&2
  exit 2
fi

# TOOLS_DIR resolves to tools/ (this script lives in tools/build/); each python
# script computes its own ROOT via tools/lib/paths.py, so cwd does not matter.
TOOLS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$TOOLS_DIR/.." && pwd)"
PUBLIC_DIR="$REPO_ROOT/public"
IDENTITY="$REPO_ROOT/tools/config/identity_canonical.json"

# ── render mode + presentation library ──────────────────────────────────────
# Decide ONCE: rich on a capable TTY, plain otherwise (or when forced). term.sh
# is pure presentation — it never affects the build, signing or publication.
if [ -n "$RENDER_FORCE" ]; then
  T_RENDER="plain"
elif [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && [ "${TERM:-dumb}" != "dumb" ]; then
  T_RENDER="rich"
else
  T_RENDER="plain"
fi
T_ASCII="$ASCII"
T_VERBOSE="$VERBOSE"
# shellcheck source=tools/build/term.sh
source "$TOOLS_DIR/build/term.sh"

# ── small build helpers ─────────────────────────────────────────────────────
# step LABEL CMD…   — spinner around a required step; any failure halts.
step() {
  local label="$1"
  shift
  t_run "$label" -- "$@" || _fail "$label"
}
# soft_step LABEL CMD…   — non-blocking step; failure shows a warn and continues.
soft_step() {
  local label="$1"
  shift
  t_verbose_cmd "$@"
  t_spin_start "$label"
  if "$@" >/dev/null 2>&1; then
    t_spin_stop pass "$label"
  else
    t_spin_stop warn "$label" "skipped (non-blocking)"
  fi
}
_fail() {
  printf '\n'
  t_say fail "$(t_mark fail) Build halted at: $1"
  t_say ink_dim "   No further stage runs. The previous edition is unaffected."
  printf '\n'
  exit 1
}

# count_pages SUBDIR   — html files under public/SUBDIR
count_pages() { find "$PUBLIC_DIR/$1" -type f -name '*.html' 2>/dev/null | wc -l | tr -d ' '; }
json_get() { python3 -c "import json;print(json.load(open('$1')).get('$2',''))" 2>/dev/null || true; }
count_manifest() {
  python3 - "$PUBLIC_DIR/integrity.json" <<'PY' 2>/dev/null || true
import json,sys
try:
    d=json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
for k in ("files","entries","manifest"):
    v=d.get(k) if isinstance(d,dict) else None
    if isinstance(v,(list,dict)):
        print(len(v)); break
else:
    print(len(d) if isinstance(d,(list,dict)) else "")
PY
}
count_archives() {
  find "$PUBLIC_DIR/integrity/releases/$EDITION" -maxdepth 1 \
    \( -name '*.zip' -o -name '*.tar.gz' \) 2>/dev/null | wc -l | tr -d ' '
}

# the trentpower.fr wordmark now lives in tools/build/term.sh (t_logo) so the
# build masthead and the `make` ceremony share one source of the art.

# ── current edition + the operator's chosen note ────────────────────────────
EDITION="$(json_get "$IDENTITY" edition)"
[ -n "$EDITION" ] || EDITION="unknown"
NOTE=""

# ── splash masthead (presentation only) ─────────────────────────────────────
splash() {
  if [ "$T_RENDER" != "rich" ]; then
    printf 'TRENTPOWER · trentpower.fr — edition %s\n' "$EDITION"
    return 0
  fi
  t_logo
}

# ── 01 · Publication Intent (interactive; skipped off a TTY or with a mode flag) ─
stage01_intent() {
  t_banner "TRENTPOWER.FR PUBLICATION BUILD" "Static · Signed · Source-verifiable" "Paris"
  t_stage 01 "PUBLICATION INTENT" "No build starts automatically. Choose deliberately."
  printf '\n'
  t_menu \
    "1=Create new edition" \
    "2=Rebuild existing edition" \
    "3=Check only — no signed artefacts" \
    "4=Exit"
  printf '\n'
  case "$T_REPLY" in
  1)
    MODE="full"
    t_say ox "Create new edition"
    printf '\n'
    t_ask_text "Edition date" "$EDITION" \
      "Edition date — used across identity, release, archives and the record. Default keeps the current edition (no rotation in this build)."
    EDITION="$T_REPLY"
    printf '\n'
    t_ask_text "Edition note" "$NOTE" \
      "One sentence describing the edition. Recorded for the review + publication record."
    NOTE="$T_REPLY"
    printf '\n'
    t_say ink "$(t_mark pass) Edition $(t_seg paper "$EDITION") · note recorded"
    ;;
  2)
    MODE="full"
    t_say ox "Rebuild existing edition"
    printf '\n'
    t_panel_open "CURRENT EDITION"
    t_panel_row "Edition" "$EDITION" paper
    t_panel_close
    printf '\n'
    if t_confirm_yn "Continue rebuild? Reuses the current edition — it will not rotate." no; then
      :
    else
      t_say ink_dim "Rebuild cancelled. Edition unchanged."
      exit 0
    fi
    ;;
  3)
    MODE="check"
    t_banner "CHECK MODE" "No signed artefacts will be produced."
    ;;
  4 | "")
    t_say ink_dim "Session closed. No edition was created."
    exit 0
    ;;
  *)
    t_say warn "Unrecognised choice '$T_REPLY'. Nothing was built."
    exit 0
    ;;
  esac
}

# ── 02 · RENDER ─────────────────────────────────────────────────────────────
stage02_render() {
  t_stage 02 "RENDER" "Transform authored content into public pages."
  t_flow "content/" "templates/" "public/"
  step "Source quality gate" bash "$TOOLS_DIR/quality/quality.sh" --check
  # Coverage ratchet — same script CI runs; exits non-zero below any floor, so a
  # coverage regression (or a failing unit test) halts the build here, BEFORE any
  # public byte is generated. .coverage + .build/coverage are gitignored. The
  # measured test count + TEST COVERAGE % are surfaced for an operator decision,
  # then the figure is synced into the badge + docs (sync_coverage.py).
  if [ "$SKIP_COVERAGE" -eq 1 ]; then
    t_say warn "$(t_mark warn) Coverage ratchet — SKIPPED (--skip-coverage, dev only)"
  elif ! python3 -m coverage --version >/dev/null 2>&1; then
    # coverage.py is the build machine's responsibility; the dedicated CI
    # coverage job (pr-checks source-quality) is the authoritative gate. Skip
    # rather than hard-fail in environments that do not install it (e.g. the
    # publication-check / release build jobs).
    t_say warn "$(t_mark warn) Coverage ratchet — SKIPPED (coverage.py not installed; enforced on the build host + the source-quality CI job)"
  else
    # floors derived from the single source of truth — never hardcoded here.
    # shellcheck source=tools/quality/coverage-floors.sh
    . "$TOOLS_DIR/quality/coverage-floors.sh"
    floors="${SEAL_MIN}/${ADR_MIN}/${BROAD_MIN}"
    cov_log="$(mktemp)"
    t_spin_start "Coverage ratchet · floors ${floors}"
    if bash "$TOOLS_DIR/quality/coverage.sh" >"$cov_log" 2>&1; then
      t_spin_stop pass "Coverage ratchet · floors ${floors}"
    else
      t_spin_stop fail "Coverage ratchet · floors ${floors}"
      sed 's/^/   /' "$cov_log" | tail -20
      rm -f "$cov_log"
      _fail "Coverage ratchet"
    fi
    cov_tests="$(grep -oE 'Ran [0-9]+ tests' "$cov_log" | grep -oE '[0-9]+' | head -1)"
    rm -f "$cov_log"
    cov_pct="$(python3 -c "import json;print(json.load(open('.build/coverage/coverage-summary.json'))['test_coverage_pct'])" 2>/dev/null || echo '?')"
    t_say ink "$(t_mark pass) ${cov_tests:-?} unit tests passed · TEST COVERAGE ${cov_pct}% · floors ${floors} all green"
    # operator gate — continue or cancel based on the numbers (auto-continues off-TTY)
    t_menu "1=Continue the build" "2=Cancel the build"
    case "$T_REPLY" in
    2 | c | C | cancel | n | N | no)
      t_say fail "$(t_mark fail) Build cancelled at coverage review — previous edition unaffected."
      exit 1
      ;;
    esac
    step "Sync coverage badge + docs" python3 "$TOOLS_DIR/badges/sync_coverage.py" --write
  fi
  # documentation freshness is build-blocking — no public byte is generated while
  # the docs make a stale machine-checkable claim or a broken internal link.
  step "Docs freshness gate" python3 "$TOOLS_DIR/quality/validate_docs_freshness.py"
  step "Docs links gate" python3 "$TOOLS_DIR/quality/validate_docs_links.py"
  step "QR drift gate" python3 "$TOOLS_DIR/build/generate_qr.py" --check
  step "Compile copy (yaml → strings.json)" python3 "$TOOLS_DIR/build/copy/build_copy.py"
  step "Render bilingual pages (/en-au/ + /fr/ + gate)" python3 "$TOOLS_DIR/build/render_pages.py" --out "$PUBLIC_DIR"
  step "Prune single-tree leftovers" python3 "$TOOLS_DIR/build/copy/prune_single_tree.py"
  step "Repository hygiene gate" python3 "$TOOLS_DIR/quality/validate_repository_hygiene.py"
  soft_step "Build font subsets" python3 "$TOOLS_DIR/build/build_font_subsets.py"
  local en fr
  en="$(count_pages en-au)"
  fr="$(count_pages fr)"
  t_say ink_dim "   $(t_mark pass) Rendered $(t_seg paper "$en") EN-AU · $(t_seg paper "$fr") FR pages"
}

# ── 03 · PREPARE PUBLIC BYTES ───────────────────────────────────────────────
stage03_prepare() {
  t_stage 03 "PREPARE PUBLIC BYTES" "Create every public artefact the publication requires."
  t_flow "HTML" "SRI" "Final HTML"
  step "Generate site assets" python3 "$TOOLS_DIR/build/generate_site.py"
  step "Generate .htaccess regions" python3 "$TOOLS_DIR/build/generate_htaccess.py"
  step "Release-record landing page" python3 "$TOOLS_DIR/build/generate_release_record.py"
  step "Tests results page" python3 "$TOOLS_DIR/build/generate_tests_page.py"
  step "Documentation surface" python3 "$TOOLS_DIR/build/generate_documentation.py"
  step "Page provenance records" python3 "$TOOLS_DIR/build/generate_provenance.py"
  step "Prune legacy versioned assets" python3 "$TOOLS_DIR/build/prune_legacy_versioned_assets.py"
  step "Generate service worker" python3 "$TOOLS_DIR/build/generate_sw.py"
  step "Integrity manifest (preliminary)" python3 "$TOOLS_DIR/build/generate_integrity.py"
  step "Verification map" python3 "$TOOLS_DIR/build/generate_verification_map.py"
  step "SRI sweep" python3 "$TOOLS_DIR/build/generate_sri.py"
  step "Sitemap checksum" bash -c "cd '$PUBLIC_DIR' && sha256sum sitemap.xml | awk '{print \$1\"  sitemap.xml\"}' > sitemap.xml.sha256"

  if [ "$EDITORIAL" -eq 1 ]; then
    step "Editorial review (copywriter)" python3 "$TOOLS_DIR/build/copy/build_copy_review.py"
    step "Editorial binaries (docx/pdf)" python3 "$TOOLS_DIR/build/generate_editorial_binaries.py"
  fi

  step "File metadata (history-anchored)" python3 "$TOOLS_DIR/build/generate_file_metadata.py"
  step "File metadata — placeholder sweep" python3 "$TOOLS_DIR/build/generate_file_metadata.py" --sweep
  step "Source mirrors" python3 "$TOOLS_DIR/build/generate_source_view.py"
  step "Source reader shell" python3 "$TOOLS_DIR/build/generate_source_reader.py"
  step "File metadata — refresh" python3 "$TOOLS_DIR/build/generate_file_metadata.py" --final
  step "Verification map — final sizes" python3 "$TOOLS_DIR/build/generate_verification_map.py"
  step "SRI re-sweep (versioned map)" python3 "$TOOLS_DIR/build/generate_sri.py"
  step "Build manifest provenance" python3 "$TOOLS_DIR/build/derive_build_manifest.py"
  step "Source mirrors — refresh" python3 "$TOOLS_DIR/build/generate_source_view.py"
  step "Source reader — recreate" python3 "$TOOLS_DIR/build/generate_source_reader.py"
  # the source catalogue + reader shells were just regenerated from
  # scratch; re-run the (idempotent) provenance sweep so those two
  # pages carry their record before the tree is re-hashed.
  step "Page provenance — regenerated surfaces" python3 "$TOOLS_DIR/build/generate_provenance.py"
  step "Integrity — mirror refresh" python3 "$TOOLS_DIR/build/generate_integrity.py"
  step "Verification map — converged source hashes" python3 "$TOOLS_DIR/build/generate_verification_map.py"
  step "SRI — re-versioned map" python3 "$TOOLS_DIR/build/generate_sri.py"
  step "Footer source-sha injection" python3 "$TOOLS_DIR/build/inject_source_sha_footer.py"
  step "File metadata — post-convergence" python3 "$TOOLS_DIR/build/generate_file_metadata.py" --final
  step "Public-exposure allow-list" python3 "$TOOLS_DIR/build/generate_public_exposure_manifest.py"
}

# ── 04 · SEAL (final integrity manifest; archives queued until after approval) ─
stage04_seal() {
  t_stage 04 "SEAL" "Convert public files into a verifiable publication."
  t_flow "public/" "manifest" "signature" "archive"
  step "Integrity manifest (final pass)" python3 "$TOOLS_DIR/build/generate_integrity.py"
  local entries
  entries="$(count_manifest)"
  [ -n "$entries" ] && t_say ink_dim "   $(t_mark pass) Manifest hashes $(t_seg paper "$entries") entries"
  # record a content snapshot of the just-sealed tree. the seal-immutability
  # guard in stage 07 re-checks it just before signing, so no generator can move
  # public bytes between seal and signature (see docs/adr/0003 + the publication
  # rule it enforces). nothing must mutate public/ after this point.
  step "Record seal snapshot" python3 "$TOOLS_DIR/build/assert_seal_immutable.py" --record
  if [ "$MODE" = "full" ]; then
    t_say ink_faint "   Release archive queued — built after publication approval (it signs the sealed bytes)."
  fi
}

# ── 05 · VERIFY (blocking minus signature, pre-approval; advisory) ───────────
BLOCKING_SUMMARY="not run"
ADVISORY_SUMMARY="not run"
stage05_verify() {
  t_stage 05 "VERIFY" "Decide whether publication is permitted."
  t_flow "SECURITY" "CORRECTNESS" "QUALITY"

  t_verbose_cmd python3 "$TOOLS_DIR/quality/gate.py" --skip-signature --all
  t_spin_start "Gate · blocking checks (pre-signature)"
  local gout grc total
  gout="$(python3 "$TOOLS_DIR/quality/gate.py" --skip-signature --all 2>&1)" && grc=0 || grc=$?
  total="$(printf '%s\n' "$gout" | grep -oE '^\[[0-9]+/[0-9]+\]' | tail -1 | cut -d/ -f2 | tr -dc '0-9')"
  if [ "$grc" -eq 0 ]; then
    BLOCKING_SUMMARY="${total:-all} passed"
    t_spin_stop pass "Gate · blocking checks" "$BLOCKING_SUMMARY (signature pending)"
  elif [ "$MODE" = "check" ]; then
    BLOCKING_SUMMARY="failures (check mode)"
    t_spin_stop warn "Gate · blocking checks" "non-zero in check mode — see below"
    printf '%s\n' "$gout"
  else
    t_spin_stop fail "Gate · blocking checks"
    printf '%s\n' "$gout" >&2
    _fail "blocking gate"
  fi

  t_verbose_cmd python3 "$TOOLS_DIR/quality/lint.py" --format json
  t_spin_start "Lint · advisory quality"
  local lout lfailed ltotal
  lout="$(python3 "$TOOLS_DIR/quality/lint.py" --format json 2>/dev/null)" || true
  lfailed="$(printf '%s' "$lout" | python3 -c "import json,sys;
try: d=json.load(sys.stdin); print(d.get('advisory_failed',''))
except Exception: print('')" 2>/dev/null)"
  ltotal="$(printf '%s' "$lout" | python3 -c "import json,sys;
try: d=json.load(sys.stdin); print(d.get('advisory_total',''))
except Exception: print('')" 2>/dev/null)"
  if [ -n "$lfailed" ] && [ "$lfailed" != "0" ]; then
    ADVISORY_SUMMARY="$lfailed warning(s)"
    t_spin_stop warn "Lint · advisory quality" "$lfailed/${ltotal:-?} advisory — non-blocking"
  else
    ADVISORY_SUMMARY="clean"
    t_spin_stop pass "Lint · advisory quality" "${ltotal:-all} advisory checks clean"
  fi
}

# ── Check complete (end of the --check path) ────────────────────────────────
check_complete() {
  printf '\n'
  t_panel_open "CHECK COMPLETE"
  t_panel_row "Edition" "$EDITION" paper
  t_panel_row "Render" "EN $(count_pages en-au) · FR $(count_pages fr)"
  t_panel_row "Blocking" "$BLOCKING_SUMMARY"
  t_panel_row "Advisory" "$ADVISORY_SUMMARY" warn
  t_panel_sub "result"
  t_panel_row "Signed" "no — check mode" ink_dim
  t_panel_row "Artefacts" "none produced" ink_dim
  t_panel_close
  printf '\n'
  t_say ink "$(t_mark pass) Check passed. No signed artefacts were produced."
}

# ── Public readiness (unnumbered panel; the public-repo posture gate) ────────
# Runs the full-history secret scan and the root-posture validator in --full
# mode. Used by --public-check and --public-release; the routine blocking gate
# already runs the validator without --full on every build.
PUBLIC_SCAN_SUMMARY=""
public_gate() {
  printf '\n'
  t_verbose_cmd python3 "$TOOLS_DIR/quality/secret_scan.py"
  t_spin_start "Secret scan · full history, every ref"
  local sout src
  sout="$(python3 "$TOOLS_DIR/quality/secret_scan.py" 2>&1)" && src=0 || src=$?
  local engine refs
  engine="$(printf '%s\n' "$sout" | grep -oE 'engine=[^ ]+ ?[^ ]*' | tail -1 | cut -d= -f2- | cut -d' ' -f1-2)"
  refs="$(printf '%s\n' "$sout" | grep -oE 'refs=[0-9]+' | tail -1 | cut -d= -f2)"
  if [ "$src" -eq 0 ]; then
    PUBLIC_SCAN_SUMMARY="clean · ${engine:-?} · ${refs:-?} refs"
    t_spin_stop pass "Secret scan" "$PUBLIC_SCAN_SUMMARY"
  else
    t_spin_stop fail "Secret scan"
    printf '%s\n' "$sout" >&2
    _fail "secret scan"
  fi

  t_verbose_cmd python3 "$TOOLS_DIR/quality/validate_public_readiness.py" --full
  t_spin_start "Public-repo posture (full mode)"
  local pout prc
  pout="$(python3 "$TOOLS_DIR/quality/validate_public_readiness.py" --full 2>&1)" && prc=0 || prc=$?
  if [ "$prc" -eq 0 ]; then
    t_spin_stop pass "Public-repo posture" "licences · exclusions · no private-claim drift"
  else
    t_spin_stop fail "Public-repo posture"
    printf '%s\n' "$pout" >&2
    _fail "public readiness"
  fi

  printf '\n'
  t_panel_open "PUBLIC READINESS"
  t_panel_row "Secret scan" "$PUBLIC_SCAN_SUMMARY" ok
  t_panel_row "Posture" "holds (full mode)" ok
  t_panel_row "Report" "reports/checks/last-secret-scan.json" ink_dim
  t_panel_close
}

# ── 06 · Publication Review (the decisive checkpoint) ───────────────────────
stage06_review() {
  t_stage 06 "PUBLICATION REVIEW" "The decisive checkpoint. Everything below is mechanism; this is the act."
  printf '\n'
  local files entries
  files="$(json_get "$PUBLIC_DIR/.well-known/build.json" public_file_count)"
  entries="$(count_manifest)"
  t_panel_open "PUBLICATION REVIEW"
  t_panel_row "Edition" "$EDITION" paper
  [ -n "$NOTE" ] && t_panel_row "Note" "$NOTE"
  t_panel_row "EN-AU pages" "$(count_pages en-au)"
  t_panel_row "FR pages" "$(count_pages fr)"
  [ -n "$files" ] && t_panel_row "Public files" "$files"
  [ -n "$entries" ] && t_panel_row "Manifest entries" "$entries"
  t_panel_sub "verification"
  t_panel_row "Blocking" "$BLOCKING_SUMMARY" ok
  t_panel_row "Advisory" "$ADVISORY_SUMMARY" warn
  t_panel_close
  printf '\n'
  t_say ink_dim "Review the edition above. Publication does not proceed without a deliberate decision."
  if ! t_is_tty; then
    # unattended build (piped / redirected): proceed and sign, as the
    # pre-ceremony build.sh always did. The ship ritual still never auto-runs.
    t_say ink_dim "Non-interactive: proceeding to approval (unattended build)."
    return 0
  fi
  if t_confirm_yn "Proceed to publication approval?" no; then
    return 0
  fi
  printf '\n'
  t_say warn "Publication paused. No approval given. No signature created. No artefacts deployed."
  exit 0
}

# ── 07 · Publication Approval (software signing; hardware-token seam) ────────
SIGN_FPR=""
stage07_approval() {
  t_stage 07 "PUBLICATION APPROVAL" "The approval is the event; the signature is the evidence."
  printf '\n'
  # Explicit signing identity: derive the fingerprint from the *published*
  # public key and assert a matching local secret key, so signing can never
  # silently fall through to gpg's ambient default key.
  SIGN_FPR="$(gpg --batch --with-colons --import-options show-only \
    --import "$PUBLIC_DIR/.well-known/pgp-key.asc" 2>/dev/null |
    awk -F: '/^fpr:/{print $10; exit}')"
  if [ -z "$SIGN_FPR" ]; then
    _fail "could not derive fingerprint from public/.well-known/pgp-key.asc"
  fi
  if ! gpg --batch --list-secret-keys "$SIGN_FPR" >/dev/null 2>&1; then
    t_say fail "$(t_mark fail) No local secret key for the published fingerprint $SIGN_FPR."
    t_say ink_dim "   Refusing to sign with an ambient default key."
    _fail "no signing key"
  fi

  local fpr_short="${SIGN_FPR:0:4} ${SIGN_FPR:4:4} … ${SIGN_FPR: -8:4} ${SIGN_FPR: -4}"
  t_panel_open "PUBLICATION APPROVAL"
  t_panel_row "Manifest" "integrity.json"
  t_panel_row "Operation" "Detached signature"
  t_panel_row "Method" "Software OpenPGP key"
  t_panel_row "Fingerprint" "$fpr_short" ox
  t_panel_close
  printf '\n'
  # ── HARDWARE-TOKEN SEAM ───────────────────────────────────────────────────
  # When an OpenPGP hardware token is issued, this is where it slots in:
  #   - "Searching for OpenPGP signing device…" → detect the token
  #   - panel Device: "OpenPGP hardware token"
  #   - "Touch device to approve publication." → wait on the real touch
  #   - keep the verbatim line "Waiting for hardware approval…"
  # Until then we approve deliberately here and sign with the software key.
  if t_is_tty; then
    if ! t_confirm_yn "Approve publication and sign integrity.json?" no; then
      printf '\n'
      t_say fail "$(t_mark fail) Publication approval cancelled. No signature created."
      exit 0
    fi
  else
    t_say ink_dim "Non-interactive: signing with the published key (unattended build)."
  fi
  printf '\n'
  # seal-immutability guard — the publication rule. the tree must be byte-for-byte
  # what stage 04 sealed; if any generator (or stray edit) moved public bytes
  # since the seal, the signature would cover something other than the manifest.
  # refuse to sign a moved tree (see docs/adr/0003).
  if ! python3 "$TOOLS_DIR/build/assert_seal_immutable.py" --verify; then
    _fail "public bytes changed between seal and sign — refusing to sign"
  fi
  t_spin_start "Signing publication…"
  local rc
  (
    cd "$PUBLIC_DIR" &&
      unset GNUPGHOME &&
      gpg --batch --yes --local-user "$SIGN_FPR" --detach-sign --armor \
        -o integrity.json.sig integrity.json
  ) && rc=0 || rc=$?
  if [ "$rc" -ne 0 ]; then
    t_spin_stop fail "Signing publication"
    _fail "gpg detach-sign"
  fi
  t_spin_stop pass "Publication approved"
  t_say ink "   $(t_mark pass) Signature created"
}

# ── 08 · Signature Verification + seal finalisation (archives + full gate) ───
stage08_sigverify() {
  t_stage 08 "SIGNATURE VERIFICATION" "Verify the evidence, then finalise the sealed publication."
  printf '\n'
  t_spin_start "Verifying signature…"
  local rc
  (cd "$PUBLIC_DIR" && gpg --verify integrity.json.sig integrity.json) >/dev/null 2>&1 && rc=0 || rc=$?
  if [ "$rc" -ne 0 ]; then
    t_spin_stop fail "Signature verification"
    t_say fail "   Signature created but verification failed. Do not deploy."
    _fail "signature verification"
  fi
  t_spin_stop pass "Signature verified"
  t_say ink_dim "   Fingerprint  $(t_seg ox "$SIGN_FPR")"

  printf '\n'
  step "Release archives — zip + tar.gz + sha256 + sigs" python3 "$TOOLS_DIR/release/build_release_archives.py"
  local archs
  archs="$(count_archives)"
  [ -n "$archs" ] && t_say ink_dim "   $(t_mark pass) Sealed $(t_seg paper "$archs") release archive(s)"

  printf '\n'
  t_verbose_cmd python3 "$TOOLS_DIR/quality/gate.py"
  t_spin_start "Deploy gate · full blocking checks (post-signature)"
  local gout grc
  gout="$(python3 "$TOOLS_DIR/quality/gate.py" 2>&1)" && grc=0 || grc=$?
  if [ "$grc" -ne 0 ]; then
    t_spin_stop fail "Deploy gate"
    printf '%s\n' "$gout" >&2
    _fail "deploy gate"
  fi
  t_spin_stop pass "Deploy gate · ready to ship"
  BLOCKING_SUMMARY="all passed"
}

# ── 09 · Publication Record (panel from build.json — no new artefact) ───────
stage09_record() {
  t_stage 09 "PUBLICATION RECORD" "The historical record — the foundation for release history."
  printf '\n'
  local files commit fpr
  files="$(json_get "$PUBLIC_DIR/.well-known/build.json" public_file_count)"
  commit="$(json_get "$PUBLIC_DIR/.well-known/build.json" git_commit)"
  fpr="$(json_get "$PUBLIC_DIR/.well-known/build.json" key_fingerprint)"
  t_panel_open "PUBLICATION RECORD"
  t_panel_row "edition" "$EDITION" paper
  [ -n "$NOTE" ] && t_panel_row "note" "$NOTE"
  [ -n "$files" ] && t_panel_row "files" "$files"
  t_panel_row "signature_verified" "true" ok
  t_panel_row "gate_status" "passed" ok
  [ -n "$commit" ] && t_panel_row "git_commit" "${commit:0:12}"
  [ -n "$fpr" ] && t_panel_row "fingerprint" "$fpr" ox
  t_panel_close
}

# ── Sealed · ship decision ──────────────────────────────────────────────────
ship() {
  printf '\n'
  t_panel_open "SEALED · READY TO SHIP"
  t_panel_row "Edition" "$EDITION" paper
  [ -n "$NOTE" ] && t_panel_row "Note" "$NOTE"
  t_panel_row "Approval" "recorded" ok
  t_panel_row "Signature" "verified" ok
  t_panel_sub "not yet shipped"
  t_panel_row "Git" "uncommitted" warn
  t_panel_row "Live host" "previous edition" ink_dim
  t_panel_close
  printf '\n'

  if ! t_is_tty; then
    if [ "$NO_PUSH" = "1" ]; then
      stage10_commit
      printf '\n'
      t_say ink "$(t_mark pass) Committed to git (--no-push). Live host unchanged."
      return 0
    fi
    if [ "$PUBLIC_RELEASE" = "1" ] && [ "$PUBLIC_APPROVED" = "1" ]; then
      # the only unattended path that ships: an explicit public release,
      # pre-approved via --yes-public / PUBLIC_RELEASE_APPROVED=1.
      t_say ink_dim "Non-interactive public release (pre-approved): committing and deploying."
      stage10_commit
      stage11_deploy
      return 0
    fi
    t_say ink "$(t_mark pass) Edition approved, sealed and recorded."
    t_say ink_dim "Off a TTY: nothing committed, pushed or deployed. Run interactively to ship."
    return 0
  fi

  t_say ox "DEPLOY DECISION"
  t_say ink_faint "Deployment is a separate, deliberate act. Nothing ships automatically."
  printf '\n'
  t_menu \
    "1=Commit & deploy to trentpower.fr" \
    "2=Commit to git only — do not deploy" \
    "3=Finish — do not commit or deploy"
  printf '\n'
  case "$T_REPLY" in
  1)
    stage10_commit
    stage11_deploy
    ;;
  2)
    stage10_commit
    printf '\n'
    t_say ink "$(t_mark pass) Committed to git. Live host unchanged."
    ;;
  *)
    t_say ink_dim "Edition left sealed on disk. Nothing committed, nothing deployed."
    ;;
  esac
}

# ── 10 · Commit (public/ is tracked — the committed bytes are the attested bytes) ─
stage10_commit() {
  t_stage 10 "COMMIT" "public/ is tracked — the committed bytes are exactly what the signed manifest attests to."
  printf '\n'
  step "Stage public bytes" git -C "$REPO_ROOT" add public/ metadata/
  local msg="Publish edition $EDITION"
  [ -n "$NOTE" ] && msg="$msg — $NOTE"
  if git -C "$REPO_ROOT" diff --cached --quiet; then
    t_say ink_dim "   $(t_mark skip) Nothing staged — working tree already matches HEAD."
    return 0
  fi
  step "Commit edition" git -C "$REPO_ROOT" commit -m "$msg"
  local commit
  commit="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null)"
  t_say ink_dim "   $(t_mark pass) Committed $(t_seg ox "$commit") (not yet pushed)"
}

# ── 11 · Deploy (typed gate BEFORE the push; push fires the GHA SFTP deploy) ─
stage11_deploy() {
  t_stage 11 "DEPLOY" "Pushing to main triggers the GitHub Actions SFTP deploy. Confirm deliberately."
  printf '\n'
  if [ "$NO_PUSH" = "1" ]; then
    t_say warn "$(t_mark warn) --no-push: bytes are committed to git but were not pushed. Live host unchanged."
    return 0
  fi
  if [ "$PUBLIC_RELEASE" = "1" ] && [ "$PUBLIC_APPROVED" = "1" ] && ! t_is_tty; then
    t_say ink "$(t_mark pass) Deployment pre-approved (public release, PUBLIC_RELEASE_APPROVED)"
  elif ! t_confirm_word "Confirm deploy" "DEPLOY" \
    "Type DEPLOY to push origin/main and trigger the deploy. Anything else leaves the commit local."; then
    printf '\n'
    t_say warn "$(t_mark warn) Deploy not confirmed. Bytes are committed to git but were not pushed. Live host unchanged."
    return 0
  else
    printf '\n'
    t_say ink "$(t_mark pass) Deployment confirmed (confirm=DEPLOY)"
  fi
  step "Push origin main" git -C "$REPO_ROOT" push origin main
  t_say ink_dim "   GitHub Actions will SFTP-mirror public/ to Gandi (non-deleting) and smoke-test."
  if command -v gh >/dev/null 2>&1; then
    soft_step "Watch CI deploy run" gh run watch --exit-status --repo "$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)" 2>/dev/null
  fi
  printf '\n'
  stage12_smoke
}

# ── 12 · Smoke test (real probes against the live host) ─────────────────────
stage12_smoke() {
  t_stage 12 "SMOKE TEST" "Probe the live host: routes that must answer, routes that must be denied, the signature itself."
  printf '\n'
  local base="https://trentpower.fr" fail=0 code
  local ok_routes=(/ /en-au/ /fr/ /en-au/verify/ /fr/verifier/ /integrity.json /integrity.json.sig /.well-known/pgp-key.asc /sitemap.xml)
  local denied_routes=(/tools/ /templates/ /private/ /documentation/README.md /integrity.json.bak)

  t_say ink_dim "   ── expected 200 ──────────────"
  for path in "${ok_routes[@]}"; do
    code="$(curl -sk -o /dev/null -w '%{http_code}' "$base$path" 2>/dev/null || echo 000)"
    if [ "$code" = "200" ]; then
      t_say ink "   $(t_mark pass) GET $(printf '%-26s' "$path") $(t_seg ok "$code")"
    else
      t_say fail "   $(t_mark fail) GET $(printf '%-26s' "$path") $(t_seg fail "$code · expected 200")"
      fail=1
    fi
  done

  t_say ink_dim "   ── expected denial ───────────"
  for path in "${denied_routes[@]}"; do
    code="$(curl -sk -o /dev/null -w '%{http_code}' "$base$path" 2>/dev/null || echo 000)"
    if [ "$code" = "403" ] || [ "$code" = "404" ]; then
      t_say ink "   $(t_mark pass) GET $(printf '%-26s' "$path") $(t_seg ok "$code") $(t_seg ink_faint "denied")"
    elif [ "$code" = "200" ]; then
      t_say fail "   $(t_mark fail) GET $(printf '%-26s' "$path") $(t_seg fail "200 · ALLOW-LIST BREACH")"
      fail=1
    else
      t_say warn "   $(t_mark warn) GET $(printf '%-26s' "$path") $(t_seg warn "$code")"
    fi
  done

  t_say ink_dim "   ── live signature ────────────"
  local tmpkr
  tmpkr="$(mktemp -d)"
  if GNUPGHOME="$tmpkr" gpg --batch --import "$PUBLIC_DIR/.well-known/pgp-key.asc" >/dev/null 2>&1 &&
    curl -sk -o "$tmpkr/integrity.json" "$base/integrity.json" 2>/dev/null &&
    curl -sk -o "$tmpkr/integrity.json.sig" "$base/integrity.json.sig" 2>/dev/null &&
    GNUPGHOME="$tmpkr" gpg --verify "$tmpkr/integrity.json.sig" "$tmpkr/integrity.json" >/dev/null 2>&1; then
    t_say ink "   $(t_mark pass) $(t_seg ok "Good signature") on the live integrity.json"
  else
    t_say fail "   $(t_mark fail) Live signature did not verify in a throwaway keyring"
    fail=1
  fi
  rm -rf "$tmpkr"

  if [ "$fail" -ne 0 ]; then
    printf '\n'
    t_say fail "$(t_mark fail) Smoke test failed."
    t_say ink_dim "   The previous edition is still live (non-deleting mirror). Do not announce."
    return 1
  fi
  stage13_live
}

# ── 13 · Live ───────────────────────────────────────────────────────────────
stage13_live() {
  t_stage 13 "LIVE" "Shipped."
  printf '\n'
  local commit
  commit="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null)"
  t_panel_open "SHIPPED"
  t_panel_row "Edition" "$EDITION" paper
  [ -n "$NOTE" ] && t_panel_row "Note" "$NOTE"
  t_panel_row "URL" "https://trentpower.fr" ox
  t_panel_row "Editions" "EN-AU · FR"
  [ -n "$commit" ] && t_panel_row "Commit" "main $commit"
  t_panel_row "Host" "Apache · Varnish"
  t_panel_row "Smoke test" "passed" ok
  t_panel_row "Live signature" "verified" ok
  t_panel_close
  printf '\n'
  t_say ok "$(t_mark pass) Edition $EDITION is live, committed and provable."
  if [ "$PUBLIC_RELEASE" = "1" ]; then
    stage14_public
  fi
}

# ── 14 · Public (only in --public-release: flip the GitHub repo public) ──────
stage14_public() {
  t_stage 14 "PUBLIC" "Make the repository public on GitHub. The deploy is proven; this is the reveal."
  printf '\n'
  if ! command -v gh >/dev/null 2>&1; then
    t_say fail "$(t_mark fail) gh CLI not available — flip visibility manually in GitHub Settings."
    return 1
  fi
  local repo visibility
  repo="$(python3 -c "import json;print(json.load(open('$TOOLS_DIR/config/public-release.json'))['repo'])")"
  visibility="$(gh repo view "$repo" --json visibility -q .visibility 2>/dev/null || echo unknown)"
  t_panel_open "PUBLIC RELEASE"
  t_panel_row "Repository" "github.com/$repo" ox
  t_panel_row "Visibility" "$visibility"
  t_panel_sub "consequences"
  t_panel_row "Code" "publicly readable, indexed, forkable" ink_dim
  t_panel_row "History" "every commit on every pushed ref" ink_dim
  t_panel_row "Secrets" "CI secrets stay secret; Actions stay restricted" ink_dim
  t_panel_close
  printf '\n'
  if [ "$visibility" = "PUBLIC" ]; then
    t_say ink "$(t_mark pass) Repository is already public."
    return 0
  fi
  if [ "$PUBLIC_APPROVED" = "1" ]; then
    t_say ink "$(t_mark pass) Public release pre-approved (--yes-public / PUBLIC_RELEASE_APPROVED)"
  elif ! t_is_tty; then
    t_say warn "$(t_mark warn) Non-interactive without pre-approval. Repository stays private."
    t_say ink_dim "   Re-run with --yes-public or PUBLIC_RELEASE_APPROVED=1, or flip manually."
    return 0
  elif ! t_confirm_word "Confirm public release" "PUBLIC" \
    "Type PUBLIC to make github.com/$repo publicly visible. Anything else leaves it private."; then
    printf '\n'
    t_say warn "$(t_mark warn) Public release not confirmed. Repository stays private."
    return 0
  fi
  printf '\n'
  # newer gh requires an explicit consequence acknowledgement; older gh
  # rejects the flag. feature-detect instead of pinning a version.
  if gh repo edit --help 2>/dev/null | grep -q -- --accept-visibility-change-consequences; then
    step "Flip repository public" gh repo edit "$repo" --visibility public --accept-visibility-change-consequences
  else
    step "Flip repository public" gh repo edit "$repo" --visibility public
  fi
  visibility="$(gh repo view "$repo" --json visibility -q .visibility 2>/dev/null || echo unknown)"
  if [ "$visibility" = "PUBLIC" ]; then
    t_say ok "$(t_mark pass) github.com/$repo is public."
  else
    t_say fail "$(t_mark fail) Visibility reads $visibility — verify in GitHub Settings."
    return 1
  fi
}

# ════════════════════════════════════════════════════════════════════════════
# Drive the ceremony.
# ════════════════════════════════════════════════════════════════════════════
splash

if [ "$MODE_EXPLICIT" -eq 0 ] && t_is_tty; then
  stage01_intent
fi

stage02_render
stage03_prepare
stage04_seal
stage05_verify

if [ "$MODE" = "check" ]; then
  check_complete
  exit 0
fi

if [ "$MODE" = "publiccheck" ]; then
  public_gate
  check_complete
  printf '\n'
  t_say ink "$(t_mark pass) Public-readiness check passed. Nothing signed, shipped or revealed."
  exit 0
fi

if [ "$MODE" = "nosign" ]; then
  printf '\n'
  t_say ink "$(t_mark pass) Build complete — not signed (--no-sign)."
  t_say ink_dim "No approval, signature, archives, deploy gate or ship ran."
  exit 0
fi

if [ "$PUBLIC_RELEASE" = "1" ]; then
  public_gate
fi

stage06_review
stage07_approval
stage08_sigverify
stage09_record
ship

printf '\n'
t_say ink_faint "Release artefacts under public/integrity/releases/$EDITION/"
