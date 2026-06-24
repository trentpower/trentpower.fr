"""generate_public_exposure_manifest.py — emit tools/public-exposure.json.

This manifest is the source of truth for what the public web may serve.
It is a build-source-of-truth artefact: lives under tools/, not public/.
Other validators (gate checks, sw-cache-manifest, edge rules) may
import this file rather than re-enumerating the public surface.
"""

import json
import sys
from collections import OrderedDict
from datetime import UTC, datetime
from fnmatch import fnmatch

# local imports
sys.path.insert(
    0,
    str(
        next(
            _a
            for _a in __import__("pathlib").Path(__file__).resolve().parents
            if _a.name == "tools"
        )
        / "lib"
    ),
)
import public_inventory as inv
import routes as _routes
from paths import IDENTITY_CANONICAL, PUBLIC_DIR, TOOLS_DIR

# ─── manifest static content ─────────────────────────────────────
# every field below is hard-coded to keep the manifest deterministic.
# the only dynamic fields are `edition` (read from identity_canonical)
# and `generated_at` (current utc, seconds precision).

PRINCIPLE = (
    "this manifest is the source of truth for what the public web "
    "may serve; anything not matched here must not be deployed."
)

# the language gate is "/"; every page lives under an /en-au/ or /fr/ tree.
LANGUAGE_ROOTS = [f"/{_routes.lang_url_segment(lang)}/" for lang in _routes.languages()]


def _public_routes() -> list[str]:
    """Trailing-slash directory URLs the public web may serve: the
    language gate, every bilingual page route, and the language-
    neutral diagnostic + source-reader surfaces. Derived from the
    route map so a new route is covered the moment it is declared
    in content/shared/routes.yml. /local/ is the device console
    (replaced /sw-reset/ as the rename target — old path now 301
    via .htaccess)."""
    out = ["/"]
    for key in _routes.route_keys():
        for lang in _routes.languages():
            out.append(_routes.route_path(key, lang))
    out.append("/local/")
    # language-neutral source-reader app surfaces.
    out += ["/source/", "/source/view/"]
    # language-neutral test-results page (renders the signed TESTRESULTS.txt).
    out.append("/tests/")
    # language-neutral public documentation surface (signed README.pdf + text).
    out.append("/documentation/")
    return out


PUBLIC_ROUTES = _public_routes()

# per-tree error documents — one flat .html per language tree, plus the
# root-level set that backstops requests matching neither tree.
_TREE_ERROR_FILES = [
    f"/{_routes.lang_url_segment(lang)}/{err}.html"
    for lang in _routes.languages()
    for err in ("403", "404", "500", "maintenance")
]

PUBLIC_ROOT_FILES = _TREE_ERROR_FILES + [
    "/index.html",
    "/403.html",
    "/404.html",
    "/500.html",
    "/maintenance.html",
    "/robots.txt",
    "/humans.txt",
    "/llms.txt",
    "/ai-usage.txt",
    "/pgp.txt",
    "/assertion.txt",
    "/statement.txt",
    "/changelog.txt",
    "/integrity.json",
    "/integrity.json.sig",
    "/site-metadata.json",
    "/attestations.json",
    "/file-metadata.json",
    "/sw-cache-manifest.json",
    "/SHA256SUMS",
    "/SHA256SUMS.sig",
    "/sitemap.xml",
    "/sitemap.xml.sha256",
    "/manifest.webmanifest",
    "/styles.css",
    "/print.css",
    "/fonts-full.css",
    "/js/theme.js",
    "/sw-register.js",
    "/js/reveal.js",
    "/js/verify-modal.js",
    "/js/copy.js",
    "/js/edition.js",
    "/js/fonts.js",
    "/js/language-gate.js",
    "/js/overlay.js",
    "/js/micro-interactions.js",
    "/js/local.js",
    "/sw.js",
    "/favicon.svg",
    "/favicon.ico",
    "/apple-touch-icon.png",
    "/icon-192.png",
    "/icon-512.png",
]

PUBLIC_WELL_KNOWN_FILES = [
    "/.well-known/security.txt",
    "/.well-known/person.json",
    "/.well-known/webfinger",
    "/.well-known/pgp-key.asc",
    "/.well-known/attribution.sig",
    "/.well-known/attribution.txt",
    "/.well-known/build.json",
    "/.well-known/publication.json",
]

PUBLIC_ASSET_GLOBS = [
    "/fonts/*.woff2",
    "/fonts/subsets/*.woff2",
    "/images/architecture/*.svg",
    "/images/icons/*.png",
    "/images/icons/*.svg",
    "/images/icons/*.ico",
    "/images/og/*.png",
    "/images/portraits/*.jpg",
    "/images/qr/*.svg",
    "/images/textures/*.svg",
]

PUBLIC_VERSIONED_GLOBS = [
    "/fonts-full.????-??-??.*.css",
    "/verify/verification-data.????-??-??.*.js",
]

PUBLIC_VERIFY_FILES = [
    "/verify/verify.js",
    "/verify/verification-data.js",
]

# system b (editorial_copy.json + editorial-copy-review.*) was retired; only the
# copywriter-facing copy-review.* (built from canonical content/en/ YAML) remains.
PUBLIC_EDITORIAL_FILES = [
    "/editorial/copy-review.html",
    "/editorial/copy-review.docx",
    "/editorial/copy-review.pdf",
]

# language-neutral documentation surface. the landing page plus the two
# served artefacts (the signed pdf + the plain-text readme). the .md extension
# is denied site-wide, so the markdown ships as README.txt — the same
# convention the source mirror uses. README.pdf is rendered locally
# (docs/pdf/build.sh) and committed; the main build only copies it into
# public/ and hashes it.
PUBLIC_DOCUMENTATION_FILES = [
    "/documentation/index.html",
    "/documentation/README.pdf",
    "/documentation/README.txt",
]

PUBLIC_SOURCE_GLOBS = [
    "/source/index.html",
    "/source/source-manifest.json",
    "/source/view/index.html",
    "/source/view/source-view.js",
    "/source/view/source-view-manifest.js",
    # mirror text files at every depth: top-level (/source/foo.txt),
    # nested dirs (/source/privacy/index.html.txt), well-known mirror
    # (/source/.well-known/webfinger.txt), and image base64 mirrors
    # (/source/images/icons/favicon.ico.base64.txt). the glob
    # alternation here covers every depth observed on disk.
    "/source/*.txt",
    "/source/**/*.txt",
    "/source/.well-known/*.txt",
    "/source/images/**/*.txt",
    # the readme + htaccess mirror sit at the source root.
    "/source/README.txt",
    "/source/htaccess.txt",
]

# language-neutral test-results page. the trailing-slash route is in
# PUBLIC_ROUTES; the index.html is listed here so the disk↔manifest
# sweep matches it the same way /source/index.html is matched.
PUBLIC_TESTS_GLOBS = [
    "/tests/index.html",
]

# C2PA Content-Credentials surface: signed distribution copies of authored media
# plus a machine index. Named /provenance/ (not /content-credentials/) because
# the secret-name deny filter blocks any path segment containing "credential".
# Signed once, hash-verified via integrity.json, excluded from the rebuild
# fixpoint (see docs/C2PA.md, docs/REPRODUCIBILITY.md).
PUBLIC_PROVENANCE_GLOBS = [
    "/provenance/*.svg",
    "/provenance/index.json",
]

PUBLIC_INTEGRITY_GLOBS = [
    "/integrity/index.html",
    "/integrity/releases/index.html",
    "/integrity/releases/archive.css",
    "/integrity/verify-locally/index.html",
    # per-edition directory route — the trailing-slash URL form, so a
    # link like <a href="/integrity/releases/2026-05-09/"> passes the
    # html-link allow check before mod_dir resolves it to index.html.
    "/integrity/releases/*/",
    "/integrity/releases/*/index.html",
    "/integrity/releases/*/SHA256SUMS",
    "/integrity/releases/*/SHA256SUMS.sig",
    "/integrity/releases/*/trentpower-fr-*.zip",
    "/integrity/releases/*/trentpower-fr-*.zip.sha256",
    "/integrity/releases/*/trentpower-fr-*.zip.sig",
    "/integrity/releases/*/trentpower-fr-*.tar.gz",
    "/integrity/releases/*/trentpower-fr-*.tar.gz.sha256",
    "/integrity/releases/*/trentpower-fr-*.tar.gz.sig",
    "/integrity/releases/*/integrity-redistributable.json",
    "/integrity/releases/*/integrity-redistributable.json.sig",
    # dated rebuild companion: integrity-redistributable-YYYY-MM-DD.json
    # — emitted when an across-day rebuild ships alongside the canonical.
    "/integrity/releases/*/integrity-redistributable-*.json",
    "/integrity/releases/*/integrity-redistributable-*.json.sig",
    # per-edition exclusion manifest. machine-readable list of every
    # file the build deliberately dropped from the archive, signed
    # alongside; lets verifiers tell "missing intentionally" apart
    # from "missing unexpectedly" without downloading the zip.
    "/integrity/releases/*/EXCLUDED_FILES.json",
    "/integrity/releases/*/EXCLUDED_FILES.json.sig",
    "/integrity/releases/*/EXCLUDED_FILES.txt",
    # dated rebuild companion of the exclusion manifest.
    "/integrity/releases/*/EXCLUDED_FILES-*.json",
    "/integrity/releases/*/EXCLUDED_FILES-*.json.sig",
    "/integrity/releases/*/EXCLUDED_FILES-*.txt",
    # per-edition release.json trust anchor. byte-identical to the
    # in-archive copy; lets a verifier follow a single signed file to
    # every other manifest in the release.
    "/integrity/releases/*/release.json",
    "/integrity/releases/*/release.json.sig",
    # dated rebuild companion of the release.json trust anchor.
    "/integrity/releases/*/release-*.json",
    "/integrity/releases/*/release-*.json.sig",
    # per-edition builds index: canonical archive plus any across-day
    # rebuild artefacts dated by build date. .sig signs the json.
    "/integrity/releases/*/builds.json",
    "/integrity/releases/*/builds.json.sig",
    # signed score-ledger attestation (TESTRESULTS.txt + detached .sig):
    # a published snapshot of the checks run against the edition at
    # release time, verifiable against the published key.
    "/integrity/releases/*/TESTRESULTS.txt",
    "/integrity/releases/*/TESTRESULTS.txt.sig",
    # legacy 2026-02 release shape: had its own integrity.json + sig
    # and bundled stylesheets under assets/. covered by direct-child
    # glob plus deep-tree glob so single-segment files match too.
    "/integrity/releases/2026-02/integrity.json",
    "/integrity/releases/2026-02/integrity.json.sig",
    "/integrity/releases/2026-02/assets/*",
    "/integrity/releases/2026-02/assets/**/*",
]

DENY_EXTENSION_PATTERNS = [
    ".php",
    ".phar",
    ".phtml",
    ".asp",
    ".aspx",
    ".jsp",
    ".cgi",
    ".pl",
    ".py",
    ".pyc",
    ".pyo",
    ".sh",
    ".bash",
    ".zsh",
    ".exe",
    ".dll",
    ".so",
    ".env",
    ".ini",
    ".conf",
    ".config",
    ".yaml",
    ".yml",
    ".toml",
    ".lock",
    ".bak",
    ".backup",
    ".old",
    ".orig",
    ".tmp",
    ".swp",
    ".log",
    ".sql",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".db3",
    ".map",
    ".psd",
    ".ai",
    ".fig",
    ".sketch",
    ".md",
]

DENY_PATH_PATTERNS = [
    "**/.git/**",
    "**/.github/**",
    "**/.vscode/**",
    "**/.idea/**",
    "**/.DS_Store",
    "**/Thumbs.db",
    "**/node_modules/**",
    "**/vendor/**",
    "**/private/**",
    "**/src/**",
    "**/tools/**",
    "**/templates/**",
    "**/scripts/**",
    "**/docs/**",
    "**/partials/**",
    "**/_archives/**",
    "**/_licences/**",
    "**/_rollback*/**",
    "**/_audit*/**",
    "**/console_data/**",
    "**/reports/**",
    "**/assets-source/**",
    "**/.template.js",
]

DENY_BASENAME_PATTERNS = [
    ".env",
    ".env.*",
    ".user.ini",
    ".htpasswd",
    "composer.json",
    "composer.lock",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "id_ed25519",
    "id_ed25519.pub",
    "*.totp_key",
    "*-key.txt",
    "identity_canonical.json",
]

# ─── repo-only artefacts ─────────────────────────────────────────
# files that exist in public/ on the build machine but are excluded
# from the sftp deploy by .github/workflows/deploy.yml. the validator
# skips them in both coverage and deny checks because they never
# reach the live web root and therefore cannot be exposed.
#
# keep this list narrow. anything added here weakens the "what is in
# public/ must be deployable and allow-listed" invariant; it should
# only contain artefacts whose exclusion is enforced by the deploy
# pipeline itself (the lftp --exclude-glob list in deploy.yml).
DEPLOY_EXCLUDED_GLOBS = [
    # editorial review .md sources — kept in repo for the review
    # workflow; sftp deploy excludes *.md so they never land on the
    # server. .htaccess additionally denies the .md extension.
    "/editorial/*.md",
    # operator-local rollback backups of .htaccess (e.g.
    # .htaccess.predeny.YYYY-MM-DD.bak). belt-and-braces: these are
    # moved to repo root by the deploy workflow; this rule keeps the
    # validator quiet if one is ever staged in public/ by mistake.
    "/.htaccess.*.bak",
]


# ─── helpers ─────────────────────────────────────────────────────


def _load_edition() -> str:
    with IDENTITY_CANONICAL.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return str(data["edition"])


def _utc_now_iso() -> str:
    # seconds precision, z suffix; no microseconds.
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_denied_by_extension(name: str) -> bool:
    lower = name.lower()
    return any(lower.endswith(ext) for ext in DENY_EXTENSION_PATTERNS)


def _is_denied_by_basename(name: str) -> bool:
    return any(fnmatch(name, pat) for pat in DENY_BASENAME_PATTERNS)


def _url_matched(url: str, exact: set[str], globs: list[str]) -> bool:
    if url in exact:
        return True
    return any(fnmatch(url, g) for g in globs)


def _all_exact_urls() -> set[str]:
    # union of every exact-match url across the manifest's hardcoded lists.
    return set(
        PUBLIC_ROUTES
        + PUBLIC_ROOT_FILES
        + PUBLIC_WELL_KNOWN_FILES
        + PUBLIC_VERIFY_FILES
        + PUBLIC_EDITORIAL_FILES
        + PUBLIC_DOCUMENTATION_FILES
    )


def _all_globs() -> list[str]:
    return (
        PUBLIC_ASSET_GLOBS
        + PUBLIC_VERSIONED_GLOBS
        + PUBLIC_SOURCE_GLOBS
        + PUBLIC_INTEGRITY_GLOBS
        + PUBLIC_TESTS_GLOBS
        + PUBLIC_PROVENANCE_GLOBS
    )


# ─── sanity checks ───────────────────────────────────────────────


def _check_inventory_coverage() -> list[str]:
    # every url in public_inventory must appear (exact or via glob).
    exact = _all_exact_urls()
    globs = _all_globs()
    offenders: list[str] = []
    inventory_urls = (
        list(inv.PUBLIC_PAGES)
        + list(inv.PUBLIC_STYLES)
        + list(inv.PUBLIC_SCRIPTS)
        + list(inv.PUBLIC_FONTS)
        + list(inv.PUBLIC_ICONS)
        + list(inv.PUBLIC_DIAGRAMS)
    )
    for url in inventory_urls:
        # routes ending in '/' are represented by their route entry,
        # e.g. '/privacy/' is in PUBLIC_ROUTES even though disk path
        # is privacy/index.html. accept exact match against the url.
        if _url_matched(url, exact, globs):
            continue
        offenders.append(url)
    return offenders


def _crawl_dir_urls(subdir: str) -> list[str]:
    # walk public/<subdir>/ and return server-rooted urls for every
    # file that is not denied by extension or basename pattern.
    base = PUBLIC_DIR / subdir
    if not base.is_dir():
        return []
    urls: list[str] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        name = path.name
        if _is_denied_by_extension(name):
            continue
        if _is_denied_by_basename(name):
            continue
        rel = path.relative_to(PUBLIC_DIR).as_posix()
        urls.append("/" + rel)
    return urls


def _check_dir_against_manifest(subdir: str, manifest_list: list[str]) -> list[str]:
    # any on-disk file under subdir that is not represented in manifest_list
    # is an offender; adding a new file forces a manifest update.
    declared = set(manifest_list)
    offenders: list[str] = []
    for url in _crawl_dir_urls(subdir):
        if url not in declared:
            offenders.append(url)
    return offenders


# ─── manifest assembly ───────────────────────────────────────────


def _build_manifest(edition: str, generated_at: str) -> "OrderedDict[str, object]":
    m: OrderedDict[str, object] = OrderedDict()
    m["schema"] = "trentpower.public-exposure.v1"
    m["edition"] = edition
    m["generated_at"] = generated_at
    m["principle"] = PRINCIPLE
    m["language_roots"] = LANGUAGE_ROOTS
    m["public_routes"] = PUBLIC_ROUTES
    m["public_root_files"] = PUBLIC_ROOT_FILES
    m["public_well_known_files"] = PUBLIC_WELL_KNOWN_FILES
    m["public_asset_globs"] = PUBLIC_ASSET_GLOBS
    m["public_versioned_globs"] = PUBLIC_VERSIONED_GLOBS
    m["public_verify_files"] = PUBLIC_VERIFY_FILES
    m["public_editorial_files"] = PUBLIC_EDITORIAL_FILES
    m["public_documentation_files"] = PUBLIC_DOCUMENTATION_FILES
    m["public_source_globs"] = PUBLIC_SOURCE_GLOBS
    m["public_integrity_globs"] = PUBLIC_INTEGRITY_GLOBS
    m["public_tests_globs"] = PUBLIC_TESTS_GLOBS
    m["public_provenance_globs"] = PUBLIC_PROVENANCE_GLOBS
    m["deny_extension_patterns"] = DENY_EXTENSION_PATTERNS
    m["deny_path_patterns"] = DENY_PATH_PATTERNS
    m["deny_basename_patterns"] = DENY_BASENAME_PATTERNS
    m["deploy_excluded_globs"] = DEPLOY_EXCLUDED_GLOBS
    return m


# ─── entry point ─────────────────────────────────────────────────


def main() -> int:
    # sanity check 1: inventory coverage.
    missing_inventory = _check_inventory_coverage()
    if missing_inventory:
        print("FAIL: public_inventory urls not represented in manifest:", file=sys.stderr)
        for u in missing_inventory:
            print(f"  - {u}", file=sys.stderr)
        return 1

    # sanity check 2: well-known on-disk vs manifest.
    wk_offenders = _check_dir_against_manifest(".well-known", PUBLIC_WELL_KNOWN_FILES)
    if wk_offenders:
        print("FAIL: .well-known files on disk missing from manifest:", file=sys.stderr)
        for u in wk_offenders:
            print(f"  - {u}", file=sys.stderr)
        return 1

    # sanity check 3: editorial on-disk vs manifest.
    ed_offenders = _check_dir_against_manifest("editorial", PUBLIC_EDITORIAL_FILES)
    if ed_offenders:
        print("FAIL: editorial files on disk missing from manifest:", file=sys.stderr)
        for u in ed_offenders:
            print(f"  - {u}", file=sys.stderr)
        return 1

    # sanity check 4: documentation on-disk vs manifest.
    doc_offenders = _check_dir_against_manifest("documentation", PUBLIC_DOCUMENTATION_FILES)
    if doc_offenders:
        print("FAIL: documentation files on disk missing from manifest:", file=sys.stderr)
        for u in doc_offenders:
            print(f"  - {u}", file=sys.stderr)
        return 1

    edition = _load_edition()
    generated_at = _utc_now_iso()
    manifest = _build_manifest(edition, generated_at)

    out_path = TOOLS_DIR / "config" / "public-exposure.json"
    text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    out_path.write_text(text, encoding="utf-8")

    n_routes = len(PUBLIC_ROUTES)
    n_root = len(PUBLIC_ROOT_FILES)
    n_wk = len(PUBLIC_WELL_KNOWN_FILES)
    n_assets = len(PUBLIC_ASSET_GLOBS)
    n_versioned = len(PUBLIC_VERSIONED_GLOBS)
    n_verify = len(PUBLIC_VERIFY_FILES)
    n_editorial = len(PUBLIC_EDITORIAL_FILES)
    n_source = len(PUBLIC_SOURCE_GLOBS)
    n_integrity = len(PUBLIC_INTEGRITY_GLOBS)
    n_tests = len(PUBLIC_TESTS_GLOBS)
    n_provenance = len(PUBLIC_PROVENANCE_GLOBS)
    print(
        f"OK: public-exposure.json written "
        f"({n_routes} routes, {n_root} root files, {n_wk} well-known, "
        f"{n_assets} asset globs, {n_versioned} versioned globs, "
        f"{n_verify} verify files, {n_editorial} editorial files, "
        f"{n_source} source globs, {n_integrity} integrity globs, "
        f"{n_tests} tests globs, {n_provenance} provenance globs)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
