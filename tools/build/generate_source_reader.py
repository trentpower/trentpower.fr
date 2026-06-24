#!/usr/bin/env python3
"""
trentpower.fr
Generate /source/view/ — the dynamic source code reader.

Inputs:
- /source/source-manifest.json  (produced by generate_source_view.py)
- templates/source-view.template.js
- identity_canonical.json

Outputs:
- /source/view/source-view-manifest.js  (metadata map, no file content)
- /source/view/source-view.js           (renderer, from template)
- /source/view/index.html               (shell page with SRI hashes)

Constraints:
- Content fetched at runtime via fetch() from /source/*.txt.
  /source/view/ has a path-scoped CSP with connect-src 'self'.
- No file content is bundled at build time.
- SRI hashes are computed here and baked into the shell page.
- Run after generate_source_view.py (needs source-manifest.json).
"""

import base64
import json
import os
import pathlib
import re
import sys

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
from hashing import sri_sha384  # noqa: E402
from paths import (
    IDENTITY_CANONICAL as CANONICAL,
)
from paths import (
    PUBLIC_DIR as ROOT,
)
from paths import (
    TEMPLATES_DIR as TEMPLATES,
)
from slugs import i18n_slug  # noqa: E402

os.chdir(ROOT)

MANIFEST_IN = pathlib.Path("source/source-manifest.json")
INTEGRITY_IN = pathlib.Path("integrity.json")
VIEW_DIR = pathlib.Path("source/view")
MANIFEST_OUT = VIEW_DIR / "source-view-manifest.js"
RENDERER_OUT = VIEW_DIR / "source-view.js"
SHELL_OUT = VIEW_DIR / "index.html"
TEMPLATE_JS = TEMPLATES / "source-view.template.js"

# files that don't warrant a reader (binary-sourced or image).
SKIP_KINDS = {"binary"}


def compute_sri(path: pathlib.Path) -> str:
    return sri_sha384(path.read_bytes())


def load_canonical() -> dict:
    try:
        return json.loads(CANONICAL.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_integrity_hashes() -> dict:
    """Return the integrity.json files dict (path → 'sha256-<b64>'), or empty.
    Used to thread the canonical SHA-256 into each source-view-manifest entry
    so the reader's integrity block reads as a verifiable archival artefact,
    not a label."""
    if not INTEGRITY_IN.exists():
        return {}
    try:
        doc = json.loads(INTEGRITY_IN.read_text(encoding="utf-8"))
    except Exception:
        return {}
    files = doc.get("files")
    return files if isinstance(files, dict) else {}


def b64_sha256_to_hex_short(value: str) -> str:
    """Convert 'sha256-<b64>' to a 12-character hex prefix. Returns '' on
    any failure so the reader simply omits the SHA-256 row rather than
    rendering a malformed value."""
    if not value or not value.startswith("sha256-"):
        return ""
    try:
        raw = base64.b64decode(value[len("sha256-") :])
    except Exception:
        return ""
    return raw.hex()[:12]


_MONTHS = (
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
)


def edition_to_signed_release(edition: str) -> str:
    """'2026-05-09' → 'May 2026'. Returns '' for malformed input."""
    m = re.match(r"^(\d{4})-(\d{2})-\d{2}$", edition or "")
    if not m:
        return ""
    year = int(m.group(1))
    month = int(m.group(2))
    if not (1 <= month <= 12):
        return ""
    return f"{_MONTHS[month - 1]} {year}"


def build_manifest_data(manifest_files: list, edition: str, integrity_hashes: dict) -> dict:
    """Build the metadata map shipped to the browser as source-view-manifest.js."""
    signed_release = edition_to_signed_release(edition)
    data = {}
    for f in manifest_files:
        kind = f.get("kind", "text")
        if kind in SKIP_KINDS:
            continue

        name = f.get("name", "")
        if not name:
            continue

        live_path = f.get("live_path", "")
        source_path = f.get("source_path", "")  # e.g. /source/index.html.txt

        # label: filename without .txt suffix, preserving directory.
        label = name[:-4] if name.endswith(".txt") else name

        # canonical page — only meaningful for html pages.
        canonical = ""
        if kind == "html" and live_path:
            # live_path is like /index.html or /privacy/index.html
            canonical = re.sub(r"/index\.html$", "/", live_path)
            if canonical and not canonical.endswith("/"):
                canonical += "/"

        # verify link — the bilingual verify page for the page's tree
        # (/fr/verifier/ for the french edition, /en-au/verify/ otherwise),
        # carrying the page's canonical url as ?path=.
        _verify_base = "/fr/verifier/" if live_path.startswith("/fr/") else "/en-au/verify/"
        if canonical:
            verify_path = _verify_base + "?path=" + canonical.replace("/", "%2F")
        else:
            verify_path = _verify_base

        # SHA-256 of the canonical file (the live, signed bytes — not the
        # source mirror). live_path starts with '/' so strip it before
        # looking up in integrity.json which keys paths without a leading
        # slash. short hex prefix keeps the integrity block tidy.
        sha256_short = ""
        if live_path:
            key = live_path[1:] if live_path.startswith("/") else live_path
            sha256_short = b64_sha256_to_hex_short(integrity_hashes.get(key, ""))

        slug = i18n_slug(name)
        data[name] = {
            "label": label,
            "description": f.get("description", ""),
            "i18n_key": "source.files." + slug + ".description" if slug else "",
            "kind": kind,
            "size": f.get("size_human", ""),
            "modified": f.get("modified", ""),
            "live_path": live_path,
            "canonical": canonical,
            "source_path": source_path,
            "verify_path": verify_path,
            "edition": edition,
            "sha256": sha256_short,
            "signed_release": signed_release,
        }
    return data


def write_manifest_js(data: dict) -> None:
    VIEW_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    js = (
        "/*! trentpower.fr · source-view-manifest.js · "
        "signed via /integrity.json */\n"
        "window.TP_SOURCE_VIEW_MANIFEST=" + payload + ";\n"
    )
    MANIFEST_OUT.write_text(js, encoding="utf-8")
    print(f"  wrote {MANIFEST_OUT} ({len(data)} entries)")


def write_renderer_js() -> None:
    VIEW_DIR.mkdir(parents=True, exist_ok=True)
    src = TEMPLATE_JS.read_text(encoding="utf-8")
    RENDERER_OUT.write_text(src, encoding="utf-8")
    print(f"  wrote {RENDERER_OUT}")


def get_site_scripts_sri(asset_v: str) -> dict:
    """Compute SRI hashes for standard site scripts needed by the shell page."""
    scripts = {
        "theme": pathlib.Path("js/theme.js"),
        "sw-register": pathlib.Path("sw-register.js"),
        "reveal": pathlib.Path("js/reveal.js"),
        "overlay": pathlib.Path("js/overlay.js"),
        "copy": pathlib.Path("js/copy.js"),
        "verify_modal": pathlib.Path("js/verify-modal.js"),
        "fonts": pathlib.Path("js/fonts.js"),
        "styles": pathlib.Path("styles.css"),
        "print": pathlib.Path("print.css"),
    }
    result = {}
    for key, path in scripts.items():
        if path.exists():
            result[key] = compute_sri(path)
    return result


def get_asset_version(canonical: dict) -> str:
    ed = canonical.get("edition", "")
    # try to read the versioned hash from an existing html file.
    # fall back to edition only if not available.
    try:
        html = pathlib.Path("verify/index.html").read_text(encoding="utf-8")
        m = re.search(r'\?v=([\w.\-]+)"', html)
        if m:
            return m.group(1)
    except Exception:
        pass
    return ed


def write_shell_page(asset_v: str, sri: dict) -> None:
    VIEW_DIR.mkdir(parents=True, exist_ok=True)

    # sri for the reader-specific scripts.
    manifest_sri = compute_sri(MANIFEST_OUT)
    renderer_sri = compute_sri(RENDERER_OUT)
    styles_sri = sri.get("styles", "")
    # phase 84 · skip integrity on print.css to match generate_sri.py's
    # site-wide rule (some print engines reject sri on media="print"
    # links and refuse to apply the stylesheet). source-view now
    # matches the other 15 pages — no integrity on print.css.
    print_sri = ""
    theme_sri = sri.get("theme", "")
    swreg_sri = sri.get("sw-register", "")
    reveal_sri = sri.get("reveal", "")
    overlay_sri = sri.get("overlay", "")
    copy_sri = sri.get("copy", "")
    verify_modal_sri = sri.get("verify_modal", "")
    fonts_sri = sri.get("fonts", "")

    def script_tag(src, integrity, extra="defer"):
        if integrity:
            return f'  <script src="{src}?v={asset_v}" integrity="{integrity}" {extra}></script>'
        return f'  <script src="{src}?v={asset_v}" {extra}></script>'

    html = f"""<!doctype html>
<!--
  trentpower.fr · /source/view/
  dynamic source code reader. one static shell; ?file= param selects
  a file from the source mirror. source-view.js fetches /source/*.txt
  and renders with line numbers and restrained syntax colouring.
  no runtime server logic. no external dependencies.
-->
<html lang="en" dir="ltr">
<head>
  <!-- foundations -->
  <meta charset="utf-8">
  <script>(()=>{{const e=document.documentElement;const n=(navigator.languages&&navigator.languages[0])||navigator.language||'en';e.lang=/^fr\\b/i.test(n)?'fr':'en';e.classList.add("js");try{{const m=localStorage.getItem('tp-theme');if(m==='dark'||m==='light')e.dataset.theme=m}}catch{{}}}})();</script>
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="color-scheme" content="light dark">
  <meta name="theme-color" content="#E9E5DC">

  <!-- document -->
  <title>Source reader · Trent Power</title>
  <meta name="description" content="Inspect the public source mirror of trentpower.fr with line numbers and syntax highlighting.">
  <link rel="canonical" href="https://trentpower.fr/source/view/">

  <!-- identity -->
  <meta name="author" content="Trent Power">
  <meta name="application-name" content="Trent Power">
  <meta name="apple-mobile-web-app-title" content="Trent Power">
  <link rel="author" href="/.well-known/attribution.txt">
  <link rel="alternate" type="application/ld+json" href="/.well-known/person.json">

  <!-- discovery -->
  <meta name="robots" content="noindex, nofollow">
  <meta name="referrer" content="no-referrer">

  <!-- social preview (generic source OG) -->
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="Trent Power">
  <meta property="og:title" content="Source reader · Trent Power">
  <meta property="og:description" content="Inspect the public source mirror of trentpower.fr with line numbers and syntax highlighting.">
  <meta property="og:url" content="https://trentpower.fr/source/view/">
  <meta property="og:image" content="https://trentpower.fr/images/og/source-og.png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:type" content="image/png">
  <meta property="og:image:alt" content="Source reader · Trent Power">

  <!-- icons -->
  <link rel="icon" href="/favicon.ico" sizes="any">
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png">
  <link rel="manifest" href="/manifest.webmanifest" type="application/manifest+json">
  <link rel="license" href="https://creativecommons.org/licenses/by-sa/4.0/">

  <!-- assets -->
  <link rel="stylesheet" href="/styles.css?v={asset_v}"{' integrity="' + styles_sri + '"' if styles_sri else ""}>
  <link rel="stylesheet" href="/print.css?v={asset_v}" media="print"{' integrity="' + print_sri + '"' if print_sri else ""}>

  <!-- structured data -->
  <script type="application/ld+json">{{"@context":"https://schema.org","@type":"WebPage","url":"https://trentpower.fr/source/view/","name":"Source reader · Trent Power","description":"Dynamic source code reader for the trentpower.fr public source mirror.","inLanguage":"en","isPartOf":{{"@id":"https://trentpower.fr/#website"}},"about":{{"@id":"https://trentpower.fr/#trent-power"}}}}</script>

</head>
<body data-page="source-reader" data-layout="masthead" data-surface="record" data-masthead="brand-only">

<a href="#main" class="skip-link">Skip to content</a>

<header class="site-header" data-component="site-header">
  <div class="nav">
    <div class="nav-inner">
      <a class="nav-mark" href="/en-au/" aria-label="Trent Power home"><span>Trent</span> <span>Power</span></a>
    </div>
  </div>
</header>

<main class="site source-reader-page" id="main" tabindex="-1">
  <div class="page">
    <section class="source-reader">
      <div id="source-view-root">
        <noscript>
          <p class="page-lede">JavaScript is required to render the source reader. The raw source mirror is available at <a href="/source/">Source</a>.</p>
        </noscript>
      </div>
      <div id="source-toolbar" class="source-toolbar" role="region" aria-label="Selection actions">
        <span class="source-toolbar__count" aria-live="polite">1 line</span>
        <span class="source-toolbar__sep" aria-hidden="true">&middot;</span>
        <button type="button" class="source-toolbar__btn" data-action="copy">Copy</button>
        <span class="source-toolbar__sep" aria-hidden="true">&middot;</span>
        <button type="button" class="source-toolbar__btn" data-action="copy-link">Copy link</button>
        <span class="source-toolbar__sep" aria-hidden="true">&middot;</span>
        <button type="button" class="source-toolbar__btn" data-action="clear" aria-keyshortcuts="Escape">Clear</button>
      </div>
    </section>
  </div>
</main>

<div id="source-announcer" class="source-announcer" aria-live="polite" role="status"></div>

<!-- body · footer -->
<footer class="site-footer" aria-label="Site footer">
  <div class="site-footer__inner">

    <!-- top stratum · identity · nav · language -->
    <div class="site-footer__top">

      <p class="site-footer__identity">
        <span class="year">&copy; <time datetime="2026">2026</time></span>
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

    <!-- bottom stratum · theme switch only.
         the source reader is its own shell — it does not carry the
         publication's edition / SHA / verified colophon (no per-page
         provenance to display in a shared reader). the live editions
         show their colophon in their own footers, linked from the
         source reader's masthead. -->
    <div class="site-footer__bottom">

      <p class="site-footer__provenance" lang="fr">Traduit automatiquement de l’original anglais.</p>

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

  <!-- source reader data + renderer (loaded before site scripts so manifest is available) -->
  <script src="/source/view/source-view-manifest.js?v={asset_v}" integrity="{manifest_sri}" defer></script>
  <script src="/source/view/source-view.js?v={asset_v}" integrity="{renderer_sri}" defer></script>
  <!-- scripts · progressive enhancement, no telemetry -->
{script_tag("/js/theme.js", theme_sri)}
{script_tag("/sw-register.js", swreg_sri)}
{script_tag("/js/reveal.js", reveal_sri)}
{script_tag("/js/overlay.js", overlay_sri)}
{script_tag("/js/copy.js", copy_sri)}
{script_tag("/js/verify-modal.js", verify_modal_sri)}
{script_tag("/js/fonts.js", fonts_sri)}
</body>
</html>
"""
    SHELL_OUT.write_text(html, encoding="utf-8")
    print(f"  wrote {SHELL_OUT}")


def patch_language_shells(asset_v: str) -> None:
    """Patch the manifest <script> tag in the per-language reader shells.

    The per-language reader shells (/en-au/source/view/, /fr/source/voir/)
    are emitted by render_pages.py from a static template that cannot
    know the build-volatile source-view-manifest.js hash. Their manifest
    <script> therefore carries a stale SRI; the browser blocks the
    manifest and the reader resolves nothing ("File not found in source
    manifest"). Patch the tag here, where the fresh hash is known, so it
    matches the manifest the root /source/view/ shell also verifies."""
    manifest_sri = compute_sri(MANIFEST_OUT)
    new_tag = (
        f'<script src="/source/view/source-view-manifest.js?v={asset_v}" '
        f'integrity="{manifest_sri}" defer></script>'
    )
    pat = re.compile(
        r'<script src="/source/view/source-view-manifest\.js[^"]*"'
        r'(?:\s+integrity="[^"]*")?\s*defer></script>'
    )
    for shell in sorted(pathlib.Path(".").glob("*/source/*/index.html")):
        html = shell.read_text(encoding="utf-8")
        if "/source/view/source-view-manifest.js" not in html:
            continue
        patched = pat.sub(new_tag, html, count=1)
        if patched != html:
            shell.write_text(patched, encoding="utf-8")
            print(f"  patched manifest SRI → {shell}")


def main():
    print("generate_source_reader.py")

    if not MANIFEST_IN.exists():
        print(
            f"ERROR: {MANIFEST_IN} not found — run generate_source_view.py first", file=sys.stderr
        )
        sys.exit(1)

    if not TEMPLATE_JS.exists():
        print(f"ERROR: {TEMPLATE_JS} not found", file=sys.stderr)
        sys.exit(1)

    canonical = load_canonical()
    manifest = json.loads(MANIFEST_IN.read_text(encoding="utf-8"))
    files = manifest.get("files", [])
    edition_id = canonical.get("edition", "") or manifest.get("edition", "")
    integrity_hashes = load_integrity_hashes()

    VIEW_DIR.mkdir(parents=True, exist_ok=True)

    # 1. renderer js (from template).
    write_renderer_js()

    # 2. metadata manifest js. carries edition / sha256 / signed-release so
    #    the in-page integrity block can render a verifiable ledger row
    #    without a second fetch.
    data = build_manifest_data(files, edition_id, integrity_hashes)
    write_manifest_js(data)

    # 3. compute sri for standard site scripts.
    asset_v = get_asset_version(canonical)
    sri = get_site_scripts_sri(asset_v)

    # 4. shell page with all sri hashes baked in.
    write_shell_page(asset_v, sri)

    # 5. patch the per-language reader shells' manifest SRI — render_pages
    #    emits them from a static template and cannot know the hash.
    patch_language_shells(asset_v)

    print(f"  source reader ready at /source/view/ ({len(data)} files in manifest)")


if __name__ == "__main__":
    main()
