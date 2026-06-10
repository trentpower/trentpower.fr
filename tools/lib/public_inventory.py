"""Single source of truth for the public-asset surface.

Imported by generate_sw.py to build the service-worker PRECACHE list,
and by inline_checks.py (check_sw_precache) to validate that every
precache URL resolves to a real file on disk with a matching
content-type.

Lists are URL paths (server-rooted, leading slash). The on-disk path
is derived by stripping the leading slash; '/' resolves to 'index.html'
and any other path that ends with '/' resolves to '<path>index.html'.
"""

# ─── pages ──────────────────────────────────────────────────────
# the bilingual public surface, derived from the route map. / is the
# language gate; every route key resolves to an /en/ and /fr/ page;
# error pages are per-tree flat files plus the root-level gate-path
# fallback. /maintenance.html is precached so the offline cache can
# serve it directly when an operator drops the site to maintenance.
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


def _public_pages() -> list:
    pages = ["/"]
    for key in _routes.route_keys():
        for lang in _routes.languages():
            pages.append(_routes.route_path(key, lang))
    for lang in _routes.languages():
        for err in ("403", "404", "500", "maintenance"):
            pages.append(f"/{_routes.lang_url_segment(lang)}/{err}.html")
    pages += [
        "/403.html",
        "/404.html",
        "/500.html",
        "/maintenance.html",
        # /local/ — single-edition english diagnostic surface;
        # replaces the legacy /sw-reset/ page (which now 301s to
        # /local/ via .htaccess). always precached so a reader
        # can reach the device console offline.
        "/local/",
    ]
    return pages


PUBLIC_PAGES = _public_pages()

# ─── stylesheets ────────────────────────────────────────────────
# screen + print. print stylesheet is shared by every trust-page
# print sheet so it must be offline-available.
PUBLIC_STYLES = [
    "/styles.css",
    "/print.css",
    # /fonts-full.css is loaded after lcp by /app-enhance.js. precaching
    # it keeps offline navigations consistent with the live (post-swap)
    # typography state. it is not on the critical chain.
    "/fonts-full.css",
]

# ─── scripts ────────────────────────────────────────────────────
# first-party behaviour scripts are served from /js/; sw-register.js
# stays at the web root next to sw.js. verify.js + verification-data.js
# are loaded only on /verify/ but are precached so that page works
# offline like the rest of the trust system.
PUBLIC_SCRIPTS = [
    "/js/theme.js",
    "/sw-register.js",
    "/js/reveal.js",
    "/js/verify-modal.js",
    "/js/copy.js",
    "/js/edition.js",
    "/js/fonts.js",
    "/js/overlay.js",
    "/js/micro-interactions.js",
    # /local/ device console diagnostics. progressive enhancement —
    # the page renders without it; with it, the six cards populate
    # locally and the reset/copy/export actions work.
    "/js/local.js",
    "/verify/verify.js",
    "/verify/verification-data.js",
]

# ─── fonts ──────────────────────────────────────────────────────
PUBLIC_FONTS = [
    # critical subsets (small, first-paint). precached.
    "/fonts/subsets/signifier-light-hero.woff2",
    "/fonts/subsets/soehne-kraftig-nav.woff2",
    "/fonts/subsets/soehne-mono-buch-labels.woff2",
    # full editorial weights (deeper content + below-fold). optional cache.
    "/fonts/signifier-light.woff2",
    "/fonts/signifier-light-italic.woff2",
    "/fonts/signifier-regular.woff2",
    "/fonts/signifier-regular-italic.woff2",
    "/fonts/soehne-buch.woff2",
    "/fonts/soehne-kraftig.woff2",
    "/fonts/soehne-mono-buch.woff2",
    "/fonts/soehne-mono-kraftig.woff2",
]

# ─── icons + manifest ───────────────────────────────────────────
PUBLIC_ICONS = [
    "/favicon.svg",
    "/favicon.ico",
    "/apple-touch-icon.png",
    "/icon-192.png",
    "/icon-512.png",
    "/manifest.webmanifest",
]

# ─── diagrams + qr codes ────────────────────────────────────────
# English-default architecture diagram + the qr codes used by the
# print sheets. localised /images/architecture/architecture.{lang}.svg
# variants are fetched on demand by app.js when the language changes;
# intentionally kept out of precache to keep it lean.
PUBLIC_DIAGRAMS = [
    "/images/architecture/architecture.svg",
    "/images/architecture/architecture-mobile.svg",
    "/images/qr/print-qr-trentpower.svg",
    "/images/qr/qr-home.svg",
    "/images/qr/qr-privacy.svg",
    "/images/qr/qr-integrity.svg",
    "/images/qr/qr-security.svg",
    "/images/qr/qr-source.svg",
    "/images/qr/qr-verify.svg",
    "/images/qr/qr-releases.svg",
    "/images/qr/qr-acknowledgments.svg",
    "/images/qr/qr-release-2026-05-09.svg",
    "/images/qr/qr-verify-locally.svg",
    "/images/qr/qr-sw-reset.svg",
    "/images/qr/qr-maintenance.svg",
]

# ─── Network-only ───────────────────────────────────────────────
# trust files whose freshness matters more than offline availability.
# a stale signed manifest on offline reload would mislead, so these
# stay network-only by design. the /integrity/ page still reads
# correctly offline because the page itself + its fonts + its css
# are precached; only the live trust-file fetches require network.
#
# /local/ is also network-only by design: the device console must
# never be served from a possibly-stale local cache. if the sw is
# misbehaving, a cached /local/ that no longer matches the live
# diagnostics code would defeat the recovery. always fetch fresh.
NETWORK_ONLY = [
    "/integrity.json",
    "/integrity.json.sig",
    "/site-metadata.json",
    "/llms.txt",
    "/local/",
    "/local/index.html",
]
NETWORK_ONLY_PREFIXES = [
    "/.well-known/",
]


def all_precache_paths():
    """Concatenated list of every URL the SW should precache, in
    deterministic order so the precache_hash is stable across builds.
    Includes both critical and optional sets so the predeploy gate
    sees the full surface."""
    return critical_precache_paths() + optional_precache_paths()


def critical_precache_paths():
    """URLs whose absence would break offline-after-first-visit for
    the active page. Failure to cache any of these aborts the
    service-worker install — the SW must serve a coherent offline
    experience or none at all.

    Includes: every active page (HTML), the three core stylesheets,
    the four core scripts, and the manifest.webmanifest. Icons that
    affect first-paint (favicon.svg) live here too.
    """
    return (
        list(PUBLIC_PAGES)
        + list(PUBLIC_STYLES)
        + list(PUBLIC_SCRIPTS)
        + ["/manifest.webmanifest", "/favicon.svg"]
    )


def optional_precache_paths():
    """URLs nice-to-have offline but whose absence does not break the
    page. Failure to cache any of these is logged but does not abort
    install — the SW gracefully degrades.

    Includes: self-hosted fonts (page renders with the CSS fallback
    stack if missing), platform icons (apple-touch-icon, icon-192,
    icon-512 — first-paint independent), architecture diagrams and
    QR codes (only used on specific pages).
    """
    optional_icons = [u for u in PUBLIC_ICONS if u not in {"/manifest.webmanifest", "/favicon.svg"}]
    return list(PUBLIC_FONTS) + optional_icons + list(PUBLIC_DIAGRAMS)


def url_to_disk_path(url: str) -> str:
    """Map a public URL to its local disk path, public/-relative.

    /                        → index.html
    /privacy/                → privacy/index.html
    /404.html                → 404.html
    /styles.css              → styles.css
    /verify/verify.js        → verify/verify.js
    """
    if not url.startswith("/"):
        raise ValueError(f"public-inventory paths must start with '/': {url!r}")
    if url == "/":
        return "index.html"
    rel = url.lstrip("/")
    if url.endswith("/"):
        return rel + "index.html"
    return rel
