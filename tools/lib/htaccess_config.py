"""htaccess_config.py — single source of truth for .htaccess CSP + headers.

Anything emitted into the BEGIN/END marker blocks of public/.htaccess
is defined here. Hand-edit this file; never hand-edit the marker blocks.

Consumed by:
  - tools/generate_htaccess.py  (renders the marker blocks)
  - tools/generate_site.py      (legacy CSP-hash sweep; deferred to the
                                 generator going forward)
"""

from __future__ import annotations

import re as _re
import sys as _sys

_sys.path.insert(
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
import routes as _routes  # noqa: E402


def _bilingual_route_allow_rules() -> list:
    """Allow patterns for every public page: both language editions of
    each route (directory url + index.html subrequest), derived from
    the route map, plus the language-neutral surfaces — the gate, the
    service-worker recovery page, and the source-reader app."""
    rules: list[str] = []
    for key in _routes.route_keys():
        for lang in _routes.languages():
            slug = _routes.route_path(key, lang).strip("/")
            esc = _re.escape(slug)
            rules.append(rf"^{esc}/?$")
            rules.append(rf"^{esc}/index\.html$")
    # per-language-tree error documents.
    for lang in _routes.languages():
        seg = _re.escape(_routes.lang_url_segment(lang))
        rules.append(rf"^{seg}/(403|404|500|maintenance)\.html$")
    # language-neutral pages — not route-map entries.
    rules += [
        # /local/ replaces /sw-reset/ as the device console; the old
        # path 301-redirects (see _RENAME_REDIRECT_RULES) and is no
        # longer served, so its allow patterns are removed.
        r"^local/?$",
        r"^local/index\.html$",
        r"^source/?$",
        r"^source/index\.html$",
        r"^source/view/?$",
        r"^source/view/index\.html$",
    ]
    return rules


# the source-reader catalogue (/source/) and reader app (/source/view/)
# are language-neutral and still served, so they are NOT legacy
# redirects even though routes.yml lists them; every other single-tree
# path is dead and 301s to its australian english edition.
_LEGACY_REDIRECT_KEEP_LIVE = {"/source/", "/source/view/"}


def _legacy_redirect_rules() -> list:
    """(match-pattern, target) pairs: pre-cut-over single-tree URLs that
    301 to their /en-au/ edition. Query strings pass through mod_rewrite
    untouched, so /verify/?path=… reaches /en-au/verify/?path=…."""
    out = []
    for old, new in _routes.legacy_redirects().items():
        if old in _LEGACY_REDIRECT_KEEP_LIVE:
            continue
        out.append(("^" + _re.escape(old.strip("/")) + "/?$", new))
    return out


def _legacy_lang_redirect_rules() -> list:
    """The /en/ → /en-au/ cut-over family. Two rules: the bare /en/
    redirect and the catch-all /en/(.*) redirect. The catch-all uses
    Apache backreference syntax ($1) so the captured path is preserved
    on the target side. Query strings pass through untouched."""
    seg = _routes.lang_url_segment("en")
    return [
        (r"^en/?$", f"/{seg}/"),
        (r"^en/(.*)$", f"/{seg}/$1"),
    ]


# /en/ → /en-au/ rules first so the cut-over is unambiguous; the
# single-tree → /en-au/ rules follow. /sw-reset/ → /local/ is a
# rename: the recovery page was repositioned as the local device
# console and lives at /local/ now. one-cycle 301 keeps old links
# (qr codes, citations, print sheets that ship the old URL) live.
_RENAME_REDIRECT_RULES: list = [
    (r"^sw-reset/?$", "/local/"),
    (r"^sw-reset/index\.html$", "/local/"),
]

LEGACY_REDIRECT_RULES: list = (
    _legacy_lang_redirect_rules() + _legacy_redirect_rules() + _RENAME_REDIRECT_RULES
)


# (match-pattern, target) pairs: legacy dated/hashed asset URLs 301 to
# their clean equivalents so any browser still holding HTML that
# references the old shapes resolves to the live file. one-cycle
# transition — remove after the 2026-NN-NN edition once HTML caches
# (≤24h on this host) have turned over.
LEGACY_VERSIONED_ASSET_REDIRECTS: list = [
    (r"^fonts-full\.[0-9]{4}-[0-9]{2}-[0-9]{2}\.[a-f0-9]+\.css$", "/fonts-full.css"),
    (
        r"^verify/verification-data\.[0-9]{4}-[0-9]{2}-[0-9]{2}\.[a-f0-9]+\.js$",
        "/verify/verification-data.js",
    ),
]


# ─── CSP HASHES ─────────────────────────────────────────────────
# hashes for inline <script> blocks we own. each entry is the
# sha256 of the script body, base64-encoded, with a 'sha256-' prefix.
#
# adding a new inline script:
#   1. place its body in the page template.
#   2. compute the hash:   bash tools/csp-hashes.sh
#   3. append the hash + a one-line label below.
#
# keep labels short; the *purpose* belongs here, the script body
# belongs in the template that ships it.

CSP_INLINE_HASHES_GLOBAL: list[tuple[str, str]] = [
    (
        "sha256-c4FkQHDOYdbxIMhLU8ATf6N5ghZraFmwUYOjEUMXkDY=",
        "js-class + theme bootstrap (trust + error pages: integrity, "
        "source, security, privacy, verify, 403, 404, 500, maintenance, local)",
    ),
    (
        "sha256-TWclPSpMaTbxEIfz4cRPUMbot1Tylbx2f0lYsawkYGA=",
        "home.html bootstrap (gate v2): js-class + tp-lang→tp-last-edition "
        "migration + theme + hero-static handoff + pageshow.persisted "
        "hero-static suppression + 2.5s fonts-ready safety setTimeout",
    ),
    (
        "sha256-4Fu481C+/mktGJCLdyqpMJqsnB02PRsuEq13yW+YFAk=",
        "language-vestibule bootstrap (gate v2 + welcome-back): tp-lang→"
        "tp-last-edition migration + data-preferred-lang + bcp47 html.lang "
        "+ data-returning + tp-show-gate restoration flag + theme + "
        "bucketed welcome-back (tp-last-read:/edition/ → data-welcome + "
        "window.__tpWelcome.{en,fr} + per-day session sentinel)",
    ),
    (
        "sha256-B71zc5uRStNPKnOmm7V/kIo7tUlvec45PMq0oNlfXQc=",
        "source-reader inline bootstrap (js-class + nav-detected lang + theme)",
    ),
    # historical sha256-EhOgYT… was the /sw-reset/ inline reset
    # script; it was removed when /sw-reset/ became /local/ (the
    # diagnostics now live in /js/local.js, loaded as a deferred
    # module with SRI, so no inline hash is needed for the new page).
]

# the source reader carries one additional inline script (the reader
# bootstrap). the global CSP must not authorise it, so it lives in a
# separate list applied only to the /source/view/ CSP override.
CSP_INLINE_HASHES_SOURCE_VIEW_DELTA: list[tuple[str, str]] = [
    ("sha256-ong18574DRSzuyO+zjuDNWecbI/I+ojY9Bvoi6zBtvw=", "source reader inline bootstrap"),
]

# phase 96 · empty <style id="sv-dyn"> element ships on /source/view/
# so source-view.template.js can mutate its cssom (insertRule) for
# the floating selection toolbar's --st-top / --st-left positioning
# without setting inline element.style.* (which would violate
# style-src-attr 'none'). the empty string's sha256 hash is well
# known and stable; cssom mutations don't change the element's
# textContent, so the hash continues to match across runtime
# updates. only applied to the /source/view/ CSP override.
CSP_INLINE_STYLE_HASHES_SOURCE_VIEW_DELTA: list[tuple[str, str]] = [
    (
        "sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=",
        "empty <style id=sv-dyn> for cssom-mutated toolbar positioning",
    ),
]

# Source-view also widens trusted-types so the reader can register
# tp-source-view alongside tp-app. no other delta.
TRUSTED_TYPES_GLOBAL = ["tp-app"]
TRUSTED_TYPES_SOURCE_VIEW = ["tp-app", "tp-source-view"]


# ─── CSP DIRECTIVE TEMPLATE ─────────────────────────────────────
# one template; the two rendered headers differ only in script-src
# hashes and the trusted-types list. if the structure ever needs to
# change (e.g. a new directive), edit it here and the source-view
# variant inherits.
#
# the order below matches the wire format we have been shipping; do
# not reorder without a reason.

_CSP_TEMPLATE = (
    "default-src 'none'; "
    "upgrade-insecure-requests; "
    "script-src {script_src}; "
    "script-src-attr 'none'; "
    "style-src {style_src}; "
    "style-src-attr 'none'; "
    "font-src 'self'; "
    "img-src 'self'; "
    "manifest-src 'self'; "
    "worker-src 'self'; "
    "connect-src 'self'; "
    "frame-src 'none'; "
    "child-src 'none'; "
    "frame-ancestors 'none'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'none'; "
    # nu html checker flags require-trusted-types-for + trusted-types
    # as unrecognised directives. modern chromium / firefox / safari
    # accept them; sw-register.template.js consumes the tp-app policy
    # and source-view.template.js consumes tp-source-view. do not
    # remove to satisfy the validator — the policies are real.
    "require-trusted-types-for 'script'; "
    "trusted-types {trusted_types}"
)

# the service worker has its own CSP — strict but with worker-script
# semantics. defined explicitly so future drift is visible.
_CSP_SW_TEMPLATE = (
    "default-src 'none'; script-src 'self'; connect-src 'self'; form-action 'none'; base-uri 'none'"
)


def _render(
    template: str,
    script_hashes: list[tuple[str, str]],
    style_hashes: list[tuple[str, str]],
    trusted_types: list[str],
) -> str:
    script_src = "'self'" + "".join(f" '{h}'" for h, _ in script_hashes)
    style_src = "'self'" + "".join(f" '{h}'" for h, _ in style_hashes)
    tt = " ".join(trusted_types)
    return template.format(
        script_src=script_src,
        style_src=style_src,
        trusted_types=tt,
    )


def csp_global() -> str:
    return _render(
        _CSP_TEMPLATE,
        CSP_INLINE_HASHES_GLOBAL,
        [],  # no inline-style hashes globally
        TRUSTED_TYPES_GLOBAL,
    )


def csp_source_view() -> str:
    combined_scripts = CSP_INLINE_HASHES_GLOBAL + CSP_INLINE_HASHES_SOURCE_VIEW_DELTA
    return _render(
        _CSP_TEMPLATE,
        combined_scripts,
        CSP_INLINE_STYLE_HASHES_SOURCE_VIEW_DELTA,
        TRUSTED_TYPES_SOURCE_VIEW,
    )


def csp_service_worker() -> str:
    return _CSP_SW_TEMPLATE


# ─── DENY / ALLOW PHASES ────────────────────────────────────────
# Hard-deny rule families emitted into the BEGIN/END PUBLIC EXPOSURE
# block. each entry is the literal mod_rewrite pattern after the
# leading "RewriteRule " token. flags are always [f,l].
#
# phase 1: dangerous paths (dotfiles, secrets, lockfiles)
# phase 2: dangerous extensions (executable, config, source)
# phase 3: build / source directories
#
# order across phases matters; order *within* a phase is documentation.

DENY_PATH_RULES = [
    r"(^|/)\.git(/|$)",
    r"(^|/)\.github(/|$)",
    r"(^|/)\.vscode(/|$)",
    r"(^|/)\.idea(/|$)",
    r"(^|/)\.env(\.|$)",
    r"(^|/)\.user\.ini$",
    r"(^|/)\.htpasswd$",
    r"(^|/)\.DS_Store$",
    r"(^|/)id_ed25519(\.pub)?$",
    r"(^|/)identity_canonical\.json$",
    r"(^|/)composer\.(json|lock)$",
    r"(^|/)package(-lock)?\.json$",
    r"(^|/)(yarn\.lock|pnpm-lock\.yaml)$",
]

DENY_EXTENSION_RULES = [
    r"\.(php|phar|phtml|asp|aspx|jsp|cgi|pl|py|pyc|pyo|sh|bash|zsh|exe|dll|so)$",
    r"\.(env|ini|conf|config|yaml|yml|toml|lock|bak|backup|old|orig|tmp|swp)$",
    r"\.(sql|sqlite|sqlite3|db|db3|log|map|psd|ai|fig|sketch|md)$",
    r"\.template\.js$",
    r"(?i)(invoice|credential|password|secret|totp_key)|-key\.txt$",
]

DENY_DIRECTORY_RULES = [
    r"^(node_modules|vendor|private|src|tools|templates|partials|scripts|docs)(/|$)",
    r"^(_archives|_licences|_rollback|_audit|console_data|reports|assets-source)(/|$)",
]


# ─── ALLOW-LIST FORWARD-LOOK EXCEPTIONS ─────────────────────────
# allow patterns expected to match zero files at some moments but
# intentionally kept. key is the literal pattern string (must equal
# the entry in ALLOW_RULE_FAMILIES below). value is a one-line reason
# string surfaced by the dead-rule audit. add an entry only when you
# can articulate why the pattern is load-bearing despite matching
# nothing on disk.
ALLOW_RULE_FORWARD_LOOK: dict[str, str] = {
    r"^integrity/releases/2026-02/assets/[A-Za-z0-9._/-]+\.(css|js|svg|woff2|png|jpe?g|webp|ico)$": "frozen-edition shape; may be partially pruned",
}


# ─── ALLOW-LIST FAMILIES ────────────────────────────────────────
# each family is (heading, [pattern, ...]). patterns are emitted as
# RewriteRule <pattern> - [l]. order across families must not change
# without re-running validate_htaccess_allowlist.py — the simulator
# evaluates rules in source order, so an earlier deny would short-
# circuit an allow added later.

ALLOW_RULE_FAMILIES: list[tuple[str, list[str]]] = [
    (
        "root + error pages",
        [
            r"^$",
            r"^index\.html$",
            r"^(403|404|500|maintenance)\.html$",
        ],
    ),
    (
        "public routes (bilingual /en/ + /fr/ trees, neutral surfaces)",
        _bilingual_route_allow_rules(),
    ),
    (
        "public root text files",
        [
            r"^(robots|humans|llms|ai-usage|pgp|assertion|statement|changelog)\.txt$",
        ],
    ),
    (
        "public root json + signed manifests",
        [
            r"^(integrity|site-metadata|attestations|file-metadata|sw-cache-manifest)\.json$",
            r"^integrity\.json\.sig$",
            r"^SHA256SUMS(\.sig)?$",
            r"^sitemap\.xml(\.sha256)?$",
            r"^manifest\.webmanifest$",
        ],
    ),
    (
        "public root css + service worker js",
        [
            # fonts-full ships only as the clean alias; cache-busting is the
            # `?v=…` query stamped onto the HTML reference. legacy dated
            # filenames are 301-redirected by the transitional block above.
            r"^(styles|print|fonts-full)\.css$",
            r"^(sw|sw-register)\.js$",
        ],
    ),
    (
        "first-party behaviour js (served from /js/)",
        [
            r"^js/(copy|edition|fonts|language-gate|local|micro-interactions|overlay|reveal|theme|verify-modal)\.js$",
        ],
    ),
    (
        "root icons",
        [
            r"^(favicon\.svg|favicon\.ico|apple-touch-icon\.png|icon-(192|512)\.png)$",
        ],
    ),
    (
        ".well-known (strictly enumerated)",
        [
            r"^\.well-known/(security\.txt|person\.json|webfinger|pgp-key\.asc|attribution\.(sig|txt)|build\.json|publication\.json)$",
        ],
    ),
    (
        "fonts (root + critical-path subsets)",
        [
            r"^fonts/(subsets/)?[a-z0-9-]+\.woff2$",
        ],
    ),
    (
        "images (architecture, icons, og, portraits, qr, textures)",
        [
            r"^images/architecture/[a-z0-9.-]+\.svg$",
            r"^images/icons/[a-z0-9.-]+\.(png|svg|ico)$",
            r"^images/og/[a-z0-9.-]+\.png$",
            r"^images/portraits/[a-z0-9.-]+\.jpg$",
            r"^images/qr/[a-z0-9.-]+\.svg$",
            r"^images/textures/[a-z0-9.-]+\.svg$",
        ],
    ),
    (
        "source mirror (*.txt + manifest + reader scripts)",
        [
            r"^source/index\.html$",
            r"^source/source-manifest\.json$",
            r"^source/view/(source-view|source-view-manifest)\.js$",
            # bounded-depth segments — no slashes inside the segment class so
            # the rule can't be coerced into matching a stray .txt at an
            # arbitrary depth. four intermediate segments cover the deepest
            # mirror today (source/integrity/releases/YYYY-MM-DD/file.txt.txt).
            r"^source/([A-Za-z0-9._-]+/){0,4}[A-Za-z0-9._-]+\.txt$",
        ],
    ),
    (
        "editorial deliverables (docx + html + pdf; .md is denied)",
        [
            # system b (editorial_copy.json + editorial-copy-review.*) retired;
            # only the copywriter-facing copy-review.* remains.
            r"^editorial/copy-review\.(html|docx|pdf)$",
        ],
    ),
    (
        "public documentation surface (landing + signed pdf + plaintext readme)",
        [
            # neutral surface like /tests/ and /source/. the markdown ships as
            # README.txt because .md is denied site-wide (deny phase 2); the
            # signed README.pdf and the landing page are served here.
            r"^documentation/?$",
            r"^documentation/index\.html$",
            r"^documentation/README\.pdf$",
            r"^documentation/README\.txt$",
        ],
    ),
    (
        "verify (clean filenames only; `?v=…` carries the edition)",
        [
            r"^verify/verify\.js$",
            # verification-data ships only as the clean alias; cache-busting is
            # the `?v=…` query stamped onto the HTML reference. legacy dated
            # filenames are 301-redirected by the transitional block above.
            r"^verify/verification-data\.js$",
        ],
    ),
    (
        "integrity releases (signed archives + checksums)",
        [
            r"^integrity/releases/archive\.css$",
            # machine-readable archive-storage policy pointer (server-canonical)
            r"^integrity/releases/index\.json$",
            r"^integrity/releases/[0-9]{4}-[0-9]{2}(-[0-9]{2})?/?$",
            r"^integrity/releases/[0-9]{4}-[0-9]{2}(-[0-9]{2})?/index\.html$",
            r"^integrity/releases/[0-9]{4}-[0-9]{2}(-[0-9]{2})?/SHA256SUMS(\.sig)?$",
            r"^integrity/releases/[0-9]{4}-[0-9]{2}(-[0-9]{2})?/trentpower-fr-[0-9-]+\.zip(\.(sha256|sig))?$",
            r"^integrity/releases/[0-9]{4}-[0-9]{2}(-[0-9]{2})?/trentpower-fr-[0-9-]+\.tar\.gz(\.(sha256|sig))?$",
            r"^integrity/releases/[0-9]{4}-[0-9]{2}(-[0-9]{2})?/integrity-redistributable(-[0-9]{4}-[0-9]{2}-[0-9]{2})?\.json(\.sig)?$",
            r"^integrity/releases/[0-9]{4}-[0-9]{2}(-[0-9]{2})?/EXCLUDED_FILES(-[0-9]{4}-[0-9]{2}-[0-9]{2})?\.json(\.sig)?$",
            r"^integrity/releases/[0-9]{4}-[0-9]{2}(-[0-9]{2})?/EXCLUDED_FILES(-[0-9]{4}-[0-9]{2}-[0-9]{2})?\.txt$",
            r"^integrity/releases/[0-9]{4}-[0-9]{2}(-[0-9]{2})?/release(-[0-9]{4}-[0-9]{2}-[0-9]{2})?\.json(\.sig)?$",
            r"^integrity/releases/[0-9]{4}-[0-9]{2}(-[0-9]{2})?/builds\.json(\.sig)?$",
            r"^integrity/releases/[0-9]{4}-[0-9]{2}(-[0-9]{2})?/TESTRESULTS\.txt(\.sig)?$",
            # legacy 2026-02 release shape: own integrity.json + assets/ tree
            r"^integrity/releases/2026-02/integrity\.json(\.sig)?$",
            r"^integrity/releases/2026-02/assets/[A-Za-z0-9._/-]+\.(css|js|svg|woff2|png|jpe?g|webp|ico)$",
        ],
    ),
    (
        "provenance (C2PA-signed distribution copies + machine index)",
        [
            r"^provenance/[a-z0-9.-]+\.svg$",
            r"^provenance/index\.json$",
        ],
    ),
    (
        "tests (language-neutral results page)",
        [
            r"^tests/?$",
            r"^tests/index\.html$",
        ],
    ),
]


# ─── PRIVATE DENYLIST (defense-in-depth, header context) ────────
# these FilesMatch / files blocks run after mod_rewrite. they are a
# belt for accidental uploads that the rewrite gate's basename
# patterns could miss.

PRIVATE_DOTFILE_GLOB = r"^\."
PRIVATE_OPS_EXTENSIONS = (
    r"\.(md|py|sh|bak|old|orig|tmp|log|sql|sqlite|db|env|ini|ya?ml|map|psd|ai|fig|sketch)$"
)
PRIVATE_BASENAMES = r"^(\.user\.ini|\.env(\.|$)|\.htpasswd|composer\.(json|lock)|package(-lock)?\.json|yarn\.lock|pnpm-lock\.yaml)$"
PRIVATE_NAME_PATTERNS = r"(?i)(invoice|licen[cs]e|order|credential|password|secret)"


# ─── COMPRESSION MIME-TYPE LIST ─────────────────────────────────
COMPRESS_MIME_TYPES = " ".join(
    [
        "text/html",
        "text/css",
        "text/javascript",
        "application/javascript",
        "application/json",
        "application/ld+json",
        "application/jrd+json",
        "application/manifest+json",
        "image/svg+xml",
        "text/xml",
        "application/xml",
        "text/plain",
    ]
)
