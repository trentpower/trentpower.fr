"""tools/lib/paths.py — single source of truth for project paths.

All build, validation, and packaging scripts import from this module
rather than computing parent.parent / "public" inline. Changing the
layout once here propagates everywhere.

Layout (responsibility pillars under tools/):
    REPO_ROOT/
        public/         ← deployable bytes (web root)
        styles/         ← authored design source css (build input)
        templates/      ← js template inputs
        tools/
            build/      ← creates the site (incl. build/copy, build/fonts)
            quality/    ← gates, lint, validators (incl. quality/pdf, quality/tests)
            verify/     ← integrity / signature / mirror verification
            release/    ← sign, package, deploy (incl. release/server)
            config/     ← declared facts the pipeline reads/checks against
            lib/        ← shared modules (this dir)
            score-ledger/ ← local audit, never a build gate
        metadata/       ← persistent build state (committed; never code)
        docs/           ← internal documentation
"""

from pathlib import Path

# this file lives at REPO_ROOT/tools/lib/paths.py.
REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DIR = REPO_ROOT / "public"
TOOLS_DIR = REPO_ROOT / "tools"
TEMPLATES_DIR = REPO_ROOT / "templates"
DOCS_DIR = REPO_ROOT / "docs"

# authored design source css — peer of templates/, minified into public/.
STYLES_DIR = REPO_ROOT / "styles"
STYLES_SRC = STYLES_DIR / "styles.src.css"
PRINT_SRC = STYLES_DIR / "print.src.css"
FONTS_FULL_SRC = STYLES_DIR / "fonts-full.src.css"

# bilingual copy compilation (was i18n/; no runtime i18n remains).
COPY_DIR = TOOLS_DIR / "build" / "copy"
COPY_STRINGS = COPY_DIR / "strings.json"
# backwards-compat aliases for the former I18N_* names.
I18N_DIR = COPY_DIR
I18N_STRINGS = COPY_STRINGS

# font-subset glyph lists + editorial reference asset (build inputs).
FONT_SUBSETS_DIR = TOOLS_DIR / "build" / "fonts"
EDITORIAL_REFERENCE_DOCX = TOOLS_DIR / "build" / "assets" / "editorial-review-reference.docx"

# declared facts the pipeline reads and checks against.
CONFIG_DIR = TOOLS_DIR / "config"
IDENTITY_CANONICAL = CONFIG_DIR / "identity_canonical.json"
PUBLIC_EXPOSURE = CONFIG_DIR / "public-exposure.json"
SOURCE_MIRROR_EXCLUSIONS = CONFIG_DIR / "source-mirror-exclusions.json"
DATE_OVERRIDES = CONFIG_DIR / "date_overrides.json"

# editorial content source tree (build input, never deployed).
#   content/shared/   ← routes, release, gate copy
#   content/en/       ← english copy YAML
#   content/fr/       ← french copy YAML
CONTENT_DIR = REPO_ROOT / "content"
ROUTES_YML = CONTENT_DIR / "shared" / "routes.yml"
SERVER_DIR = TOOLS_DIR / "release" / "server"

# persistent build state — kept OUT of tools/ (code) so state and
# code do not mix. both files are committed to git: archive-baseline
# is the release-archive immutability trust anchor; content-history
# is the first-seen-date oracle that gives every page an honest
# modified date across rebuilds.
METADATA_DIR = REPO_ROOT / "metadata"
ARCHIVE_BASELINE = METADATA_DIR / "archive-baseline.json"
CONTENT_HISTORY = METADATA_DIR / "content-history.json"

# build outputs that live under public/ but are regenerated each build.
SITE_METADATA = PUBLIC_DIR / "site-metadata.json"  # asset_version + edition

# Build-machinery scratch space. generators that need a temp file
# should write under TMP_DIR (gitignored at .build/) rather than
# leaking files into public/, tools/ or repo root.
TMP_DIR = REPO_ROOT / ".build"

# Backwards-compat alias — early audit deliverables referenced
# BUILD_METADATA as a generic name for the asset_version oracle.
# keep both names so future scripts can use either.
BUILD_METADATA = SITE_METADATA

# js template inputs.
APP_TEMPLATE = TEMPLATES_DIR / "app.template.js"
VERIFY_MODAL_TEMPLATE = TEMPLATES_DIR / "verify-modal.template.js"
