#!/bin/bash
# CSP Hash Regeneration Helper — trentpower.fr
#
# DIAGNOSTIC TOOL ONLY. The everyday CSP-hash sweep is automatic
# inside generate_site.py — this script is a manual-inspection helper
# for ad-hoc debugging. It does NOT run as part of tools/build.sh.
#
# Outputs the complete CSP header line ready to paste into .htaccess.
#
# Usage (from repo root):
#   bash tools/csp-hashes.sh
#
# Replace the Content-Security-Policy line in public/.htaccess with the
# output below "=== PASTE LINE ===". Portable: works on macOS (no grep -P).

set -euo pipefail

# Resolve repo root from this script's location, then operate inside
# public/. Robust against cwd; no assumption that the operator has
# already cd'd into public/.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT/public"

hashes=""

for html in index.html privacy/index.html integrity/index.html \
  security/acknowledgments/index.html 404.html 403.html \
  maintenance.html integrity/releases/index.html; do

  [ -f "$html" ] || continue

  # JSON-LD blocks
  perl -0777 -ne 'while (/<script type="application\/ld\+json">(.*?)<\/script>/gs) { print "$1\n---SPLIT---\n" }' "$html" 2>/dev/null | while IFS= read -r line; do
    [ "$line" = "---SPLIT---" ] && continue
    [ -z "$line" ] && continue
    hash=$(printf '%s' "$line" | openssl dgst -sha256 -binary | openssl base64)
    echo "sha256-${hash}"
  done

  # Speculation rules
  spec=$(perl -0777 -ne 'while (/<script type="speculationrules">(.*?)<\/script>/gs) { print $1 }' "$html" 2>/dev/null)
  if [ -n "$spec" ]; then
    hash=$(printf '%s' "$spec" | openssl dgst -sha256 -binary | openssl base64)
    echo "sha256-${hash}"
  fi

done | sort -u | while read -r h; do
  hashes="${hashes} '${h}'"
  echo "$hashes" >/tmp/csp-hashes-tmp
done

hashes=$(cat /tmp/csp-hashes-tmp 2>/dev/null || echo "")
rm -f /tmp/csp-hashes-tmp

echo ""
echo "Individual hashes:"
echo "$hashes" | tr ' ' '\n' | grep sha256 | sed 's/^/  /'
echo ""
echo "=== PASTE INTO .htaccess (replace the existing CSP line) ==="
echo ""
echo "  Header always set Content-Security-Policy \"default-src 'none'; upgrade-insecure-requests; block-all-mixed-content; script-src 'self'${hashes}; style-src 'self'; font-src 'self'; img-src 'self'; manifest-src 'self'; worker-src 'self'; connect-src 'none'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'; form-action 'none'\""
echo ""
