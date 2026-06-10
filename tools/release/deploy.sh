#!/usr/bin/env bash
# trentpower.fr — build + git push pipeline.
#
# Run from anywhere:
#     bash tools/deploy.sh                    # full build + git commit + push
#     bash tools/deploy.sh --skip-build       # git commit + push without rebuilding
#     bash tools/deploy.sh --help             # this message
#
# Deployment to the live host is handled by git — push here and
# the host picks it up. No SFTP credentials required locally.

set -euo pipefail

# ── Argument parsing ────────────────────────────────────────────
SKIP_BUILD=0
for arg in "$@"; do
  case "$arg" in
  --skip-build) SKIP_BUILD=1 ;;
  --help | -h)
    sed -n '2,9p' "$0" | sed 's/^# \?//'
    exit 0
    ;;
  *)
    echo "deploy.sh: unknown argument '$arg' (try --help)" >&2
    exit 2
    ;;
  esac
done

# ── Path resolution ─────────────────────────────────────────────
TOOLS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$TOOLS_DIR/.." && pwd)"
PUBLIC_DIR="$REPO_ROOT/public"

if [ ! -d "$PUBLIC_DIR" ]; then
  echo "deploy.sh: $PUBLIC_DIR not found — repo layout out of date" >&2
  exit 1
fi

# ── Build (unless skipped) ──────────────────────────────────────
if [ "$SKIP_BUILD" -eq 0 ]; then
  echo "[deploy] running tools/build/build.sh first (use --skip-build to skip)"
  bash "$TOOLS_DIR/build/build.sh"
  echo
fi

# ── Git commit + push ───────────────────────────────────────────
cd "$REPO_ROOT"

if git diff --quiet && git diff --cached --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
  echo "[deploy] nothing to commit — working tree clean"
else
  EDITION=$(python3 -c "import json; print(json.load(open('$TOOLS_DIR/config/identity_canonical.json'))['edition'])")
  git add -A
  git commit -m "Build artefacts · local rebuild + GPG sign $EDITION"
  echo "[deploy] committed build artefacts"
fi

echo "[deploy] pushing to origin main"
git push origin main

echo
echo "OK: build committed and pushed — deployment via git"
