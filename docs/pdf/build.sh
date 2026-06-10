#!/usr/bin/env bash
# Build README.pdf from the editorial HTML using paged.js + system Chromium.
#
#   bash docs/pdf/build.sh
#
# Source of truth is docs/pdf/readme.html; this only paginates + exports.
# Output: README.pdf at the repository root.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
cd "$root"

src="docs/pdf/readme.html"
out="README.pdf"

chrome="$(command -v chromium || command -v chromium-browser || command -v google-chrome || command -v google-chrome-stable || true)"
if [ -z "$chrome" ]; then
  echo "error: no chromium/chrome found on PATH" >&2
  exit 1
fi
echo "chromium: $chrome"
export PUPPETEER_EXECUTABLE_PATH="$chrome"
export PUPPETEER_SKIP_DOWNLOAD=1

# pagedjs-cli paginates the flowing document into A4 and renders via Chromium.
# Installed on demand into the gitignored node_modules (npx --yes).
npx --yes pagedjs-cli "$src" \
  --output "$out" \
  --browserArgs "--no-sandbox,--allow-file-access-from-files,--font-render-hinting=none"

echo "wrote $out"
command -v pdfinfo >/dev/null 2>&1 && pdfinfo "$out" | grep -E '^(Pages|Page size|File size)'

# Publication-layout gate: no overlaps, no clipped text, no orphan headings.
# A failure here means the PDF must not ship — fix the CSS/markup and re-render.
# --review renders every page + a contact sheet into docs/pdf/review/ (local
# only, gitignored) so the export can be eyeballed page by page.
echo "validating layout…"
python3 tools/quality/pdf/validate-layout.py "$out" --review docs/pdf/review

# Semantic gate: chart bars match the repository data they claim to show,
# every referenced asset embedded, display headings extract with their
# spaces intact, edition mentions current.
echo "validating content…"
python3 tools/quality/pdf/validate-content.py "$out"
