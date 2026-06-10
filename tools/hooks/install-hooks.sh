#!/usr/bin/env bash
# tools/install-hooks.sh — install the repo's git hooks (.git/hooks is not tracked).
# Symlinks tools/hooks/* into .git/hooks/ so updates to the tracked hook propagate.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
HOOK_SRC="$ROOT/tools/hooks"
HOOK_DST="$ROOT/.git/hooks"

mkdir -p "$HOOK_DST"
for src in "$HOOK_SRC"/*; do
  name="$(basename "$src")"
  chmod +x "$src"
  ln -sf "../../tools/hooks/$name" "$HOOK_DST/$name"
  echo "installed: .git/hooks/$name -> tools/hooks/$name"
done

echo "done. commit a staged source file to test; QUALITY_ENFORCE=1 to make it blocking."
