#!/usr/bin/env python3
"""
trentpower.fr
Generate /source/, the public source-mirror tree.

Inputs:
- final rendered public files
- canonical route inventory (MIRROR allowlist below)
- site metadata

Outputs:
- /source/*.txt mirrors
- /source/source-manifest.json
- /source/index.html (grouped catalogue)

Constraints:
- Mirror only the allowlist; never private templates, secrets, or
  build logs.
- Run after generate_sri.py so mirrored HTML reflects current SRI
  attributes:

    python3 generate_site.py
    python3 generate_sri.py
    python3 generate_source_view.py
    python3 generate_sw.py
    python3 generate_integrity.py
    gpg --detach-sign --armor -o integrity.json.sig integrity.json
"""

import json
import os
import pathlib
import re
import sys
from datetime import UTC, datetime

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
import routes as _routes
from hashing import sha256_b64  # noqa: E402
from paths import (
    CONTENT_DIR as _CONTENT_DIR,
)
from paths import (
    IDENTITY_CANONICAL as IDENTITY_CANONICAL,
)
from paths import (
    PUBLIC_DIR as ROOT,
)
from paths import (
    REPO_ROOT as _REPO_ROOT,
)
from paths import (
    TEMPLATES_DIR as _TEMPLATES_DIR,
)
from slugs import i18n_slug  # noqa: E402

os.chdir(ROOT)

SOURCE_DIR = ROOT / "source"

# Per-mirror source override. the /source/ surface is an editorial
# transparency mirror; when a destination has an authored source, we
# mirror that authored source rather than the compact production
# bytes. the mapped path itself is not exposed in the public mirror —
# only a one-line "authored source" banner is emitted, so the mirror
# remains self-describing without leaking the build layout.
SOURCE_MIRROR_MAP = {
    "styles.css.txt": _REPO_ROOT / "styles" / "styles.src.css",
    "print.css.txt": _REPO_ROOT / "styles" / "print.src.css",
    "fonts-full.css.txt": _REPO_ROOT / "styles" / "fonts-full.src.css",
    "theme.js.txt": _TEMPLATES_DIR / "theme.template.js",
    "sw-register.js.txt": _TEMPLATES_DIR / "sw-register.template.js",
    "reveal.js.txt": _TEMPLATES_DIR / "reveal.template.js",
    "verify-modal.js.txt": _TEMPLATES_DIR / "verify-modal.template.js",
    "copy.js.txt": _TEMPLATES_DIR / "copy.template.js",
    "edition.js.txt": _TEMPLATES_DIR / "edition.template.js",
    "overlay.js.txt": _TEMPLATES_DIR / "overlay.template.js",
    "fonts.js.txt": _TEMPLATES_DIR / "fonts.template.js",
    "micro-interactions.js.txt": _TEMPLATES_DIR / "micro-interactions.template.js",
    "local.js.txt": _TEMPLATES_DIR / "local.template.js",
}
_AUTHORED_BANNER_CSS = b"/*! trentpower.fr \xc2\xb7 authored source */\n"
_AUTHORED_BANNER_JS = b"/*! trentpower.fr \xc2\xb7 authored source */\n"
# the apache config mirror carries an explicit framing so a reader
# understands the published copy is a transparency artefact, not a
# deployment snapshot — and that operational details may be elided.
_HTACCESS_TRANSPARENCY_BANNER = (
    b"# public transparency copy.\n"
    b"# this is a sanitised text rendering of the apache policy used by trentpower.fr.\n"
    b"# it is published for auditability and may omit comments, paths, or operational details\n"
    b"# that are not necessary to understand the public security posture.\n"
    b"\n"
)

# per-line patterns elided from the published mirror. each entry is a
# substring; any line that contains it is dropped before the banner is
# prepended. used for operational filenames where the deny rule must
# stay live on the server but the exact name does not need to be
# published. line removal keeps the deployed .htaccess byte-stable;
# only the mirror is sanitised.
_HTACCESS_MIRROR_REDACTIONS = [
    "id_ed25519",
]


def _htaccess_mirror_transform(raw: bytes) -> bytes:
    """Return the bytes that should land in source/htaccess.txt for a
    given raw public/.htaccess byte stream. Applies line-wise redaction
    of operational filenames, then prepends the transparency banner.
    Shared with validate_source_mirrors.py so byte-equality is honest."""
    text = raw.decode("utf-8")
    kept_lines = [
        ln
        for ln in text.splitlines(keepends=True)
        if not any(needle in ln for needle in _HTACCESS_MIRROR_REDACTIONS)
    ]
    redacted = "".join(kept_lines).encode("utf-8")
    return _HTACCESS_TRANSPARENCY_BANNER + redacted


# explicit allowlist. no globs, no recursion. if a future asset should
# be mirrored, add it here deliberately.
#
# mirror destinations preserve directory structure under /source/.
# the convention is: append .txt to the full live-URL path.
#
# Examples:
#   /index.html             → /source/index.html.txt
#   /privacy/index.html     → /source/privacy/index.html.txt
#   /styles.css             → /source/styles.css.txt
#   /.well-known/person.json → /source/.well-known/person.json.txt
#
# this makes the mirror tree shape identical to the live tree, so a
# visitor can reason about /source/<live-url>.txt for any public file.
#
# no /source/source/* tree.
#   the rendered source page lives at /source/index.html and is its
#   own entry point; it does not get a self-mirror under /source/source/.
#   the brief explicitly forbids /source/source/ paths; the only
#   tolerated entries under /source/ are index.html, *.txt mirrors,
#   source-manifest.json (+ .txt), README.txt, and the images/ subtree
#   for binary mirrors. a self-mirror at /source/source/index.html.txt
#   would re-introduce a recursive level and is no longer generated.
#
# special cases:
#   - source-manifest.json lives natively in /source/ and gets a
#     byte-equal /source/source-manifest.json.txt mirror at the same
#     level.
#   - .htaccess uses "htaccess.txt" (no leading dot) so apache does
#     not surface it under hidden-file rules; display_name() restores
#     the leading dot for the visible row.


def _page_mirror_entries() -> list:
    """The page portion of MIRROR, derived from the route map so the
    /source/ mirror tree tracks the bilingual /en/ + /fr/ editions
    automatically. A new page route is mirrored the moment it is
    declared in content/shared/routes.yml.

    Appended explicitly (not route-map entries): the language gate at
    /, the neutral service-worker recovery page, the per-tree and root
    error documents, and the frozen release-page snapshots.
    """
    pages = ["index.html"]  # the language gate
    for key in _routes.route_keys():
        # not mirrored:
        #  · source-view — the reader-app shells (/en/source/view/,
        #    /fr/source/voir/) are reader chrome, not editorial pages, and
        #    carry a build-volatile SRI for source-view-manifest.js;
        #    mirroring would fold that hash into the manifest they verify.
        #  · source — the /en/source/ and /fr/source/ catalogue pages
        #    receive a generator-spliced registry below; mirroring them
        #    would fold the registry's own hashes back into itself.
        # both are convergence cycles, and like the root /source/ and
        # /source/view/ pages these are not themselves catalogued.
        if key in ("source", "source-view"):
            continue
        for lang in _routes.languages():
            pages.append(_routes.route_output(key, lang))
    pages.append("local/index.html")
    pages.append("tests/index.html")
    pages.append("documentation/index.html")
    errors = ("403.html", "404.html", "500.html", "maintenance.html")
    for lang in _routes.languages():
        for err in errors:
            pages.append(f"{_routes.lang_url_segment(lang)}/{err}")
    pages.extend(errors)  # root-level fallbacks for unmatched requests
    # per-edition release-record pages — every dated edition directory
    # under integrity/releases/ that carries an index.html. discovered
    # by glob so a freshly-cut edition is mirrored without restating it
    # here; the undated legacy 2026-02 archive keeps its own shape and
    # is intentionally not matched.
    import glob as _glob

    pages += sorted(
        _glob.glob("integrity/releases/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]/index.html")
    )
    return [(p, p + ".txt") for p in pages]


# explicit allowlist, page portion + asset portion. the page portion is
# route-map-derived (above); the asset portion below is hand-listed —
# stylesheets, scripts, machine-readable records and the apache config.
MIRROR = _page_mirror_entries() + [
    # path on the live site                       /source/<dst> destination
    ("styles.css", "styles.css.txt"),
    ("print.css", "print.css.txt"),
    ("fonts-full.css", "fonts-full.css.txt"),
    ("js/theme.js", "theme.js.txt"),
    ("sw-register.js", "sw-register.js.txt"),
    ("js/reveal.js", "reveal.js.txt"),
    ("js/verify-modal.js", "verify-modal.js.txt"),
    ("js/copy.js", "copy.js.txt"),
    ("js/edition.js", "edition.js.txt"),
    ("js/overlay.js", "overlay.js.txt"),
    ("js/fonts.js", "fonts.js.txt"),
    ("js/language-gate.js", "language-gate.js.txt"),
    ("js/micro-interactions.js", "micro-interactions.js.txt"),
    ("js/local.js", "local.js.txt"),
    ("sw.js", "sw.js.txt"),
    ("manifest.webmanifest", "manifest.webmanifest.txt"),
    ("humans.txt", "humans.txt.txt"),
    ("llms.txt", "llms.txt.txt"),
    ("robots.txt", "robots.txt.txt"),
    ("changelog.txt", "changelog.txt.txt"),
    ("ai-usage.txt", "ai-usage.txt.txt"),
    ("assertion.txt", "assertion.txt.txt"),
    ("statement.txt", "statement.txt.txt"),
    ("pgp.txt", "pgp.txt.txt"),
    ("sitemap.xml", "sitemap.xml.txt"),
    ("sitemap.xml.sha256", "sitemap.xml.sha256.txt"),
    ("attestations.json", "attestations.json.txt"),
    ("site-metadata.json", "site-metadata.json.txt"),
    ("sw-cache-manifest.json", "sw-cache-manifest.json.txt"),
    ("verify/verify.js", "verify/verify.js.txt"),
    # verify/verification-data.js not mirrored: it embeds per-route
    # SHA-256 records read from integrity.json; mirroring it would
    # close a hashing loop (mirror bytes → integrity.json → next-build
    # verification-data.js bytes → mirror bytes …). excluded in
    # tools/source-mirror-exclusions.json. visitors can read the live
    # /verify/verification-data.js directly — it is itself the public
    # source.
    ("integrity/releases/archive.css", "integrity/releases/archive.css.txt"),
    (".well-known/person.json", ".well-known/person.json.txt"),
    (".well-known/security.txt", ".well-known/security.txt.txt"),
    (".well-known/attribution.txt", ".well-known/attribution.txt.txt"),
    (".well-known/pgp-key.asc", ".well-known/pgp-key.asc.txt"),
    (".well-known/webfinger", ".well-known/webfinger.txt"),
    (".well-known/publication.json", ".well-known/publication.json.txt"),
    (".well-known/build.json", ".well-known/build.json.txt"),
    (".htaccess", "htaccess.txt"),
]


# ── editorial entry metadata ─────────────────────────────────────
# Per-file editorial metadata: conceptual group, one-sentence
# description (what it is, why it exists), and an optional role
# label for quietly distinguishing critical files. keys are mirror
# destination names (dst_name from mirror) plus synthesised entries
# (README.txt, source-manifest.json.txt, verification rows). files
# absent here fall back to the legacy kind-based group.
#
# the descriptions are the editorial voice of the page. they must
# stay terse, factual, and consistent with the registers used on
# /integrity/, /verify/ and /security/. no marketing language, no
# hedging, no buzzwords. each line should justify why the file
# exists in public.
#
# role labels are restrained text, not badges. they sit inline at
# the head of the description in a quiet mono register, marking the
# few files that carry the trust system: the signed manifest, the
# detached signature, the public signing key, the canonical
# identity record, the disclosure surface.
ENTRY_META: dict[str, dict] = {
    # ── Pages: readable surfaces of the public site ──────────────
    "index.html.txt": {
        "group": "pages",
        "description": "Home page. The editorial entry point.",
    },
    "privacy/index.html.txt": {
        "group": "pages",
        "description": "Privacy statement. What is collected, retained and shared.",
    },
    "integrity/index.html.txt": {
        "group": "pages",
        "description": "Integrity overview. The signed manifest, key and release authority.",
    },
    "integrity/releases/index.html.txt": {
        "group": "pages",
        "description": "Release index. The list of signed editions.",
    },
    "integrity/releases/2026-05-09/index.html.txt": {
        "group": "pages",
        "description": "Frozen page record for the 2026-05-09 edition.",
    },
    "integrity/releases/2026-05-17/index.html.txt": {
        "group": "pages",
        "description": "Frozen page record for the 2026-05-17 edition.",
    },
    "integrity/verify-locally/index.html.txt": {
        "group": "pages",
        "description": "Detached verification notes. The shell commands that check the signed manifest locally.",
    },
    "security/index.html.txt": {
        "group": "pages",
        "description": "Security posture. Architecture, headers and disclosure path.",
    },
    "security/acknowledgments/index.html.txt": {
        "group": "pages",
        "description": "Acknowledgments for public security disclosures.",
    },
    "verify/index.html.txt": {
        "group": "pages",
        "description": "Verification interface. Page-level fingerprint checks.",
    },
    "local/index.html.txt": {
        "group": "pages",
        "description": "Local Device Console. Inspect and clear the offline cache and local preferences for this device.",
    },
    "tests/index.html.txt": {
        "group": "pages",
        "description": "Test results. Signed verification snapshot of the published edition.",
    },
    "documentation/index.html.txt": {
        "group": "pages",
        "description": "Documentation. The signed README.pdf and plain-text README, with the PDF's hash for verification.",
    },
    "404.html.txt": {
        "group": "pages",
        "description": "Not found page.",
    },
    "403.html.txt": {
        "group": "pages",
        "description": "Forbidden page.",
    },
    "500.html.txt": {
        "group": "pages",
        "description": "Server error page.",
    },
    "maintenance.html.txt": {
        "group": "pages",
        "description": "Maintenance notice. Used during planned downtime.",
    },
    # ── Identity: canonical identity records ─────────────────────
    ".well-known/person.json.txt": {
        "group": "identity",
        "role": "Canonical identity record",
        "description": "Machine-readable identity in JSON-LD. The reference used by discovery, federation and verification.",
    },
    ".well-known/webfinger.txt": {
        "group": "identity",
        "role": "Identity discovery",
        "description": "WebFinger discovery surface. Resolves identity across federated protocols.",
    },
    ".well-known/publication.json.txt": {
        "group": "identity",
        "description": "Publication record. Describes the site as a self-managed editorial work.",
    },
    ".well-known/attribution.txt.txt": {
        "group": "identity",
        "description": "Author attribution. Names the responsible party for the public site.",
    },
    "humans.txt.txt": {
        "group": "identity",
        "description": "Credits and notes for the people behind the site.",
    },
    # ── Policies: public commitments and disclosure ──────────────
    ".well-known/security.txt.txt": {
        "group": "policies",
        "role": "Public trust surface",
        "description": "Coordinated disclosure policy. Standard /.well-known/security.txt contact and scope.",
    },
    "ai-usage.txt.txt": {
        "group": "policies",
        "description": "Statement of AI usage and policy for the site.",
    },
    "assertion.txt.txt": {
        "group": "policies",
        "description": "Authorship assertion. Declaration of authorship and integrity intent.",
    },
    "statement.txt.txt": {
        "group": "policies",
        "description": "Editorial statement. The site's authoring principles.",
    },
    "pgp.txt.txt": {
        "group": "policies",
        "description": "PGP statement. The signing key fingerprint and its use.",
    },
    # ── Discovery: crawler and ai guidance ───────────────────────
    "sitemap.xml.txt": {
        "group": "discovery",
        "description": "Public sitemap. URL inventory for crawlers.",
    },
    "robots.txt.txt": {
        "group": "discovery",
        "description": "Crawler access policy and public indexing intent.",
    },
    "llms.txt.txt": {
        "group": "discovery",
        "description": "Machine-readable guidance for language models and AI systems.",
    },
    "changelog.txt.txt": {
        "group": "discovery",
        "description": "Edition change log. Notable revisions to the public site.",
    },
    # ── source code: authored stylesheets and scripts ────────────
    "styles.css.txt": {
        "group": "source-mirrors",
        "description": "Authored stylesheet. Mirrored from source, not the minified deployed bytes.",
    },
    "print.css.txt": {
        "group": "source-mirrors",
        "description": "Print stylesheet. Layout rules for paper output.",
    },
    "fonts-full.css.txt": {
        "group": "source-mirrors",
        "description": "Webfont declarations. Subsets, formats and fallbacks.",
    },
    "theme.js.txt": {
        "group": "source-mirrors",
        "description": "Theme toggle and the html.js / html.enhanced enhancement flags.",
    },
    "sw-register.js.txt": {
        "group": "source-mirrors",
        "description": "Service-worker registration and the tp-app Trusted Types policy.",
    },
    "reveal.js.txt": {
        "group": "source-mirrors",
        "description": "Scroll-reveal — fades sections in as they enter the viewport.",
    },
    "overlay.js.txt": {
        "group": "source-mirrors",
        "description": "Shared overlay lifecycle — focus trap, scroll lock, the cite and project modals.",
    },
    "copy.js.txt": {
        "group": "source-mirrors",
        "description": "Shared copy-to-clipboard behaviour, driven by data-copy attributes.",
    },
    "edition.js.txt": {
        "group": "source-mirrors",
        "description": "Footer edition-age localisation. Reads body[data-edition] and rewrites [data-edition-age] in the document language.",
    },
    "fonts.js.txt": {
        "group": "source-mirrors",
        "description": "Post-paint full-font upgrade. Swaps the subset fonts for the full set.",
    },
    "verify-modal.js.txt": {
        "group": "source-mirrors",
        "description": "Verify action menu. Five-row overlay handing off to source, citation, integrity, verify and print.",
    },
    "verify/verify.js.txt": {
        "group": "source-mirrors",
        "description": "Verification logic. Renders a page record from the verification map.",
    },
    "integrity/releases/archive.css.txt": {
        "group": "source-mirrors",
        "description": "Stylesheet used inside frozen release archives. Held alongside its release records.",
    },
    # ── offline & app surface (folded into adjacent groups) ──────
    # phase 61 · the service worker is an authored runtime script,
    # so it sits with the other authored scripts under source
    # mirrors. the cache manifest and installable web-app manifest
    # are machine-readable json, so they sit with the other
    # manifests.
    "sw.js.txt": {
        "group": "source-mirrors",
        "description": "Service worker. Offline cache for the public site.",
    },
    "manifest.webmanifest.txt": {
        "group": "machine-readable",
        "description": "Web app manifest. Installable surface metadata.",
    },
    "sw-cache-manifest.json.txt": {
        "group": "machine-readable",
        "description": "Service worker cache manifest. Files pinned for offline use.",
    },
    # ── Machine-readable records ─────────────────────────────────
    "site-metadata.json.txt": {
        "group": "machine-readable",
        "description": "Site-level metadata. Edition, build, asset version.",
    },
    "attestations.json.txt": {
        "group": "machine-readable",
        "description": "Public attestations. Verifiable claims about the site.",
    },
    ".well-known/build.json.txt": {
        "group": "machine-readable",
        "description": "Build record. Reproducibility data for the current edition.",
    },
    "source-manifest.json.txt": {
        "group": "machine-readable",
        "description": "Manifest of the /source/ tree itself. Every mirrored file with its hash.",
    },
    "sitemap.xml.sha256.txt": {
        "group": "machine-readable",
        "description": "Source mirror of the SHA-256 checksum for sitemap.xml.",
    },
    "README.txt": {
        "group": "machine-readable",
        "description": "Orientation note for the source tree. Same text shipped at the root of every release archive.",
    },
    # ── server config folds into machine-readable ───────────────
    # phase 61 · apache configuration is read by the http server,
    # so it belongs with the other machine-read infrastructure
    # files rather than as its own one-row section.
    "htaccess.txt": {
        "group": "machine-readable",
        "description": "Apache configuration. Public-safety scanned before mirroring.",
    },
    # phase 61 · the verification authority surface has moved to
    # /integrity/. /source/ no longer hosts integrity.json,
    # integrity.json.sig, sha256sums, SHA256SUMS.sig or the live
    # sitemap.xml.sha256 row. only the .well-known/pgp-key.asc
    # mirror remains in the catalogue, under identity, where it
    # belongs as the publisher's signing identity rather than as
    # a verification claim.
    ".well-known/pgp-key.asc.txt": {
        "group": "identity",
        "description": "ASCII-armoured public signing key. The publisher's signing identity.",
    },
}

# Public-safety scan run on .htaccess before mirroring it. we target
# actual secret values, not pattern declarations , the active .htaccess
# legitimately contains filesmatch directives that deny filenames
# matching strings like "invoice", "credential", "password", which is
# private-file blocking (a public-safe security feature). the scan
# therefore looks for things that would only appear if a secret leaked
# in: literal local paths, sftp hostnames, ipv4 in private ranges,
# inline credential assignments, or pgp private-key markers.
HTACCESS_BLOCK_PATTERNS = [
    r"/home/[A-Za-z]",
    r"/Users/[A-Za-z]",
    r"sftp\.sd3\.gpaas\.net",
    r"sftp://",
    r"BEGIN PGP PRIVATE",
    r"AuthBasicProvider\s+file",
    r"AuthUserFile\s+\S",
    r"\bPassword\s*=\s*\S",
    r"\bSecret\s*=\s*\S",
    r"\bApiKey\s*=\s*\S",
    r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
    r"\bquick\s+fix\b",
    r"\bAsk\s+Trent\b",
]


# ── per-language source copy ─────────────────────────────────────
# the rendered /en-au/source/ and /fr/source/ catalogue pages are
# template-rendered from content/<lang>/pages/source.yml, but the
# exhaustive registry is spliced in by this generator (see the
# bilingual-parity splice in main()). to keep the spliced registry in
# the page's own language, the splice reads the same per-language YAML
# the template renderer reads, so group headings, glosses and per-file
# descriptions land in french on the french tree. the english
# GROUP_FALLBACK / GLOSS_FALLBACK / ENTRY_META dicts remain only as a
# true last-resort fallback (and as the source for the neutral root
# /source/index.html, which carries no language tree).
_SOURCE_COPY_CACHE: dict[str, dict] = {}


def _source_copy(lang: str | None) -> dict:
    """Return the `source:` mapping from content/<lang>/pages/source.yml.

    `lang` is the internal language key ('en', 'fr'). Returns {} for the
    neutral root catalogue (lang is None) or if the file is absent/empty,
    so callers fall back to the english hardcoded dicts."""
    if not lang:
        return {}
    if lang in _SOURCE_COPY_CACHE:
        return _SOURCE_COPY_CACHE[lang]
    import yaml as _yaml

    path = _CONTENT_DIR / lang / "pages" / "source.yml"
    data: dict = {}
    if path.is_file():
        try:
            loaded = _yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            data = (loaded.get("source") or {}) if isinstance(loaded, dict) else {}
        except Exception:
            data = {}
    _SOURCE_COPY_CACHE[lang] = data
    return data


def kind_from_name(name: str) -> str:
    if name == "htaccess.txt":
        return "apache"
    if name.endswith(".html.txt"):
        return "html"
    if name.endswith(".css.txt"):
        return "css"
    if name.endswith(".js.txt"):
        return "js"
    if name.endswith((".json.txt", ".json")):
        return "json"
    if name.endswith((".webmanifest.txt",)):
        return "json"
    if name.endswith(".txt.txt") or name.endswith(".txt"):
        return "text"
    return "file"


def display_name(name: str) -> str:
    """How the mirror file appears in the /source/ directory listing.
    htaccess.txt → .htaccess (canonical filename; the .txt extension on
    the mirror is a serving convention, not part of the original file's
    name). all other *.txt mirrors collapse the .txt suffix so the row
    reads as the canonical file (index.html, styles.css, …)."""
    if name == "htaccess.txt":
        return ".htaccess"
    if name.endswith(".txt"):
        return name[:-4]
    return name


def public_safety_scan(text: str, label: str) -> None:
    """Block the build if a mirrored config contains anything private."""
    import re as _re

    bad = []
    for pattern in HTACCESS_BLOCK_PATTERNS:
        if _re.search(pattern, text, _re.IGNORECASE):
            bad.append(pattern)
    if bad:
        raise SystemExit(
            f"public-safety scan failed for {label}: "
            f"matched blocked pattern(s) {bad}. Mirror aborted."
        )


from sizes import humanise_bytes as _humanise_bytes  # noqa: E402


def fmt_size(n: int) -> str:
    # thin wrapper around the unified formatter so source-manifest and
    # source-index render identical strings to what they did before:
    # sub-kilobyte values keep the short "n b" form, KB/MB use one
    # decimal place across the board.
    if n < 1024:
        return f"{n} B"
    return _humanise_bytes(n, lang="en")


# ── binary source-mirror format ─────────────────────────────────
# per the image-system brief: every public image must have a
# plain-text source mirror. svg mirrors are byte-equal text copies
# under /source/<rel>.svg.txt. raster (PNG/JPG/WebP/AVIF/ICO) mirrors
# are base64 under /source/<rel>.base64.txt with a small header so
# the file remains self-describing.

_IMAGE_BINARY_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".avif", ".ico"}
_IMAGE_TEXT_EXTS = {".svg"}

_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".ico": "image/x-icon",
    ".svg": "image/svg+xml",
}


def _image_mirror_dst(src_rel: str, ext: str) -> str:
    """Mirror dest path RELATIVE to /source/.

    Convention:
      /<rel>.svg                → /source/<rel>.svg.txt
      /<rel>.{png,jpg,…,ico}    → /source/<rel>.<ext>.base64.txt
    """
    if ext in _IMAGE_TEXT_EXTS:
        return src_rel + ".txt"
    return src_rel + ".base64.txt"


def _emit_image_mirror(src: pathlib.Path, src_rel: str) -> tuple[bytes, str]:
    """Returns (mirror_bytes, mirror_rel_under_source)."""
    import base64 as _b64

    ext = src.suffix.lower()
    dst_rel = _image_mirror_dst(src_rel, ext)
    data = src.read_bytes()
    sha = sha256_b64(data)
    if ext in _IMAGE_TEXT_EXTS:
        # svg is xml text; mirror verbatim. validate_source_mirrors will
        # do byte-equality against the live file.
        return data, dst_rel
    # Binary: base64-encode with a small header.
    mime = _MIME_BY_EXT.get(ext, "application/octet-stream")
    body = _b64.b64encode(data).decode("ascii")
    # wrap to 76-char lines for readability — base64 standard.
    wrapped = "\n".join(body[i : i + 76] for i in range(0, len(body), 76))
    header = (
        f"# Base64 mirror of:\n"
        f"/{src_rel}\n\n"
        f"# SHA-256:\n"
        f"{sha}\n\n"
        f"# MIME:\n"
        f"{mime}\n\n"
        f"# Size:\n"
        f"{len(data)} bytes\n\n"
    )
    return (header + wrapped + "\n").encode("utf-8"), dst_rel


def _discover_image_mirrors(root: pathlib.Path) -> list[tuple[str, str]]:
    """Return a list of (src_rel, dst_rel) tuples for every image
    under root/images/. dst_rel is the path under SOURCE_DIR.
    Excludes the source/ tree itself (no recursive mirrors).
    """
    out: list[tuple[str, str]] = []
    img_root = root / "images"
    if not img_root.is_dir():
        return out
    for fp in sorted(img_root.rglob("*")):
        if not fp.is_file():
            continue
        ext = fp.suffix.lower()
        if ext not in (_IMAGE_BINARY_EXTS | _IMAGE_TEXT_EXTS):
            continue
        rel = fp.relative_to(root).as_posix()
        out.append((rel, _image_mirror_dst(rel, ext)))
    # also mirror root-level icon compatibility files (favicon,
    # apple-touch-icon, etc.) — they're public bytes too.
    for name in (
        "favicon.ico",
        "favicon.svg",
        "apple-touch-icon.png",
        "icon-192.png",
        "icon-512.png",
    ):
        fp = root / name
        if not fp.is_file():
            continue
        ext = fp.suffix.lower()
        rel = name
        out.append((rel, _image_mirror_dst(rel, ext)))
    return out


def main() -> int:
    SOURCE_DIR.mkdir(exist_ok=True)

    # build-day stamp for the manifest's top-level generated_at field.
    # per-row `modified` no longer uses this — it now reads the canonical
    # file's content-history date from /file-metadata.json so each row
    # reflects when its source content actually changed.
    generated_at_date = datetime.now(UTC).strftime("%Y-%m-%d")

    # load file-metadata.json (written by generate_file_metadata.py at
    # stage [5g]). carries content-history-anchored modified_iso plus
    # canonical byte counts per public path.
    fmd_path = ROOT / "file-metadata.json"
    if fmd_path.is_file():
        fmd = json.loads(fmd_path.read_text(encoding="utf-8"))
        fmd_files = fmd.get("files", {}) if isinstance(fmd, dict) else {}
    else:
        fmd_files = {}

    def _row_modified(live_rel: str) -> str:
        # prefer the canonical file's content-history date; fall back to
        # build-day if the manifest doesn't cover this path (e.g. first
        # run before a content-history entry exists).
        rec = fmd_files.get(live_rel)
        if rec and rec.get("modified_iso"):
            return rec["modified_iso"]
        return generated_at_date

    def _canonical_size(live_rel: str, mirror_bytes: int) -> int:
        # stat the live public file directly; reading file-metadata.json
        # here would give pre-sweep bytes for html pages because the
        # preliminary manifest [5g] runs before the placeholder sweep.
        live = ROOT / live_rel
        if live.is_file():
            return live.stat().st_size
        return mirror_bytes

    manifest_files = []
    written = 0
    missing = []

    for src_path, dst_name in MIRROR:
        sp = ROOT / src_path
        if not sp.is_file():
            missing.append(src_path)
            continue
        # when an authored source is mapped, mirror that instead of the
        # compact production bytes. /source/ is editorial transparency,
        # not a deployment snapshot.
        authored_src = SOURCE_MIRROR_MAP.get(dst_name)
        if authored_src is not None and authored_src.is_file():
            authored = authored_src.read_bytes()
            if dst_name.endswith(".css.txt"):
                data = _AUTHORED_BANNER_CSS + authored
            elif dst_name.endswith(".js.txt"):
                data = _AUTHORED_BANNER_JS + authored
            else:
                data = authored
        else:
            data = sp.read_bytes()
        # the apache config mirror gets a public-transparency banner and
        # per-line redaction of operational filenames; the live .htaccess
        # is unchanged. see _htaccess_mirror_transform().
        if src_path == ".htaccess":
            public_safety_scan(data.decode("utf-8", errors="replace"), src_path)
            data = _htaccess_mirror_transform(data)
        dst = SOURCE_DIR / dst_name
        # the dst path may now contain subdirectories (e.g.
        # privacy/index.html.txt, .well-known/person.json.txt) under the
        # directory-preserving convention. create parents on the fly so
        # the writer can place the mirror without requiring the build to
        # pre-mkdir every nested directory.
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        sha = sha256_b64(data)
        canonical_bytes = _canonical_size(src_path, len(data))
        manifest_files.append(
            {
                "live_path": "/" + src_path,
                "source_path": "/source/" + dst_name,
                "name": dst_name,
                "display_name": display_name(dst_name),
                "kind": kind_from_name(dst_name),
                # `size`/`size_human` describe the canonical public file
                # (what /source/ rows display). mirror_bytes/mirror_size_human
                # describe the .txt mirror itself.
                "size": canonical_bytes,
                "size_human": fmt_size(canonical_bytes),
                "mirror_bytes": len(data),
                "mirror_size_human": fmt_size(len(data)),
                "modified": _row_modified(src_path),
                "sha256": sha,
                "sha256_short": sha[:12],
            }
        )
        written += 1

    # synthesise /source/README.txt — the same orientation note the
    # release archives carry at root, exposed live so a visitor can
    # read it without first downloading the zip. the /htdocs/README.txt
    # at the sftp root is a separate gandi instance documentation
    # file and stays excluded from public output (see EXCLUDE_PATHS in
    # generate_integrity.py). this readme, at /source/README.txt, is
    # the public companion: same orientation, same edition.
    README_NOTE = (
        "This site is static HTML, CSS and vanilla JavaScript.\n"
        "\n"
        "It is designed to be readable, printable, inspectable and\n"
        "available offline after first visit.\n"
        "\n"
        "The public source mirrors are published at /source/.\n"
        "The signed integrity manifest is published at /integrity.json.\n"
        "Release archives are published at /integrity/releases/.\n"
        "\n"
        "No analytics.\n"
        "No cookies.\n"
        "No third-party scripts.\n"
        "\n"
        "Verification\n"
        "------------\n"
        "This release follows a standard public archive verification\n"
        "model.\n"
        "\n"
        "SHA256SUMS lists the SHA-256 hashes for the release archives.\n"
        "SHA256SUMS.sig is the detached PGP signature over SHA256SUMS.\n"
        "\n"
        "The archive files may be checked against SHA256SUMS.\n"
        "The archive files may also be verified directly with their\n"
        "detached .sig files.\n"
        "\n"
        "The live public site manifest is published at /integrity.json.\n"
        "The manifest signature is published at /integrity.json.sig.\n"
        "The public signing key is published at /.well-known/pgp-key.asc.\n"
        "\n"
        "Typography\n"
        "----------\n"
        "The live site uses licensed webfonts. Proprietary font files\n"
        "are not included in this archive. The site remains readable\n"
        "with fallback fonts. To reproduce the exact typography,\n"
        "obtain the appropriate font licences and place the licensed\n"
        "files in /fonts/.\n"
    )
    readme_path = SOURCE_DIR / "README.txt"
    readme_path.write_text(README_NOTE, encoding="utf-8")
    readme_bytes = readme_path.read_bytes()
    readme_sha = sha256_b64(readme_bytes)
    manifest_files.append(
        {
            "live_path": "/source/README.txt",
            "source_path": "/source/README.txt",
            "name": "README.txt",
            "display_name": "README.txt",
            "kind": "text",
            "size": len(readme_bytes),
            "size_human": fmt_size(len(readme_bytes)),
            "mirror_bytes": len(readme_bytes),
            "mirror_size_human": fmt_size(len(readme_bytes)),
            # README.txt is synthesised here and has no separate canonical
            # form; content-history will date it from its own bytes.
            "modified": _row_modified("source/README.txt"),
            "sha256": readme_sha,
            "sha256_short": readme_sha[:12],
        }
    )
    written += 1

    # ── image source mirrors (binary base64 + svg verbatim) ─────
    # every public image gets a plain-text source mirror. tracked in
    # source-manifest.json, intentionally not shown in the rendered
    # /source/ catalogue (would dilute the editorial taxonomy). run
    # before source-manifest.json is dumped so the manifest covers
    # them; run before the catalogue render so `grouped` skips them.
    image_pairs = _discover_image_mirrors(ROOT)
    image_mirror_files = []
    for src_rel, dst_under_source in image_pairs:
        sp = ROOT / src_rel
        if not sp.is_file():
            continue
        mirror_bytes, _ = _emit_image_mirror(sp, src_rel)
        dst = SOURCE_DIR / dst_under_source
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(mirror_bytes)
        live_data = sp.read_bytes()
        live_sha = sha256_b64(live_data)
        image_mirror_files.append(
            {
                "live_path": "/" + src_rel,
                "source_path": "/source/" + dst_under_source,
                "name": dst_under_source,
                "display_name": dst_under_source,
                "kind": "image",
                "size": len(live_data),
                "size_human": fmt_size(len(live_data)),
                "mirror_bytes": len(mirror_bytes),
                "mirror_size_human": fmt_size(len(mirror_bytes)),
                "modified": _row_modified(src_rel),
                "sha256": live_sha,
                "sha256_short": live_sha[:12],
            }
        )
        written += 1

    # render /source/ as a public archival registry, grouped by
    # editorial purpose rather than file type. each entry carries a
    # one-line description in ENTRY_META that explains its role in
    # the public site. files not in ENTRY_META fall back to a
    # kind-based group so the build never silently drops a file.
    # phase 61 · 6 conceptual sections, in reading order. offline /
    # server folded into source-mirrors and machine-readable so the
    # catalogue is grouped strictly by what a file is for, not by
    # what kind it is.
    # the source mirrors index is intentionally curated. this allow
    # list controls public index visibility only. it is not an
    # access-control mechanism and does not remove directly
    # addressable mirrors — the .txt files for every public file
    # remain on disk and resolvable by url where they support
    # verification, recovery, or release integrity. the curated
    # index just narrows the visible directory to the principal
    # public surfaces so the page reads as editorial selection
    # rather than a filesystem dump.
    PUBLISHED_PAGES = "published-pages"
    TRUST_RECORDS = "trust-records"
    SCRIPTS = "scripts"
    METADATA = "metadata"
    GROUP_ORDER = [PUBLISHED_PAGES, TRUST_RECORDS, SCRIPTS, METADATA]
    GROUP_FALLBACK = {
        PUBLISHED_PAGES: "Published pages",
        TRUST_RECORDS: "Trust records",
        SCRIPTS: "Scripts",
        METADATA: "Metadata",
    }
    CURATED_INDEX: dict[str, str] = {
        # published pages — readable mirrors of canonical public pages
        "403.html.txt": PUBLISHED_PAGES,
        "404.html.txt": PUBLISHED_PAGES,
        "500.html.txt": PUBLISHED_PAGES,
        "index.html.txt": PUBLISHED_PAGES,
        "integrity/index.html.txt": PUBLISHED_PAGES,
        "maintenance.html.txt": PUBLISHED_PAGES,
        "privacy/index.html.txt": PUBLISHED_PAGES,
        "security/index.html.txt": PUBLISHED_PAGES,
        "verify/index.html.txt": PUBLISHED_PAGES,
        # trust records — public declarations and identity surfaces
        ".well-known/attribution.txt.txt": TRUST_RECORDS,
        ".well-known/person.json.txt": TRUST_RECORDS,
        ".well-known/publication.json.txt": TRUST_RECORDS,
        ".well-known/security.txt.txt": TRUST_RECORDS,
        ".well-known/webfinger.txt": TRUST_RECORDS,
        "ai-usage.txt.txt": TRUST_RECORDS,
        "assertion.txt.txt": TRUST_RECORDS,
        "humans.txt.txt": TRUST_RECORDS,
        "pgp.txt.txt": TRUST_RECORDS,
        "statement.txt.txt": TRUST_RECORDS,
        # scripts — authored stylesheets and javascript shipped to the
        # browser. css sits here alongside js so the index reads as
        # "what the page executes / styles itself with", one group.
        "theme.js.txt": SCRIPTS,
        "sw-register.js.txt": SCRIPTS,
        "reveal.js.txt": SCRIPTS,
        "overlay.js.txt": SCRIPTS,
        "copy.js.txt": SCRIPTS,
        "edition.js.txt": SCRIPTS,
        "fonts.js.txt": SCRIPTS,
        "verify-modal.js.txt": SCRIPTS,
        "print.css.txt": SCRIPTS,
        "styles.css.txt": SCRIPTS,
        "sw.js.txt": SCRIPTS,
        "verify/verify.js.txt": SCRIPTS,
        # metadata — server config and machine-readable records that
        # describe the site to crawlers, indexers and language models.
        "htaccess.txt": METADATA,
        "attestations.json.txt": METADATA,
        "llms.txt.txt": METADATA,
        "robots.txt.txt": METADATA,
        "site-metadata.json.txt": METADATA,
        "sitemap.xml.txt": METADATA,
    }
    # bilingual edition pages — each /en/ and /fr/ route's readable
    # mirror joins the catalogue's published-pages group, derived from
    # the route map so a new edition never silently drops out of the
    # /source/ catalogue. (this was the cause of the missing /en/ and
    # /fr/ pages: the hand-maintained list above held root-namespace
    # keys only, so every bilingual edition mirror was filtered out.)
    for _rk in _routes.route_keys():
        if _rk in ("source", "source-view"):
            continue  # catalogue + reader shells are not mirrored — see _page_list()
        for _lang in _routes.languages():
            CURATED_INDEX[_routes.route_output(_rk, _lang) + ".txt"] = PUBLISHED_PAGES

    def _key_for(m):
        """Stable lookup key into ENTRY_META.

        Tries m['name'] first (set on MIRROR entries via dst_name),
        then m['display_name'] (set on synthesised entries), then the
        basename of source_path. Returns None when no key can be
        determined — caller falls back to kind-based grouping.
        """
        if m.get("name"):
            return m["name"]
        if m.get("display_name"):
            return m["display_name"]
        sp = m.get("source_path") or ""
        return sp.rsplit("/", 1)[-1] if sp else None

    def _group_for(m):
        """Return the curated section for `m`, or None if the file is
        not part of the public directory index. CURATED_INDEX is the
        single source of truth — the previous heuristic fallback (kind
        + path) is intentionally retired so the index never silently
        expands as new files appear in the mirror."""
        key = _key_for(m)
        if key and key in CURATED_INDEX:
            return CURATED_INDEX[key]
        return None

    grouped = {g: [] for g in GROUP_ORDER}
    for m in manifest_files:
        g = _group_for(m)
        if g is None:
            continue
        grouped[g].append(m)

    # ── editorial registry rendering ────────────────────────────
    # one <section class="source-group"> per editorial group, each
    # containing a <dl class="source-registry"> of <.source-entry>
    # rows. each entry is a micro-grid: filename left, mono meta
    # right (file type abbr, size, validated date, optional short
    # SHA-256). the markup is intentionally semantic — <code> for
    # filenames, <abbr> for file-type tokens, <time> for the
    # validated date, <samp> for the short hash fragment — so the
    # page reads as a public provenance ledger, not a directory
    # dump.

    # mapping from kind code to <abbr> token + tooltip. covers the
    # editorial taxonomy used in the source registry plus the
    # cryptographic verification artefacts (sig / asc).
    KIND_LABELS = {
        "html": ("HTML", "HyperText Markup Language"),
        "css": ("CSS", "Cascading Style Sheets"),
        "js": ("JS", "JavaScript"),
        "json": ("JSON", "JavaScript Object Notation"),
        "xml": ("XML", "Extensible Markup Language"),
        "text": ("TXT", "Plain text"),
        "apache": ("Apache", "Apache HTTP server configuration"),
        "sig": ("PGP", "Detached Pretty Good Privacy signature"),
        "asc": ("PGP", "ASCII-armoured Pretty Good Privacy key"),
        "image": ("Image", "Image asset"),
        "file": ("File", "Plain file"),
    }

    # phase 61 · render the modified date in long human form
    # ("13 may 2026") for the visible text while keeping the
    # iso yyyy-mm-dd in the <time datetime> attribute for
    # machine readability. less system-ui, more archival.
    _MONTHS_LONG = [
        "",
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]

    def _format_date_long(iso: str) -> str:
        try:
            y, m, d = iso.split("-")
            return f"{int(d)} {_MONTHS_LONG[int(m)]} {int(y)}"
        except Exception:
            return iso

    def _meta_html(m):
        kind = m.get("kind", "file")
        label, title = KIND_LABELS.get(kind, (kind.upper(), kind))
        parts = [f'<abbr title="{title}">{label}</abbr>']
        if m.get("size_human") and m["size_human"] != "—":
            parts.append(f'<span class="source-entry-size">{m["size_human"]}</span>')
        # date intentionally omitted from each row to keep the
        # catalogue compact and editorial rather than dashboard-like.
        return ' <span class="source-entry-sep" aria-hidden="true">·</span> '.join(parts)

    def _label_for(m):
        if m.get("display_name"):
            return m.get("display_name", "")
        if m.get("href"):
            return ""
        sp = m["source_path"]
        label = sp[len("/source/") :] if sp.startswith("/source/") else sp
        return label

    def _reader_url(m):
        """Return the /source/view/?path= URL for this entry, or None if
        not applicable. Uses the entry's canonical live route — never the
        raw .txt mirror name — so the address bar never exposes the
        mirror extension. /index.html collapses to /, /privacy/index.html
        to /privacy/, non-HTML live paths pass through unchanged."""
        sp = m.get("source_path", "")
        if not sp.startswith("/source/"):
            return None
        file_key = sp[len("/source/") :]  # e.g. "index.html.txt"
        if not file_key or m.get("href"):  # skip override rows (manifest entry itself)
            return None
        live = m.get("live_path", "")
        if live:
            canon = re.sub(r"/index\.html$", "/", live)
            return "/source/view/?path=" + canon.replace("/", "%2F")
        # legacy fallback for entries without a live_path. should never
        # fire on a clean build — every manifest entry carries one.
        return f"/source/view/?file={file_key}"

    def _entry_for(m, copy=None):
        reader_url = _reader_url(m)
        href = reader_url or m.get("href") or m["source_path"]
        raw_href = m.get("href") or m["source_path"]  # always points to raw .txt
        label = _label_for(m)
        # short sha fragment as a <samp>, only when present and real
        # (verification-row em-dash placeholder skipped). lives in
        # its own row block so the meta line stays single-line.
        sha_block = ""
        if m.get("sha256_short") and m["sha256_short"] != "—":
            sha_block = (
                '\n              <p class="source-entry-hash">'
                '<abbr title="Secure Hash Algorithm, 256-bit">SHA-256</abbr>'
                f' <samp title="{m["sha256"]}">{m["sha256_short"]}</samp>'
                "</p>"
            )
        # editorial description and optional role label. role labels
        # quietly distinguish trust-critical files (signed manifest,
        # public key, canonical identity record, disclosure surface)
        # — text, not badges. when a per-language source.yml is passed
        # (the /en-au/ and /fr/ catalogue splice), the description and
        # role render in that language from source.files.<slug>; the
        # english ENTRY_META is the last-resort fallback and the source
        # for the neutral root /source/ catalogue.
        key = _key_for(m) or ""
        meta = ENTRY_META.get(key, {})
        description = meta.get("description", "")
        role = meta.get("role", "")
        if copy:
            slug_key = i18n_slug(key)
            file_copy = (copy.get("files") or {}).get(slug_key) or {}
            if file_copy.get("description"):
                description = file_copy["description"]
            if file_copy.get("role"):
                role = file_copy["role"]
        critical_attr = ' data-critical="true"' if role else ""
        desc_block = ""
        if description:
            if role:
                desc_block = (
                    '\n            <dd class="source-entry-desc">'
                    f'<span class="source-entry-role">{role}</span> '
                    f'<span class="source-entry-desc-text">{description}</span>'
                    "</dd>"
                )
            else:
                desc_block = f'\n            <dd class="source-entry-desc">{description}</dd>'
        # when a reader url exists, show filename linked to reader + quiet raw link.
        # otherwise fall back to linking directly to the raw .txt.
        if reader_url and raw_href != reader_url:
            name_html = (
                f'<a href="{href}"><code>{label}</code></a>'
                f' <a class="source-entry-raw" href="{raw_href}">Plain text</a>'
            )
        else:
            name_html = f'<a href="{href}"><code>{label}</code></a>'

        return (
            f'          <div class="source-entry"{critical_attr}>\n'
            f'            <dt class="source-entry-name">{name_html}</dt>\n'
            f'            <dd class="source-entry-meta">{_meta_html(m)}{sha_block}</dd>'
            f"{desc_block}\n"
            "          </div>"
        )

    # stage 1: write source-manifest.json (covers public mirrors only,
    # never itself , avoids circular hashing). then stat() and hash the
    # file on disk so the /source/ html row can show real size + SHA-256.
    manifest_path = SOURCE_DIR / "source-manifest.json"
    # generated_at uses the same `validated_date` as every row's
    # `modified` field, so source-manifest.json and the rendered source
    # page agree exactly. two consecutive builds within a day produce
    # byte-identical output; cross-day builds advance the date in step.
    # enrich manifest entries with editorial descriptions so downstream
    # consumers (e.g. generate_source_reader.py) can render them without
    # re-importing ENTRY_META.
    for mf in manifest_files:
        key = _key_for(mf)
        desc = (ENTRY_META.get(key) or {}).get("description", "")
        if desc:
            mf["description"] = desc

    manifest_path.write_text(
        json.dumps(
            {
                "schema": "https://trentpower.fr/source/source-manifest.json",
                "generated_at": generated_at_date + "T00:00:00Z",
                "principle": "This site is designed first for human readers. "
                "The /source/ tree mirrors public files as plain "
                "text so the bytes the live site serves can be "
                "inspected without any tooling.",
                "files": manifest_files,
                # image mirrors are kept in a separate top-level array
                # rather than mixed into `files` so the editorial source
                # catalogue stays terse. Per-entry shape mirrors `files`.
                "images": image_mirror_files,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_bytes = manifest_path.read_bytes()

    # publish source-manifest.json.txt — a byte-equal copy under
    # the .txt mirror convention, so the metadata row can link there
    # like every other JSON/text row (which all link to /source/*.txt).
    # the canonical .json file remains for clients that want
    # application/json semantics.
    manifest_txt_path = SOURCE_DIR / "source-manifest.json.txt"
    manifest_txt_path.write_bytes(manifest_bytes)
    # the .txt mirror of source-manifest.json is still written so its
    # direct url stays resolvable, but the row is intentionally absent
    # from the visible curated index — the manifest is build plumbing,
    # not a principal public surface. CURATED_INDEX is the single
    # source of truth for what appears in the directory listing.
    # no self-mirror under /source/source/. the source page lives at
    # /source/index.html and is its own entry point; visitors who want
    # to read the page bytes can do so via view source (the page is
    # plain html). adding /source/source/index.html.txt would create
    # a recursive layer the brief explicitly forbids. the page is
    # byte-stable per build because its derived counters (group
    # totals, modified date) are computed against a pinned utc date.

    # inject verification rows: signed integrity manifest, detached
    # signature, public signing key. these link directly to the
    # canonical paths (/integrity.json etc.) — not to .txt mirrors —
    # so the live signed file is what readers inspect, no chance of
    # a stale source-side mirror diverging from the signed authority.
    #
    # size + hash columns intentionally show "—" rather than the bytes
    # on disk at render time. Why: integrity.json hashes /source/
    # index.html, and embedding integrity.json's own hash here would
    # create a hashing loop (integrity.json bytes ← source/index.html
    # bytes ← integrity.json hash). pointing to the canonical url
    # keeps the trust file authoritative; the live hash is whatever
    # /integrity.json currently is, signed and verifiable directly.
    # phase 61 · the verification group is no longer rendered on
    # /source/. cryptographic trust (signed authority, detached
    # signature, public signing key, release checksums) lives only
    # on /integrity/ now. page-level provenance lives on /verify/.
    # the source page owns one responsibility — listing what
    # public files exist and why — and closes with a quiet
    # related-records nav.

    # alphabetical sort across every registry group.
    for g in grouped:
        grouped[g].sort(key=lambda m: (m["display_name"], m["source_path"]))

    # ── registry sections ───────────────────────────────────────
    # one <article class="integrity-record-card source-group-card">
    # per editorial group. each carries a short prose gloss so the
    # registry reads as authored commentary rather than an inventory
    # list. the four cards sit as siblings of the edition card above,
    # so /source/ reads as a sibling of /integrity/ — four signed
    # records rather than four flat lists.
    GLOSS_FALLBACK = {
        PUBLISHED_PAGES: "Readable mirrors of the principal public pages, served as plain text so the bytes can be inspected without execution.",
        TRUST_RECORDS: "Public commitments and identity surfaces. Who publishes the site, what is promised, where disclosure runs.",
        SCRIPTS: "Authored stylesheets and JavaScript the page ships to the browser. Mirrored from source, not the minified deployed bytes.",
        METADATA: "Server configuration and machine-readable records describing the site to crawlers, indexers and language models.",
    }
    REGISTRY_GROUPS = list(GROUP_ORDER)

    def _build_registry_html(lang=None):
        """Render the exhaustive registry for one language.

        `lang` is the internal language key ('en'/'fr') or None for the
        neutral root /source/ catalogue. Group headings and glosses come
        from content/<lang>/pages/source.yml (source.group.* /
        source.group_gloss.*) and per-file descriptions from
        source.files.<slug>, falling back to the english GROUP_FALLBACK /
        GLOSS_FALLBACK / ENTRY_META dicts when a key is absent."""
        copy = _source_copy(lang)
        copy_groups = copy.get("group") or {}
        copy_gloss = copy.get("group_gloss") or {}
        sections = []
        for g in REGISTRY_GROUPS:
            if not grouped[g]:
                continue
            count = len(grouped[g])
            # group key in YAML is the same slug used by GROUP_ORDER
            # (published-pages / trust-records / scripts / metadata).
            title = copy_groups.get(g) or GROUP_FALLBACK[g]
            gloss = copy_gloss.get(g) or GLOSS_FALLBACK.get(g, "")
            title_id = f"source-group-{g}"
            entries = "\n".join(_entry_for(m, copy=copy) for m in grouped[g])
            gloss_html = ""
            if gloss:
                # YAML block scalars may carry trailing newlines; collapse
                # internal whitespace so the spliced markup stays tidy.
                gloss_text = " ".join(gloss.split())
                gloss_html = f'        <p class="source-group-gloss">{gloss_text}</p>\n'
            sections.append(
                f'      <article class="integrity-record-card source-group-card" aria-labelledby="{title_id}">\n'
                f'        <header class="source-group-header">\n'
                f'          <h2 class="source-group-title" id="{title_id}">'
                f"<span>{title}</span>"
                f"</h2>\n"
                f'          <p class="source-group-count" aria-label="{count} entries">{count}</p>\n'
                f"        </header>\n"
                f"{gloss_html}"
                f'        <dl class="source-registry">\n'
                f"{entries}\n"
                f"        </dl>\n"
                f"      </article>"
            )
        return "\n".join(sections)

    # the neutral root /source/index.html carries no language tree, so it
    # renders from the english fallback dicts.
    registry_html = _build_registry_html(lang=None)

    # NOTE: a former "edition lineage" panel was removed here — it read
    # grouped.get("pages") against a dict only ever keyed by GROUP_ORDER
    # ("published-pages"/"trust-records"/"scripts"/"metadata"), so it was
    # always empty and rendered nothing. edition lineage lives at
    # /integrity/releases/. the f-string slot below is intentionally blank
    # to keep output bytes identical.

    index_html = f"""<!doctype html>
<!--
  trentpower.fr · public source mirror
  static, self-managed, privacy-first
  plain-text mirrors of public files at /source/*.txt
-->
<html lang="en">
<head>
  <!-- foundations -->
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="color-scheme" content="light">
  <meta name="theme-color" content="#E9E5DC">

  <!-- document -->
  <title>Source mirrors · Trent Power</title>
  <meta name="description" content="Readable public mirrors of selected site files">
  <link rel="canonical" href="https://trentpower.fr/source/">

  <!-- identity -->
  <meta name="author" content="Trent Power">
  <meta name="application-name" content="Trent Power">
  <meta name="apple-mobile-web-app-title" content="Trent Power">
  <link rel="author" href="/.well-known/attribution.txt">
  <link rel="alternate" type="application/ld+json" href="/.well-known/person.json">

  <!-- discovery -->
  <meta name="robots" content="noindex">
  <meta name="referrer" content="no-referrer">

  <!-- social preview -->
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="Trent Power">
  <meta property="og:title" content="Source mirrors · Trent Power">
  <meta property="og:description" content="Readable public mirrors of selected site files">
  <meta property="og:url" content="https://trentpower.fr/source/">
  <meta property="og:image" content="https://trentpower.fr/images/og/source-og.png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:type" content="image/png">
  <meta property="og:image:alt" content="Source mirrors · Trent Power">
  <meta name="twitter:card"        content="summary_large_image">
  <meta name="twitter:title"       content="Source mirrors · Trent Power">
  <meta name="twitter:description" content="Readable public mirrors of selected site files">
  <meta name="twitter:image"       content="https://trentpower.fr/images/og/source-og.png">
  <meta name="twitter:image:alt"   content="Source mirrors · Trent Power">
  <meta name="twitter:site"        content="@trentpower">
  <meta name="twitter:creator"     content="@trentpower">

  <!-- icons and app surface -->
  <link rel="icon" href="/favicon.ico" sizes="any">
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png">
  <link rel="manifest" href="/manifest.webmanifest">

  <!-- assets -->
  <link rel="stylesheet" href="/styles.css?v={_asset_version()}">
  <link rel="stylesheet" href="/print.css?v={_asset_version()}" media="print">

  <!-- structured data -->
  <script type="application/ld+json">{{"@context":"https://schema.org","@type":"TechArticle","@id":"https://trentpower.fr/source/#article","headline":"Source · Trent Power","url":"https://trentpower.fr/source/","description":"Public source mirrors. Plain-text inspection of every active publishable byte.","inLanguage":"en","isPartOf":{{"@id":"https://trentpower.fr/#website"}},"author":{{"@id":"https://trentpower.fr/#trent-power"}},"publisher":{{"@id":"https://trentpower.fr/#trent-power"}},"datePublished":"2026-02-15","dateModified":"{_source_index_datemod()}","primaryImageOfPage":{{"@type":"ImageObject","url":"https://trentpower.fr/images/og/source-og.png","width":1200,"height":630}}}}</script>

</head>
<body data-page="source" data-layout="masthead" data-surface="record" data-masthead="brand-only" class="source-page" data-edition="{_edition()}">

<a href="#main" class="skip-link">Skip to content</a>

<header class="site-header" data-component="site-header">
  <div class="nav">
    <div class="nav-inner">
      <a class="nav-mark" href="/" aria-label="Trent Power home"><span>Trent</span> <span>Power</span></a>
    </div>
  </div>
</header>

<main class="site" id="main" tabindex="-1" itemscope itemtype="https://schema.org/TechArticle">
  <div class="page">
    <p class="page-kicker">Source</p>
    <h1 class="page-title hero-stack"><span class="hero-line">Every public byte,</span><span class="hero-line">in plain text.</span></h1>
    <div class="page-body">
      <p class="page-lede">Selected public files, published in readable form. For inspection, preservation, and machine readability.</p>

      <p class="source-curation-note">This index shows the principal public mirrors. Additional mirrored files may remain available by direct URL where they support verification, recovery, or release integrity.</p>

      <div class="source-registry-wrap">
{registry_html}
      </div>

{""}
    </div>
  </div>

</main>

<!-- body · footer -->
<footer class="site-footer" aria-label="Site footer">
  <div class="site-footer__inner">

    <!-- top stratum · identity · nav · language -->
    <div class="site-footer__top">

      <p class="site-footer__identity">
        <span class="year">&copy; <span class="since">1997 &ndash;</span> <time datetime="2026">2026</time></span>
        <a class="wm" href="/" rel="home" aria-describedby="desc-home-footer"><bdi>Trent Power</bdi></a>
        <span class="visually-hidden" id="desc-home-footer">Return to the homepage</span>
      </p>

      <nav class="site-footer__nav" aria-label="Footer">
        <span>Paris, France</span>
        <span class="sep" aria-hidden="true">&middot;</span>
        <a class="site-footer__action" href="/en-au/privacy/" rel="privacy-policy" aria-describedby="desc-privacy">Privacy</a>
        <span class="visually-hidden" id="desc-privacy">Read how this site avoids analytics, cookies, profiling, tracking, and third-party assets</span>
        <span class="sep" aria-hidden="true">&middot;</span>
        <button type="button" class="site-footer__action"
                data-cite-open aria-haspopup="dialog"
                aria-describedby="desc-cite"
               >Verify</button>
        <span class="visually-hidden" id="desc-cite">Open citation and verification details for this page</span>
      </nav>

      <ul class="site-footer__language" aria-label="Language">
        <li><button type="button" data-lang="en" aria-pressed="true"  aria-describedby="desc-lang-en" lang="en">English</button> <span class="visually-hidden" id="desc-lang-en">Read this site in English</span></li>
        <li aria-hidden="true"><span class="sep">&middot;</span></li>
        <li><button type="button" data-lang="fr" aria-pressed="false" aria-describedby="desc-lang-fr" lang="fr">Français</button> <span class="visually-hidden" id="desc-lang-fr">Lire ce site en français</span></li>
      </ul>

    </div>

    <hr class="site-footer__break" aria-hidden="true">

    <!-- bottom stratum · imprint · theme -->
    <div class="site-footer__bottom">

      <dl class="site-footer__imprint is-loading" id="footerImprint" aria-label="Publication integrity">
        <dt>Edition</dt>
        <dd><span data-proof="edition">&mdash;</span></dd>
        <dt>SHA256</dt>
        <dd><a class="sha-link" href="/en-au/integrity/" aria-describedby="desc-integrity"
               data-proof="sha">sha256:&mdash;</a> <span class="visually-hidden" id="desc-integrity">Open the public integrity record, including hashes, signatures, and release verification</span></dd>
        <dt>Verified</dt>
        <dd><span class="v--fresh" data-proof="verified">&mdash;</span></dd>
      </dl>

      <p class="site-footer__provenance" lang="fr">Machine-translated from the English original.</p>

      <ul class="site-footer__theme" aria-label="Appearance">
        <li><button type="button" data-theme="light"  aria-pressed="false" aria-describedby="desc-theme-light">Light</button> <span class="visually-hidden" id="desc-theme-light">Switch to the light appearance</span></li>
        <li aria-hidden="true"><span class="sep">&middot;</span></li>
        <li><button type="button" data-theme="system" aria-pressed="true"  aria-describedby="desc-theme-auto">Auto</button> <span class="visually-hidden" id="desc-theme-auto" >Match the system appearance setting</span></li>
        <li aria-hidden="true"><span class="sep">&middot;</span></li>
        <li><button type="button" data-theme="dark"   aria-pressed="false" aria-describedby="desc-theme-dark">Dark</button> <span class="visually-hidden" id="desc-theme-dark" >Switch to the dark appearance</span></li>
      </ul>

    </div>

  </div>
</footer>

<!-- scripts · progressive enhancement, no telemetry -->
<script src="/verify/verification-data.js?v={_asset_version()}" defer></script>

<script src="/js/theme.js?v={_asset_version()}" defer></script>

<script src="/sw-register.js?v={_asset_version()}" defer></script>

<script src="/js/reveal.js?v={_asset_version()}" defer></script>

<script src="/js/overlay.js?v={_asset_version()}" defer></script>

<script src="/js/copy.js?v={_asset_version()}" defer></script>

<script src="/js/verify-modal.js?v={_asset_version()}" defer></script>

<script src="/js/fonts.js?v={_asset_version()}" defer></script>

</body>
</html>
"""
    (SOURCE_DIR / "index.html").write_text(index_html, encoding="utf-8")
    written += 2  # source-manifest.json + index.html

    # ── bilingual catalogue parity ──────────────────────────────
    # /en-au/source/ and /fr/source/ are template-rendered editorial pages
    # whose hand-authored registry drifts behind this generated, complete
    # catalogue. splice the exhaustive registry between the markers so
    # all three catalogue pages list the same full set of source files.
    # each edition's registry is rendered in its own language so the
    # spliced group headings, glosses and per-file descriptions match the
    # template-rendered chrome around them. previously a single english
    # registry_html was spliced into both trees, which overwrote the
    # french tokens render_pages.py had already filled — leaving the
    # /fr/source/ catalogue showing english headings and descriptions.
    _RM_BEGIN = "<!-- BEGIN source-registry"
    _RM_END = "<!-- END source-registry -->"
    for _lang in _routes.languages():
        _ed = _routes.route_output("source", _lang)
        _p = SOURCE_DIR.parent / _ed
        if not _p.is_file():
            continue
        _h = _p.read_text(encoding="utf-8")
        _b = _h.find(_RM_BEGIN)
        _e = _h.find(_RM_END)
        if _b == -1 or _e == -1:
            continue
        _lang_registry_html = _build_registry_html(lang=_lang)
        _b = _h.find("-->", _b) + 3  # end of the BEGIN comment
        _new = _h[:_b] + "\n" + _lang_registry_html + "\n      " + _h[_e:]
        if _new != _h:
            _p.write_text(_new, encoding="utf-8")
            written += 1
            print(f"  ✓ spliced exhaustive registry ({_lang}) → {_ed}")

    # ── orphan cleanup ──────────────────────────────────────────
    # the directory-preserving rename leaves the old flat-named
    # mirrors (privacy.html.txt, integrity.html.txt, etc.) on disk.
    # compute the set of files this build should have produced and
    # delete every other file under SOURCE_DIR. idempotent across
    # builds; protects against future renames silently leaving
    # stale mirrors live on the server.
    expected = {
        SOURCE_DIR / "index.html",
        SOURCE_DIR / "source-manifest.json",
        SOURCE_DIR / "source-manifest.json.txt",
        SOURCE_DIR / "README.txt",
    }
    for _, dst_name in MIRROR:
        expected.add(SOURCE_DIR / dst_name)
    for _, dst_under_source in image_pairs:
        expected.add(SOURCE_DIR / dst_under_source)

    removed = 0
    for fp in SOURCE_DIR.rglob("*"):
        if fp.is_dir():
            continue
        if fp in expected:
            continue
        try:
            fp.unlink()
            removed += 1
        except OSError:
            pass
    # prune empty directories left behind.
    for dp in sorted(SOURCE_DIR.rglob("*"), reverse=True):
        if dp.is_dir():
            try:
                dp.rmdir()  # only succeeds when empty
            except OSError:
                pass

    print(f"✓ /source/ generated · {written} files")
    print(f"  manifest entries: {len(manifest_files)}")
    if removed:
        print(f"  cleaned: {removed} orphan mirror(s) removed")
    if missing:
        print(f"  WARN: {len(missing)} allowlisted source(s) not found:", file=sys.stderr)
        for m in missing:
            print(f"    - {m}", file=sys.stderr)

    return 0


def _edition() -> str:
    """Read edition from identity_canonical.json or fall back to today."""
    try:
        canon = json.load(open(IDENTITY_CANONICAL, encoding="utf-8"))
        return canon.get("edition", "")
    except Exception:
        return ""


def _source_index_datemod() -> str:
    """resolve the json-ld dateModified for source/index.html against the
    content-history-anchored manifest. validate_dates.py enforces strict
    equality with file-metadata.json modified_iso; using the manifest
    here keeps the substitution at generation time so the byte count
    stabilises before verification-data.js / sri are computed (a
    {{datemod:...}} placeholder swept later would shift sizes after
    those bytes are pinned)."""
    try:
        manifest_path = ROOT / "file-metadata.json"
        manifest = json.load(open(manifest_path, encoding="utf-8"))
        rec = manifest.get("files", {}).get("source/index.html") or {}
        iso = rec.get("modified_iso")
        if iso:
            return iso
    except Exception:
        pass
    return _edition()


def _asset_version() -> str:
    """Read asset_version from site-metadata.json (written by generate_site.py).
    The value is the canonical CSS/JS cache-bust token; missing here means
    generate_site.py has not run yet, which is a pipeline-order error."""
    try:
        sm = json.load(open("site-metadata.json", encoding="utf-8"))
        return sm.get("asset_version", "")
    except Exception:
        return ""


if __name__ == "__main__":
    sys.exit(main())
