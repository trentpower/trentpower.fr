#!/usr/bin/env python3
"""
generate_site.py , Generate all derived identity files from identity_canonical.json.

Invoked by tools/build.sh; runnable directly from the repo root:
    python3 tools/generate_site.py
The script resolves its own paths via _TOOLS_DIR and chdir(public/),
so cwd does not matter beyond the path-resolution boundary.

Generates:
  - /.well-known/person.json   (JSON-LD Person entity)
  - /site-metadata.json         (machine-readable site metadata)
  - /js/verify-modal.js         (verify action menu + clipboard handler)
  - /llms.txt                   (LLM identity summary)
  - /sitemap.xml                (sitemap with file mtimes)

Updates in-place:
  - /index.html                 (meta description, og:description, Person + WebSite JSON-LD, document-edition)
  - All HTML files              (document-edition meta tag)
  - /integrity/index.html       (Last reviewed date)
  - /.htaccess                  (CSP hashes for updated JSON-LD)

Validates:
  - All required fields present
  - URLs match canonical domain
  - Edition date is well-formed

No build pipeline. No dependencies. Run before upload.
"""

import hashlib
import json
import os
import re
import sys
import sys as _sys
from datetime import datetime

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
import routes as _routes
from dates import LOCALE_MONTHS, human_date  # noqa: E402
from hashing import sri_sha256  # noqa: E402
from minify import minify_css, minify_js  # noqa: E402
from paths import (
    I18N_STRINGS as _PATHS_I18N_STRINGS,
)
from paths import (
    IDENTITY_CANONICAL as _PATHS_IDENTITY_CANONICAL,
)
from paths import (
    PUBLIC_DIR as _PATHS_PUBLIC_DIR,
)
from paths import (
    REPO_ROOT as _PATHS_REPO_ROOT,
)
from paths import (
    TEMPLATES_DIR as _PATHS_TEMPLATES_DIR,
)
from paths import (
    TOOLS_DIR as _PATHS_TOOLS_DIR,
)
from urls import host_matches  # noqa: E402

_TOOLS_DIR = str(_PATHS_TOOLS_DIR)
_REPO_ROOT = str(_PATHS_REPO_ROOT)
ROOT = str(_PATHS_PUBLIC_DIR)
TEMPLATES_DIR = str(_PATHS_TEMPLATES_DIR)
I18N_STRINGS = str(_PATHS_I18N_STRINGS)

# identity_canonical.json lives in tools/ (build source-of-truth, not
# served). resolved from the script's own directory rather than via
# the cwd-relative literal "identity_canonical.json" so chdir(root)
# does not break the read.
CANONICAL_FILE = str(_PATHS_IDENTITY_CANONICAL)

# active site uses clean filenames (styles.css / app.js / verify-modal.js / fonts/*.woff2).
# versioned filenames exist only inside frozen archive paths
# /integrity/releases/YYYY-MM/assets/.
ASSET_MODE = "clean"

# asset bundle the cache-bust version hashes over. order is sorted
# deterministically; sw.js and verify/verification-data.js are intentionally
# excluded (sw.js would create a hash → cache-name → hash cycle, and
# verification-data.js is regenerated downstream of this script).
ASSET_BUNDLE = sorted(
    [
        "js/copy.js",
        "js/edition.js",
        "js/fonts.js",
        "fonts-full.css",
        "js/overlay.js",
        "print.css",
        "js/reveal.js",
        "styles.css",
        "sw-register.js",
        "js/theme.js",
        "js/verify-modal.js",
        "verify/verify.js",
    ]
)

# all html files that carry document-edition
HTML_FILES = [
    "index.html",
    "privacy/index.html",
    "integrity/index.html",
    "integrity/releases/index.html",
    "integrity/verify-locally/index.html",
    "security/index.html",
    "security/acknowledgments/index.html",
    "source/index.html",
    "verify/index.html",
    "403.html",
    "404.html",
    "500.html",
    "maintenance.html",
]


def ml_en(field):
    """Extract English value from a multilingual dict, or return as-is."""
    return field["en"] if isinstance(field, dict) else field


def compact(d):
    """Remove None values from a dict."""
    return {k: v for k, v in d.items() if v is not None}


# Per-locale regex matching any prior "(d|dd) <month-name> yyyy" form
# (with optional spanish "de"/"de" particles or german "."). used by the
# sweep to find stale dates regardless of the date they happen to carry.
def _locale_human_date_re(lang):
    months = LOCALE_MONTHS.get(lang, LOCALE_MONTHS["en"])
    alt = "|".join(re.escape(m) for m in months)
    if lang == "es":
        return re.compile(r"\b\d{1,2}\s+de\s+(?:" + alt + r")\s+de\s+\d{4}\b")
    if lang == "de":
        return re.compile(r"\b\d{1,2}\.\s+(?:" + alt + r")\s+\d{4}\b")
    return re.compile(r"\b\d{1,2}\s+(?:" + alt + r")\s+\d{4}\b")


# homepage size used to be embedded in the print evidence chip, but
# self-referential bytes (the kb string was a function of the html
# containing it) introduced silent drift on every build. the chip now
# carries identity + date only; per-file canonical sizes live in
# /source/ and /file-metadata.json.

# ─── Helper: compute csp hash ────────────────────────────────


def csp_hash(content):
    """Compute SHA-256 CSP hash for an inline script block."""
    return sri_sha256(content.encode("utf-8"))


_LANG_NAMES = {"en": "English", "fr": "French"}

# edition label is derived from the YYYY-MM-DD edition so the canonical
# date stays the single source of truth — the label is rendered as
# `month-name year` (e.g. "may 2026"). operators editing
# identity_canonical.json never have to update the label by hand.
_MONTH_LABELS = [
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

# ─── edition sync , keep every published date stamp matching ──
# identity_canonical.json's `edition`. this is the single source of
# truth; future edition bumps require only one edit there.
#
# what gets rewritten in-place:
#   • every active html file: data-edition="…", meta document-edition,
#     and the static fallback "edition YYYY-MM-DD" / "Édition …" /
#     "edizione …" / "edición …" / "ausgabe …" strings inside the
#     print sheets (these are i18n-bound, but the html default text
#     also tracks the canonical date for no-JS visitors).
#   • i18n/strings.json: the same patterns inside any string value.
#   • integrity/releases/2026-MM/ paths are never rewritten , the
#     /YYYY-MM/ path component is part of the url, not a date stamp.
#
# frozen archive directories under integrity/releases/<edition>/
# are intentionally immutable and skipped.

EDITION_LITERAL = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
EDITION_PREFIXES = ("Edition", "Édition", "Edizione", "Edición", "Ausgabe")
EDITION_PREFIX_RE = re.compile(r"\b(" + "|".join(EDITION_PREFIXES) + r")\s+\d{4}-\d{2}-\d{2}\b")


# every active .html under public/ — discovered by walk so the
# bilingual /en-au/ and /fr/ trees, the language gate and the per-tree
# error pages are all swept for the edition tag and the ?v= asset
# version. excluded: the dated frozen-archive snapshots (PGP-signed
# historical bytes) and the generated editorial review documents.
def _discover_active_html():
    import glob

    out = []
    for p in sorted(glob.glob("**/*.html", recursive=True)):
        if re.match(r"integrity/releases/[^/]+/", p):
            continue
        if p.startswith("editorial/"):
            continue
        out.append(p)
    return out


def _sweep_edition_in_html(html_path, ed):
    if not os.path.exists(html_path):
        return False
    with open(html_path, encoding="utf-8") as f:
        text = f.read()
    new = text
    # data-edition="..."
    new = re.sub(r'(data-edition=")[^"]*(")', rf"\g<1>{ed}\2", new)
    # <meta name="document-edition" content="...">
    new = re.sub(
        r'(<meta name="document-edition" content=")[^"]*(")',
        rf"\g<1>{ed}\2",
        new,
    )
    # JSON-LD datemodified — per-file placeholder resolved by
    # generate_file_metadata.py --sweep using content-history dates
    # rather than the canonical edition. the regex matches three forms
    # so the sweep is idempotent: legacy date-only, current datetime,
    # and any pre-existing placeholder from an earlier build.
    new = re.sub(
        r'("dateModified"\s*:\s*")(?:\{\{datemod:[^}]+\}\}|\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}[+\-]\d{2}:\d{2})?)(")',
        rf"\g<1>{{{{datemod:{html_path}}}}}\2",
        new,
    )
    # webpage edition-archive link "/integrity/releases/<edition>/"
    # — only on pages that should track the current edition's release
    # archive (e.g. /verify/ intro panel, /sw-reset/ JSON-LD). the
    # rendered source page (/source/index.html) is excluded because
    # its release-records rows reference specific historical mirror
    # files that live under their original edition path, not the
    # current canonical one. the releases lineage page is also
    # excluded — its archive entries link to specific frozen release
    # directories (2026-05-09, 2026-05-17, etc.) and those paths
    # must not be rewritten to the canonical edition. frozen 2026-02
    # archive html is also untouched (those files are sealed historical
    # bytes).
    html_norm = html_path.replace(os.sep, "/")
    is_source_page = html_norm.startswith("source/") or "/source/" in html_norm
    # the bilingual releases-lineage page (en/integrity/releases/,
    # fr/integrite/archives/) lists every edition, current and frozen;
    # its per-edition links must never be collapsed onto the canonical
    # edition.
    is_releases_index = html_norm in {
        _routes.route_output("integrity-releases", _l) for _l in _routes.languages()
    }
    if not is_source_page and not is_releases_index:
        new = re.sub(
            r"(/integrity/releases/)\d{4}-\d{2}-\d{2}(/)",
            rf"\g<1>{ed}\2",
            new,
        )
        # the archive filename carries the edition too: a current-
        # release link is /integrity/releases/<ed>/trentpower-fr-<ed>.zip
        # — sweep the filename's date in lockstep with the directory.
        new = re.sub(
            r"(trentpower-fr-)\d{4}-\d{2}-\d{2}(\.(?:zip|tar\.gz))",
            rf"\g<1>{ed}\2",
            new,
        )
    # inline edition <code> in the verify intro panel — anchored to
    # a unique class so this sweep cannot touch any other date code.
    # the date is wrapped in <time datetime="…"> for machine-readable
    # markup; the sweep rewrites the entire code body each time so the
    # datetime attribute and visible text stay in lockstep.
    new = re.sub(
        r'<code class="verify-intro-edition-value">.*?</code>',
        f'<code class="verify-intro-edition-value"><time datetime="{ed}">{ed}</time></code>',
        new,
        flags=re.DOTALL,
    )
    # footer imprint edition stamp — anchored to the .imprint-edition
    # <dd>; rewritten as a whole so the datetime attribute and the
    # visible text stay in lockstep with the canonical edition.
    new = re.sub(
        r'<dd class="imprint-edition">.*?</dd>',
        f'<dd class="imprint-edition"><time datetime="{ed}">{ed}</time></dd>',
        new,
        flags=re.DOTALL,
    )
    # "edition / Édition / … YYYY-MM-DD" , replace prefix + date as a unit.
    new = EDITION_PREFIX_RE.sub(lambda m: f"{m.group(1)} {ed}", new)
    # same prefix forms but wrapping the date in a <time> element, e.g.
    # "edition <time datetime="YYYY-MM-DD">YYYY-MM-DD</time>" inside the
    # print-edition <p>. the plain-text EDITION_PREFIX_RE above cannot
    # match because the prefix is followed by `<`, so this is a separate
    # sub anchored on the <time> shape.
    new = re.sub(
        r'<time datetime="\d{4}-\d{2}-\d{2}">\d{4}-\d{2}-\d{2}</time>',
        f'<time datetime="{ed}">{ed}</time>',
        new,
    )
    # print-evidence chip: matches both the legacy literal
    # ("public record · html · 28 kb · validated <time…>…</time>")
    # and the current form ("public record · html · edition <time…>…</time>").
    # the chip is en-only at the static fallback level; runtime i18n
    # swaps it for the locale form via data-i18n-html.
    new = re.sub(
        r'(<p class="print-evidence"[^>]*>)[^<]*<time datetime="\d{4}-\d{2}-\d{2}">\d{4}-\d{2}-\d{2}</time>(</p>)',
        rf'\g<1>Public record · HTML · Edition <time datetime="{ed}">{ed}</time>\g<2>',
        new,
    )
    if new != text:
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(new)
        return True
    return False


def _sweep_edition_in_strings(strings_path, ed, edition_dt):
    """Sweeps the i18n strings tree for two patterns at once:
    1. ISO 'Edition YYYY-MM-DD' / 'Édition …' / 'Edizione …' / etc.
       → updated to the canonical ISO edition.
    2. Localised human dates ('1 May 2026' / '1 mai 2026' /
       '1. Mai 2026' / '1 de mayo de 2026' / '1 maggio 2026')
       → updated to today's localised form per top-level lang key.
    Also stamps the print.footer.evidence chip with the current
    homepage size (KB) and validated date so the evidence line is
    self-updating, never hardcoded."""
    if not os.path.exists(strings_path):
        return False
    with open(strings_path, encoding="utf-8") as f:
        data = json.load(f, object_pairs_hook=__import__("collections").OrderedDict)

    # paths to skip during localised-date rewriting. these look like dates
    # but reference frozen archives (e.g. "01 may 2026" = card label for
    # the may 2026 release archive). rewriting them would rewrite history.
    # keys whose values reference a specific frozen archive page and
    # must not be swept to the current canonical edition. these all
    # pin to the 9 may 2026 archive page or earlier release records.
    IGNORE_PREFIXES = (
        "releases.print.card.",
        "releases.detail.",
        "releases.edition_may09_",
        "releases.edition_feb_",
        "release_archive.print.",
    )

    def _walk(obj, lang, date_re, localised, trail):
        if isinstance(obj, str):
            ignored = any(trail.startswith(p) for p in IGNORE_PREFIXES)
            s = obj if ignored else EDITION_PREFIX_RE.sub(lambda m: f"{m.group(1)} {ed}", obj)
            # sweep <time datetime="YYYY-MM-DD">YYYY-MM-DD</time> wrappers
            # (e.g. inside print.footer.edition for data-i18n-html). the
            # EDITION_PREFIX_RE above cannot match across html tags.
            # also skipped for frozen-archive-pinned keys.
            if not ignored:
                s = re.sub(
                    r'<time datetime="\d{4}-\d{2}-\d{2}">\d{4}-\d{2}-\d{2}</time>',
                    f'<time datetime="{ed}">{ed}</time>',
                    s,
                )
            if date_re is not None and localised and not ignored:
                s = date_re.sub(localised, s)
            return s
        if isinstance(obj, dict):
            for k, v in obj.items():
                sub = f"{trail}.{k}" if trail else k
                obj[k] = _walk(v, lang, date_re, localised, sub)
            return obj
        if isinstance(obj, list):
            return [_walk(x, lang, date_re, localised, trail) for x in obj]
        return obj

    for lang in list(data.keys()):
        if lang not in LOCALE_MONTHS:
            # walk for iso edition prefix only; skip locale-specific date sub.
            _walk(data[lang], lang, None, None, "")
            continue
        date_re = _locale_human_date_re(lang)
        localised = human_date(edition_dt, lang=lang) if edition_dt else None
        _walk(data[lang], lang, date_re, localised, "")

        # specifically refresh the evidence chip with the current edition
        # date. "validated" was misleading (no validation event happened
        # on edition day — that's the publication date), so the chip now
        # says "edition". the size token was dropped because it was self-
        # referential — see /file-metadata.json for canonical sizes.
        evidence_label = {
            "en": f"Public record · HTML · Edition {localised}",
            "fr": f"Document public · HTML · Édition du {localised}",
            "it": f"Documento pubblico · HTML · Edizione {localised}",
            "es": f"Documento público · HTML · Edición {localised}",
            "de": f"Öffentlicher Beleg · HTML · Ausgabe {localised}",
        }.get(lang)
        if (
            evidence_label
            and "print" in data[lang]
            and isinstance(data[lang].get("print"), (dict,))
        ):
            footer = data[lang]["print"].get("footer")
            if isinstance(footer, dict) and "evidence" in footer:
                footer["evidence"] = evidence_label

    new_text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    with open(strings_path, encoding="utf-8") as f:
        old_text = f.read()
    if new_text != old_text:
        with open(strings_path, "w", encoding="utf-8") as f:
            f.write(new_text)
        return True
    return False


# ─── compute ASSET_VERSION + sweep cache-bust into html ──────
# one canonical version of the form "{edition}.{hash8}" derived from
# the bundled state of active css + js. stored in site-metadata.json
# and applied as ?v={asset_version} on every active CSS/JS reference
# in html by `_sweep_asset_version_in_html()`. the hash domain is
# ASSET_BUNDLE (defined at the top); changing any of those files
# changes the version, which busts every reference in lockstep.

# collapse both `/fonts-full.<v>.css` (legacy dated form, may still
# appear in cached source bytes during the transition cycle) AND
# `/fonts-full.css?v=<v>` (new query-string form) back to the clean
# `/fonts-full.css` literal before hashing. without this normalisation
# the asset_version depends on the version literal embedded by the
# post-compute substitution pass, and the build oscillates between
# two values — the validator at predeploy stage 7 catches the drift.
_VER_LITERAL_RE_LEGACY = re.compile(rb"(/fonts-full)\.\d{4}-\d{2}-\d{2}\.[a-f0-9]{8}(\.css)")
_VER_LITERAL_RE_QUERY = re.compile(rb"(/fonts-full\.css)\?v=\d{4}-\d{2}-\d{2}\.[a-f0-9]{8}")

# the `var I18N_VTAG='<asset_version>'` literal in /app.js is the
# runtime cache-bust tag for lazy /i18n/<lang>.js fetches. it must
# be normalised back to `var I18N_VTAG=''` before the asset_version
# hash is computed — otherwise the literal embeds the version it
# carries and the build oscillates between two values (same defect
# the _VER_LITERAL_RE above guards against for /app-enhance.<v>.js).
_I18N_VTAG_RE = re.compile(rb"var I18N_VTAG\s*=\s*'\d{4}-\d{2}-\d{2}\.[a-f0-9]{8}';?")


def _compute_asset_version(ed):
    h = hashlib.sha256()
    for rel in ASSET_BUNDLE:
        if not os.path.exists(rel):
            print(f"  ⚠ asset-version: {rel} missing — bundle incomplete", file=sys.stderr)
            continue
        with open(rel, "rb") as fp:
            data = fp.read()
        data = _VER_LITERAL_RE_LEGACY.sub(rb"\1\2", data)
        data = _VER_LITERAL_RE_QUERY.sub(rb"\1", data)
        data = _I18N_VTAG_RE.sub(b"var I18N_VTAG = '';", data)
        digest = hashlib.sha256(data).digest()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(digest)
    return f"{ed}.{h.hexdigest()[:8]}"


def _sweep_asset_version_in_html(html_path, version):
    # skip the dated frozen-archive snapshots under
    # integrity/releases/<edition>/ — PGP-signed historical bytes that
    # must never be rewritten. the bilingual editorial releases page
    # (en/integrity/releases/, fr/integrite/archives/) is a live page,
    # not a frozen snapshot, and is swept normally.
    if re.match(r"integrity/releases/[^/]+/", html_path):
        return False
    if not os.path.exists(html_path):
        return False
    with open(html_path, encoding="utf-8") as fp:
        text = fp.read()
    new = text
    for asset in ASSET_BUNDLE:
        # match href="/{asset}" or src="/{asset}" optionally followed by ?v=…
        # replace any prior query string with the current asset_version
        # (idempotent , re-running rewrites the same value).
        pat = re.compile(r'((?:href|src)=")(/' + re.escape(asset) + r')(\?v=[^"]*)?(")')
        new = pat.sub(rf"\g<1>\g<2>?v={version}\g<4>", new)
    # /verify/verification-data.js is precached and surfaces verify state;
    # bust it on the same canonical version so a verify-data refresh is
    # never blocked by a stale ?v=. it is not in ASSET_BUNDLE because it
    # is regenerated downstream of this script (see plan).
    extra = "verify/verification-data.js"
    pat = re.compile(r'((?:href|src)=")(/' + re.escape(extra) + r')(\?v=[^"]*)?(")')
    new = pat.sub(rf"\g<1>\g<2>?v={version}\g<4>", new)
    if new != text:
        with open(html_path, "w", encoding="utf-8") as fp:
            fp.write(new)
        return True
    return False


# substitute the references that js uses to load these files.
def _patch_js_literal(path, old_literal, new_literal):
    if not os.path.exists(path):
        return
    text = open(path, encoding="utf-8").read()
    if old_literal not in text:
        return
    open(path, "w", encoding="utf-8").write(text.replace(old_literal, new_literal))


def _topic_name(term):
    """a knowsAbout entry is a concept string or a DefinedTerm object."""
    return term["name"] if isinstance(term, dict) else term


# indexed page routes — one entry per language edition, each carrying
# the full hreflang cluster. every other route is intentionally
# noindexed and omitted (integrity overview, release archive,
# verify-locally, acknowledgments, the source pages). changefreq +
# priority are keyed by route key.
SITEMAP_ROUTE_META = {
    "home": ("monthly", "1.0"),
    "privacy": ("yearly", "0.3"),
    "verify": ("yearly", "0.4"),
    "security": ("yearly", "0.3"),
}

# per-language priority overrides — /en-au/ is the author's edition
# and remains the primary ranking target (1.0); /fr/ is a
# machine-translated rendering and carries a slightly lower priority
# (0.9) as a supporting signal. the root / sits below both at 0.5,
# emitted inline below.
SITEMAP_PRIORITY_OVERRIDES = {
    "home": {"fr": "0.9"},
}

# Non-HTML resources (no hreflang, changefreq, or priority)
SITEMAP_ASSETS = [
    ("/attestations.json", "attestations.json"),
    ("/integrity.json", None),  # always regenerated , use edition date
    ("/integrity.json.sig", None),  # always regenerated , use edition date
    ("/manifest.webmanifest", "manifest.webmanifest"),
    ("/site-metadata.json", "site-metadata.json"),
    ("/.well-known/person.json", ".well-known/person.json"),
    ("/llms.txt", "llms.txt"),
    ("/ai-usage.txt", "ai-usage.txt"),
]


def get_lastmod(file_path, edition):
    # emit a placeholder; generate_file_metadata.py --sweep resolves it
    # against content-history-anchored modified_iso. assets without a
    # backing public file (e.g. synthetic entries) fall back to edition.
    if file_path is None:
        return edition
    if os.path.exists(file_path):
        return f"{{{{lastmod:{file_path}}}}}"
    return edition


def _hreflang_lines(cluster):
    # keys are BCP47 tags from routes.hreflang_cluster (en-AU, fr,
    # x-default). loop over them rather than hardcoding so the function
    # auto-follows any future locale change.
    out = []
    for hl in cluster.keys():
        out.append(f'    <xhtml:link rel="alternate" hreflang="{hl}" href="{cluster[hl]}"/>')
    return out


def main() -> int:
    os.chdir(ROOT)

    # ─── load canonical ──────────────────────────────────────────

    if not os.path.exists(CANONICAL_FILE):
        print(f"ERROR: {CANONICAL_FILE} not found", file=sys.stderr)
        sys.exit(1)

    with open(CANONICAL_FILE) as f:
        canon = json.load(f)

    # ─── validation ──────────────────────────────────────────────

    errors = []

    # required top-level fields
    for field in ["domain", "url", "edition", "person", "sameAs", "image"]:
        if field not in canon:
            errors.append(f"Missing required field: {field}")

    # required person fields
    person = canon.get("person", {})
    for field in [
        "name",
        "jobTitle",
        "description",
        "addressLocality",
        "addressCountry",
        "worksFor",
        "alumniOf",
        "knowsAbout",
    ]:
        if field not in person:
            errors.append(f"Missing person.{field}")

    # edition date format
    edition = canon.get("edition", "")
    try:
        edition_dt = datetime.strptime(edition, "%Y-%m-%d")
    except ValueError:
        errors.append(f"Edition date must be YYYY-MM-DD, got: {edition}")
        edition_dt = None

    # url consistency
    domain = canon.get("domain", "")
    url = canon.get("url", "")
    if domain and url:
        if f"https://{domain}" != url:
            errors.append(f"URL '{url}' does not match domain '{domain}'")

    # sameas urls must be valid
    for sa in canon.get("sameAs", []):
        if not sa.startswith("https://"):
            errors.append(f"sameAs entry must start with https://: {sa}")

    # image fields
    img = canon.get("image", {})
    for field in [
        "filename",
        "creditText",
        "copyrightNotice",
        "license",
        "creatorName",
        "creatorUrl",
    ]:
        if field not in img:
            errors.append(f"Missing image.{field}")

    if errors:
        print("VALIDATION ERRORS:", file=sys.stderr)
        for e in errors:
            print(f"  ✗ {e}", file=sys.stderr)
        sys.exit(1)

    print("✓ Canonical validation passed")
    # ─── derived values ──────────────────────────────────────────

    base_url = canon["url"]
    description = ml_en(person["description"])
    fr_description = (
        person["description"].get("fr", description)
        if isinstance(person["description"], dict)
        else description
    )
    # the root / is a language-selection gateway, not the canonical authored
    # page. it carries a deliberately modest meta description so search
    # engines don't rank it as the primary content surface — the editions
    # (/en-au/ and /fr/) carry the full authored description.
    gate_description = "Choose the English or French edition of Trent Power's publication."
    entity_summary = ml_en(person["entity_summary"])
    job_title = ml_en(person["jobTitle"])
    ka_field = person["knowsAbout"]
    # english-first machine data: the language-neutral gate graph exposes the
    # english knowsAbout concepts only. per-language editions localise downstream
    # in render_pages.py phase b.
    knows_about = ml_en(ka_field) if isinstance(ka_field, dict) else ka_field

    works_for = person["worksFor"]
    works_for_name = works_for["name"] if isinstance(works_for, dict) else works_for
    works_for_sameas = works_for.get("sameAs") if isinstance(works_for, dict) else None

    alumni_of = person["alumniOf"]
    alumni_of_name = alumni_of["name"] if isinstance(alumni_of, dict) else alumni_of
    alumni_of_sameas = alumni_of.get("sameAs") if isinstance(alumni_of, dict) else None

    orcid = person.get("orcid", "")
    citation = f"{person['name']}. Personal Site. Paris, France. Edition {edition}. {domain}"

    # Human-readable edition date: "21 february 2026"
    if edition_dt:
        edition_human = edition_dt.strftime("%-d %B %Y")
    else:
        edition_human = edition

    # ─── build person JSON-LD (shared by person.json and inline) ─

    # jobtitle / disambiguatingdescription , single english string. the
    # language-neutral gate graph carries english machine data; the /fr/
    # edition localises these fields in render_pages.py phase b. this keeps
    # each language tree exposing one clear value rather than a multilingual
    # @language array on every page.
    job_title_jsonld = job_title
    disamb_desc_jsonld = description

    # alternatename , optional latin/transliterated variant from canonical.
    # none today (the chinese-script name was removed); compact() drops it.
    alternate_name = person.get("alternateName")

    # subjectof , build webpage entries from canonical
    subject_of = [
        compact(
            {
                "@type": "WebPage",
                "name": pg["name"],
                "url": pg.get("url"),
            }
        )
        for pg in person.get("subjectOf", [])
    ]
    # typed language objects per Schema.org guidance — preferred over bare
    # strings for richer structured-data extraction. plain iso codes still
    # accepted by validator.schema.org but the typed form makes the spoken
    # languages first-class.
    knows_language_typed = [
        {"@type": "Language", "name": _LANG_NAMES.get(code, code), "alternateName": code}
        for code in person.get("knowsLanguage", ["en"])
    ]

    # orcid is already in sameas; the `identifier` propertyvalue carries
    # the typed assertion of the same id so consumers that parse identifier
    # specifically (rather than walking sameas) pick it up.
    orcid_id = person.get("orcid", "")
    identifier_jsonld = (
        {
            "@type": "PropertyValue",
            "propertyID": "ORCID",
            "value": orcid_id,
            "url": f"https://orcid.org/{orcid_id}",
        }
        if orcid_id
        else None
    )

    person_jsonld = compact(
        {
            "@context": "https://schema.org",
            "@type": "Person",
            "@id": f"{base_url}/#trent-power",
            "name": person["name"],
            "givenName": "Trent",
            "familyName": "Power",
            "alternateName": alternate_name,
            "url": base_url,
            "sameAs": canon["sameAs"],
            "identifier": identifier_jsonld,
            "jobTitle": job_title_jsonld,
            "disambiguatingDescription": disamb_desc_jsonld,
            "description": entity_summary,
            "nationality": compact({"@type": "Country", "name": person.get("nationality", "")})
            or None,
            "worksFor": compact(
                {"@type": "Organization", "name": works_for_name, "sameAs": works_for_sameas}
            ),
            "address": {
                "@type": "PostalAddress",
                "addressLocality": person["addressLocality"],
                "addressCountry": person["addressCountry"],
            },
            "alumniOf": compact(
                {"@type": "CollegeOrUniversity", "name": alumni_of_name, "sameAs": alumni_of_sameas}
            ),
            "knowsAbout": knows_about,
            "knowsLanguage": knows_language_typed,
            "mainEntityOfPage": {"@id": f"{base_url}/#profile-page"},
            "subjectOf": subject_of if subject_of else None,
            "image": {
                "@type": "ImageObject",
                "@id": f"{base_url}/#trent-power-image",
                "url": f"{base_url}/images/portraits/{img['filename']}",
                "creditText": img["creditText"],
                "copyrightNotice": img["copyrightNotice"],
                "license": img["license"],
                "acquireLicensePage": img.get("acquireLicensePage", img["creatorUrl"]),
                "creator": {
                    "@type": "Person",
                    "name": img["creatorName"],
                    "url": img["creatorUrl"],
                },
            },
        }
    )

    # ─── build website JSON-LD ───────────────────────────────────

    website_jsonld = {
        "@type": "WebSite",
        "@id": f"{base_url}/#website",
        "name": person["name"],
        "description": description,
        "url": f"{base_url}/",
        "author": {"@id": f"{base_url}/#trent-power"},
        "publisher": {"@id": f"{base_url}/#trent-power"},
        "copyrightYear": 2026,
        "copyrightHolder": {"@id": f"{base_url}/#trent-power"},
        # one website entity covers both editions, so inLanguage carries
        # both bcp47 tags. _localise_homepage_jsonld does NOT override this
        # per-edition (the WebSite is a global entity, not a page entity).
        "inLanguage": ["en-AU", "fr"],
        "dateModified": "{{datemod:index.html}}",
    }

    # NOTE: the homepage profilepage/clienteling/person/@graph payload that
    # used to be assembled here was dead — it built a full localised homepage
    # @graph (homepage_graph_payload / homepage_graph_inline) that nothing
    # consumed. the live homepage JSON-LD is produced by render_pages.py from
    # the home.html template (see _localise_homepage_jsonld). profilepage_jsonld
    # and clienteling_jsonld fed only that dead payload and were removed with it.
    # website_jsonld is retained below — it is still consumed by the language-gate
    # graph. person_jsonld is retained — it backs /.well-known/person.json.

    # language-gate graph — a deliberately modest WebSite + WebPage. the
    # root / is a language-selection page, not the canonical biography or
    # profile. the rich person / ProfilePage / DefinedTerm entities live
    # on the per-edition pages (/en-au/ and /fr/), where the visible
    # definitions actually exist. no person node is emitted on the gate —
    # the WebSite's author / publisher / copyrightHolder @id references
    # resolve to the canonical person defined on the editions, keeping the
    # gate from competing with the editions as an identity document.
    language_gate_webpage = {
        "@type": "WebPage",
        "@id": f"{base_url}/#language-gate",
        "url": f"{base_url}/",
        "name": "Choose a language",
        "description": (
            "Language selection gateway for trentpower.fr. The publication "
            "is available as an English edition (/en-au/) and a machine-translated "
            "French rendering (/fr/)."
        ),
        "isPartOf": {"@id": f"{base_url}/#website"},
        "inLanguage": ["en-AU", "fr"],
        "about": {"@id": f"{base_url}/#website"},
    }
    gate_graph_payload = {
        "@context": "https://schema.org",
        "@graph": [
            website_jsonld,
            language_gate_webpage,
        ],
    }
    gate_graph_inline = json.dumps(
        gate_graph_payload,
        ensure_ascii=False,
        indent=2,
    )

    # ─── generate /.well-known/person.json ───────────────────────

    os.makedirs(".well-known", exist_ok=True)
    with open(".well-known/person.json", "w") as f:
        json.dump(person_jsonld, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("  → .well-known/person.json")

    # ─── generate /site-metadata.json ────────────────────────────

    privacy = canon.get("privacy", {})
    license_info = canon.get("license", {})
    _ed_year, _ed_month, _ed_day = edition.split("-")
    edition_label = f"{_MONTH_LABELS[int(_ed_month) - 1]} {_ed_year}"

    orcid_url = f"https://orcid.org/{orcid}" if orcid else None
    linkedin_url = next((s for s in canon["sameAs"] if host_matches(s, "linkedin.com")), None)
    github_url = next((s for s in canon["sameAs"] if host_matches(s, "github.com")), None)
    author_same_as = [u for u in (orcid_url, linkedin_url, github_url) if u]

    site_metadata = {
        "type": "PersonalSiteMetadata",
        "schema_version": "1.0",
        "name": person["name"],
        "description": person.get("description", {}).get("en", ""),
        "url": base_url,
        "canonical_url": f"{base_url}/",
        "language": ["en-AU", "fr"],
        "edition": {
            "id": edition,
            "label": edition_label,
            "date": edition,
        },
        "author": {
            "name": person["name"],
            "identity": f"{base_url}/#trent-power",
            "orcid": orcid_url,
            "linkedin": linkedin_url,
            "github": github_url,
            "same_as": author_same_as,
        },
        "publisher": {
            "name": person["name"],
            "url": base_url,
        },
        "information_classes": {
            "declared": "Statements authored directly on this site",
            "attested": "Cryptographic verification of document authenticity",
        },
        "trust_order": ["attested", "declared"],
        "integrity": {
            "manifest": f"{base_url}/integrity.json",
            "signature": f"{base_url}/integrity.json.sig",
            "public_key": f"{base_url}/.well-known/pgp-key.asc",
            "checksums": f"{base_url}/SHA256SUMS",
        },
        "privacy": {
            "tracking": privacy.get("tracking", False),
            "analytics": privacy.get("analytics", False),
            "cookies": privacy.get("cookies", False),
            "third_party_requests": privacy.get("thirdPartyRequests", False),
            "attestations": f"{base_url}/attestations.json",
        },
        "citation": {
            "text": citation,
            "format": "plain-text",
        },
        "license": {
            "content": license_info.get("content", "All rights reserved"),
            "portrait": license_info.get("portrait", ""),
        },
        "machine_readable": {
            "person": f"{base_url}/.well-known/person.json",
            "webfinger": f"{base_url}/.well-known/webfinger",
            "security": f"{base_url}/.well-known/security.txt",
            "attestations": f"{base_url}/attestations.json",
        },
    }

    # remove none values from author
    site_metadata["author"] = {k: v for k, v in site_metadata["author"].items() if v is not None}

    with open("site-metadata.json", "w") as f:
        json.dump(site_metadata, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("  → site-metadata.json")

    # ─── generate /.well-known/build.json ────────────────────────
    # small machine-readable build identity. crawlers / verifiers can
    # fetch this without parsing site-metadata.json (which carries
    # editorial / identity content). Date-only timestamp keeps it
    # byte-stable across multiple builds within a single utc day.
    from datetime import UTC  # noqa: E402
    from datetime import datetime as _dt  # noqa: E402

    build_json = {
        "$schema": f"{base_url}/.well-known/build.json",
        "site": base_url,
        "edition": edition,
        "generated_at": _dt.now(UTC).strftime("%Y-%m-%d"),
        "static": True,
        "framework": None,
        "tracking": False,
        "trusted_types": True,
        "csp_strict": True,
        "signed_release": True,
        "source_mirrors": True,
        "language_model_assistance": "selective drafting or structuring only",
        "automated_publishing": False,
        "publication_policy": f"{base_url}/.well-known/publication.json",
        "integrity_manifest": f"{base_url}/integrity.json",
        "integrity_signature": f"{base_url}/integrity.json.sig",
        "public_key": f"{base_url}/.well-known/pgp-key.asc",
        "key_fingerprint": "A729 591B 450D 3F59 3694 98BD 8299 1F25 04AE 0263",
    }
    with open(".well-known/build.json", "w") as f:
        json.dump(build_json, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("  → .well-known/build.json")

    # ─── emit minified /styles.css + /print.css from tools/*.src.css ─────
    # tools/styles.src.css and tools/print.src.css are the readable source.
    # generate_site.py minifies them on every build and writes the deployed
    # bytes to public/. this keeps the operator-edited source clean while
    # the deployed bytes are render-path-friendly.

    for src_name, dst_name in (
        ("styles.src.css", "styles.css"),
        ("print.src.css", "print.css"),
        ("fonts-full.src.css", "fonts-full.css"),
    ):
        src_path = os.path.join(_REPO_ROOT, "styles", src_name)
        if not os.path.exists(src_path):
            print(f"  ⚠ {src_path} not found — {dst_name} not regenerated", file=sys.stderr)
            continue
        with open(src_path, encoding="utf-8") as f:
            css_src = f.read()
        css_min = minify_css(css_src)
        # calm public banner. survives minification because /*! ... */ is
        # a licence-class block. the integrity.json pointer is editorial,
        # not implementation detail — kept.
        header = (
            "/*! trentpower.fr · " + dst_name + " · generated · signed via /integrity.json */\n"
        )
        with open(dst_name, "w", encoding="utf-8") as f:
            f.write(header + css_min + "\n")
        saved = max(0, len(css_src) - len(css_min) - len(header))
        print(f"  → {dst_name} (minified from tools/{src_name}, saved {saved // 1024} KB)")

    # ─── generate /copy.js from copy.template.js ─────────────────
    # copy.template.js is the editable source; copy.js is the generator
    # output (minified, no substitution). the one shared copy-to-clipboard
    # behaviour — the cite overlay, verify pages and source reader all
    # defer to it.

    # first-party behaviour scripts are served from /js/ (documents and
    # behaviour kept in separate trees). sw.js + sw-register.js stay at the
    # web root because the service-worker scope is bound to the script path.
    os.makedirs("js", exist_ok=True)

    copy_template_path = os.path.join(TEMPLATES_DIR, "copy.template.js")
    copy_path = "js/copy.js"
    if os.path.exists(copy_template_path):
        with open(copy_template_path, encoding="utf-8") as f:
            copy_js = f.read()
        copy_js = minify_js(copy_js)
        copy_header = (
            "/*! trentpower.fr · /js/copy.js · generated · signed via /integrity.json */\n"
        )
        with open(copy_path, "w", encoding="utf-8") as f:
            f.write(copy_header + copy_js)
        print(f"  → {copy_path} (minified, from {copy_template_path})")
    else:
        print(f"  ⚠ {copy_template_path} not found — {copy_path} not generated", file=sys.stderr)

    # ─── generate /verify-modal.js from verify-modal.template.js ─────────
    # verify-modal.template.js is the editable source; verify-modal.js is the
    # generator output with the edition string substituted in. supersedes the
    # earlier cite.template.js → cite.js path (the verify action menu replaces
    # the old cite drawer; the dedicated /verify/ page now carries the record).

    verify_modal_template_path = os.path.join(TEMPLATES_DIR, "verify-modal.template.js")
    verify_modal_path = "js/verify-modal.js"
    if os.path.exists(verify_modal_template_path):
        with open(verify_modal_template_path) as f:
            verify_modal_js = f.read()
        verify_modal_js = re.sub(
            r"(var EDITION = ')[^']*(')", rf"\g<1>{edition}\2", verify_modal_js
        )
        verify_modal_js = minify_js(verify_modal_js)
        verify_modal_header = (
            "/*! trentpower.fr · /js/verify-modal.js · generated · signed via /integrity.json */\n"
        )
        with open(verify_modal_path, "w") as f:
            f.write(verify_modal_header + verify_modal_js)
        print(
            f"  → {verify_modal_path} (EDITION updated, minified, from {verify_modal_template_path})"
        )
    else:
        print(
            f"  ⚠ {verify_modal_template_path} not found — {verify_modal_path} not generated",
            file=sys.stderr,
        )

    # ─── generate /overlay.js + /fonts.js + /edition.js from templates ──────
    # behaviour-scoped post-paint modules: overlay.js carries the shared
    # overlay lifecycle (window.TP_OVERLAY) used by verify-modal.js + the project
    # modal; fonts.js does the post-lcp full-font upgrade; edition.js does
    # the footer relative-age localisation. all minified, no substitution
    # (edition.js reads body[data-edition] at runtime, so the same bytes
    # work for every page on every build).

    for _tname, _out in (
        ("overlay.template.js", "js/overlay.js"),
        ("fonts.template.js", "js/fonts.js"),
        ("edition.template.js", "js/edition.js"),
        ("micro-interactions.template.js", "js/micro-interactions.js"),
        # /local/ device console — diagnostics module.
        # progressive enhancement only; the page works
        # without it (static fields show fallback copy).
        ("local.template.js", "js/local.js"),
    ):
        _tpath = os.path.join(TEMPLATES_DIR, _tname)
        if os.path.exists(_tpath):
            with open(_tpath, encoding="utf-8") as f:
                _src = f.read()
            _min = minify_js(_src)
            _header = (
                f"/*! trentpower.fr · /{_out} · generated · "
                "loaded after first paint · signed via /integrity.json */\n"
            )
            with open(_out, "w", encoding="utf-8") as f:
                f.write(_header + _min)
            print(f"  → {_out} (minified, from {_tpath})")
        else:
            print(f"  ⚠ {_tpath} not found — {_out} not generated", file=sys.stderr)

    ACTIVE_HTML_FOR_EDITION = _discover_active_html()

    _html_changes = sum(1 for h in ACTIVE_HTML_FOR_EDITION if _sweep_edition_in_html(h, edition))
    _strings_changed = _sweep_edition_in_strings(I18N_STRINGS, edition, edition_dt)
    print(
        f"  → edition synced to {edition}: {_html_changes} HTML files, "
        f"{'i18n updated' if _strings_changed else 'i18n already current'}"
    )

    # ─── generate /js/theme.js, /sw-register.js, /js/reveal.js ───────────
    # the former app.js "brain" is split into behaviour-scoped modules:
    # theme.js (theme toggle + html.js/.enhanced flags), sw-register.js
    # (service-worker registration + the tp-app trusted types policy) and
    # reveal.js (scroll reveal). csp `script-src 'self'` authorises them.

    # remove superseded runtime-i18n artefacts so the source-mirror and
    # public-exposure gates do not flag them as unmirrored public files.
    for _stale in ("i18n-core.js", "i18n.js", "source/i18n-core.js.txt", "source/i18n.js.txt"):
        if os.path.exists(_stale):
            os.remove(_stale)
    if os.path.isdir("i18n"):
        import shutil as _rm_i18n

        _rm_i18n.rmtree("i18n")

    # theme.js + reveal.js move to /js/; sw-register.js stays at the web
    # root alongside sw.js (service-worker registration scope is path-bound).
    for _tname, _out in (
        ("theme.template.js", "js/theme.js"),
        ("sw-register.template.js", "sw-register.js"),
        ("reveal.template.js", "js/reveal.js"),
    ):
        _tpath = os.path.join(TEMPLATES_DIR, _tname)
        if os.path.exists(_tpath):
            with open(_tpath, encoding="utf-8") as f:
                _src = f.read()
            _min = minify_js(_src)
            _header = f"/*! trentpower.fr · /{_out} · generated · signed via /integrity.json */\n"
            with open(_out, "w", encoding="utf-8") as f:
                f.write(_header + _min)
            print(f"  → {_out} (minified, from {_tpath})")
        else:
            print(f"  ⚠ {_tpath} not found — {_out} not generated", file=sys.stderr)

    asset_version = _compute_asset_version(edition)
    print(f"  → asset_version: {asset_version}")
    # ─── runtime cache-bust for /fonts-full.css ──────────────────────────
    # /fonts-full.css is loaded after first paint by /js/fonts.js as a same-
    # origin <link rel='stylesheet'>. served unversioned it could carry no
    # immutable header (lighthouse flagged "Cache-Control: none").
    #
    # filename is stable; cache busting via query string only — matches every
    # other asset on the site (styles.css, print.css, js/verify-modal.js, …). the
    # /js/fonts.js literal is rewritten to embed ?v={asset_version} so a new
    # edition busts the cache without a new filename. fonts-full.css is in
    # ASSET_BUNDLE so any future HTML <link> to it is swept by
    # _sweep_asset_version_in_html() in the same shape.
    #
    # the legacy dated variant `fonts-full.<edition>.<hash>.css` is no longer
    # emitted here. any stale on-disk dated siblings are removed by
    # tools/prune_legacy_versioned_assets.py (one-time + recurring sweep);
    # a transitional 301 in .htaccess maps legacy URLs to the clean path.

    # /js/fonts.js loads /fonts-full.css?v={asset_version} so the stylesheet
    # is cache-busted per edition without changing the filename.
    _patch_js_literal("js/fonts.js", "'/fonts-full.css'", f"'/fonts-full.css?v={asset_version}'")

    # patch site-metadata.json with the asset version (the file was already
    # written above; an in-place patch keeps the schema stable and avoids
    # re-ordering the canonical generation pipeline).
    sm_path = "site-metadata.json"
    if os.path.exists(sm_path):
        with open(sm_path, encoding="utf-8") as fp:
            sm = json.load(fp)
        # asset_version is an operational field (sw cache key, ?v= sweeper).
        # asset_bundle was removed: integrity.json already lists every public
        # file, and ASSET_BUNDLE in this script remains the single source of
        # truth for cache-key hashing. site-metadata.json should describe the
        # publication, not the build inventory.
        sm["asset_version"] = asset_version
        with open(sm_path, "w", encoding="utf-8") as fp:
            json.dump(sm, fp, indent=2, ensure_ascii=False)
            fp.write("\n")

    _av_changes = sum(
        1 for h in ACTIVE_HTML_FOR_EDITION if _sweep_asset_version_in_html(h, asset_version)
    )
    print(f"  → asset version swept in {_av_changes} HTML files")

    # ─── generate /llms.txt ──────────────────────────────────────

    topics_lines = "\n".join(f"- {t.lower()}" for t in canon.get("topics", []))

    # build identity verification from all sameas + fixed endpoints
    identity_lines = []
    for sa in canon["sameAs"]:
        if host_matches(sa, "linkedin.com"):
            identity_lines.append(f"- linkedin: {sa}")
        elif host_matches(sa, "github.com"):
            identity_lines.append(f"- source repository (github): {sa}")
        elif host_matches(sa, "orcid.org"):
            identity_lines.append(f"- orcid: {sa}")
        elif host_matches(sa, "wikidata.org"):
            identity_lines.append(f"- wikidata: {sa}")
        elif host_matches(sa, "commons.wikimedia.org"):
            identity_lines.append(f"- portrait (wikimedia commons): {sa}")
        elif host_matches(sa, "crunchbase.com"):
            identity_lines.append(f"- crunchbase: {sa}")
        else:
            identity_lines.append(f"- {sa}")
    # identity_lines holds only external/wikimedia/orcid identity proofs;
    # the manifest / signature / key / publication-policy URLs moved to
    # dedicated "Integrity:" and "Records:" sections below to avoid
    # duplicating the verification handles inside this freeform list.
    identity_block = "\n".join(identity_lines)

    # french description + topic block for llms.txt. english topics come
    # from canon["topics"]; the canonical identity carries no chinese data.
    ka = person.get("knowsAbout", {})

    extra_desc_lines = ""
    if fr_description:
        extra_desc_lines += f"\ndescription (fr): {fr_description.lower()}"

    extra_topic_blocks = ""
    if isinstance(ka, dict) and "fr" in ka:
        extra_topic_blocks += "\nprimary topics (fr):\n" + "\n".join(
            f"- {_topic_name(t).lower()}" for t in ka["fr"]
        )

    # no alternate-name line: the canonical identity carries no transliterated name.
    alt_name_line = ""

    llms_txt = f"""# llms.txt — {domain}
# machine-readable identity summary for language models.
# canonical source: {base_url}/

Principle:
this site is designed first for human readers. machine-readable
files exist to preserve identity, authorship and context.

Site:
Name:               {person["name"].lower()}{alt_name_line.replace("alternate name", "Alternate Name")}
Domain:             {domain}
Role:               {job_title.lower()} at {works_for_name.lower()}
Location:           {person["addressLocality"].lower()}, {person["addressCountry"].lower()}
Description:        {description.lower()}{extra_desc_lines.replace("description (fr)", "Description (fr)").replace("description (zh)", "Description (zh)")}
Summary:            {entity_summary.lower()}

Primary Topics:
{topics_lines}{extra_topic_blocks.replace("primary topics (fr)", "Primary Topics (fr)").replace("primary topics (zh)", "Primary Topics (zh)")}

Records:
Site Metadata:       {base_url}/site-metadata.json
Structured Identity: {base_url}/.well-known/person.json
Publication Policy:  {base_url}/.well-known/publication.json
Attestations:        {base_url}/attestations.json
Security Policy:     {base_url}/.well-known/security.txt

Integrity:
Manifest:            {base_url}/integrity.json
Signature:           {base_url}/integrity.json.sig
Public Key:          {base_url}/.well-known/pgp-key.asc
Checksums:           {base_url}/SHA256SUMS

Identity Verification:
{identity_block}

Verify Pages:
- public verification route: {base_url}/verify/
- per-page verification: {base_url}/verify/?path=/<route>/

License:
content:  all rights reserved
portrait: https://creativecommons.org/licenses/by-sa/4.0/

Citation:
{citation.lower()}
"""

    with open("llms.txt", "w") as f:
        f.write(llms_txt)
    print("  → llms.txt")
    # ─── generate /sitemap.xml ───────────────────────────────────

    sitemap_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
        '        xmlns:xhtml="http://www.w3.org/1999/xhtml">',
    ]

    # the language gate at / — the x-default entry point. its hreflang
    # cluster points visitors at the two editions; the gate itself is
    # x-default. keys + paths derived from the route map so the cluster
    # stays in lockstep with the published URL segments.
    _gate_cluster = {
        _routes.lang_bcp47("en"): f"{base_url}{_routes.route_path('home', 'en')}",
        _routes.lang_bcp47("fr"): f"{base_url}{_routes.route_path('home', 'fr')}",
        "x-default": f"{base_url}/",
    }
    sitemap_lines += [
        "  <url>",
        f"    <loc>{base_url}/</loc>",
        *_hreflang_lines(_gate_cluster),
        f"    <lastmod>{get_lastmod('index.html', edition)}</lastmod>",
        "    <changefreq>monthly</changefreq>",
        "    <priority>0.5</priority>",
        "  </url>",
    ]
    sitemap_html_count = 1

    for route_key, (changefreq, default_priority) in SITEMAP_ROUTE_META.items():
        cluster = _routes.hreflang_cluster(route_key)
        overrides = SITEMAP_PRIORITY_OVERRIDES.get(route_key, {})
        for lang in _routes.languages():
            full_url = f"{base_url}{_routes.route_path(route_key, lang)}"
            lastmod = get_lastmod(_routes.route_output(route_key, lang), edition)
            priority = overrides.get(lang, default_priority)
            sitemap_lines += [
                "  <url>",
                f"    <loc>{full_url}</loc>",
                *_hreflang_lines(cluster),
                f"    <lastmod>{lastmod}</lastmod>",
                f"    <changefreq>{changefreq}</changefreq>",
                f"    <priority>{priority}</priority>",
                "  </url>",
            ]
            sitemap_html_count += 1

    for url_path, file_path in SITEMAP_ASSETS:
        lastmod = get_lastmod(file_path, edition)
        sitemap_lines += [
            "  <url>",
            f"    <loc>{base_url}{url_path}</loc>",
            f"    <lastmod>{lastmod}</lastmod>",
            "  </url>",
        ]

    sitemap_lines.append("</urlset>")
    sitemap_lines.append("")

    with open("sitemap.xml", "w") as f:
        f.write("\n".join(sitemap_lines))
    total_urls = sitemap_html_count + len(SITEMAP_ASSETS)
    print(f"  → sitemap.xml ({total_urls} URLs, {sitemap_html_count} with hreflang)")

    # ─── update index.html ───────────────────────────────────────
    # Propagates: description, person JSON-LD, website JSON-LD datemodified

    print()
    print("Updating HTML files...")

    with open("index.html") as f:
        html = f.read()

    # 1. meta description (root / uses the modest gate description, not
    #    the global identity description — keeps the gate from competing
    #    with the editions for ranking).
    html = re.sub(
        r'(<meta\s+name="description"\s+content=")[^"]*(")', rf"\g<1>{gate_description}\2", html
    )

    # 2. og:description (same modest framing on the gate)
    html = re.sub(
        r'(<meta\s+property="og:description"\s+content=")[^"]*(")',
        rf"\g<1>{gate_description}\2",
        html,
    )

    # 3. consolidated JSON-LD @graph (person + website + profilepage)
    #    the homepage exposes one machine-readable truth layer rather
    #    than three separate <script> blocks. Strategy:
    #      a. strip the consolidated comment + script pair (idempotent
    #         re-emit; matches what we wrote on the previous build).
    #      b. strip any orphan inline JSON-LD blocks left over from the
    #         pre-consolidation generators (Person/WebSite/ProfilePage
    #         in separate tags). the `<link rel="alternate"
    #         type="application/ld+json">` is a <link>, not a <script>,
    #         so it does not match.
    #      c. inject one fresh <script> block carrying the @graph
    #         immediately before </head>.
    html = re.sub(
        r"\s*<!--\s*[Ss]tructured data\s*[—\-]\s*single @graph[^\n]*-->\s*"
        r'<script type="application/ld\+json">\s*\{.*?</script>',
        "",
        html,
        flags=re.S,
    )
    # strip every legacy and orphan structured-data anchor. two
    # generations of comments need to go: the pre-consolidation
    # per-entity labels ("structured data · person", "structured
    # data · website", "structured data · profilepage" — middle dot),
    # any orphan "structured data — single @graph" comment that
    # survived the pair-strip above, and the lowercase "<!-- structured
    # data -->" anchors emitted by this generator on prior runs
    # (phase 19 onward — comment case matters because the previous
    # regex was case-sensitive and silently stacked one fresh marker
    # per build).
    html = re.sub(
        r"\s*<!--\s*(?:head\s*[·—\-]\s*)?[Ss]tructured data(?:\s*[·—\-][^\n]*)?\s*-->",
        "",
        html,
    )
    html = re.sub(
        r'\s*<script type="application/ld\+json">\s*\{.*?</script>',
        "",
        html,
        flags=re.S,
    )
    graph_block = (
        f"\n  <!-- head · structured data -->\n"
        f'  <script type="application/ld+json">\n{gate_graph_inline}\n  </script>\n\n'
    )
    html = html.replace("</head>", graph_block + "</head>", 1)
    # collapse any run of 2+ blank lines that the inject may have produced
    # back to a single blank line. keeps the deployed <head> visually
    # regular regardless of incoming whitespace.
    html = re.sub(r"\n{3,}", "\n\n", html)

    # 5. og:locale:alternate (fr_FR only) , insert/update after og:locale line
    html = re.sub(
        r'(<meta property="og:locale" content="en_AU">)(\n\s*<meta property="og:locale:alternate"[^\n]*)*',
        '<meta property="og:locale" content="en_AU">\n  <meta property="og:locale:alternate" content="fr_FR">',
        html,
    )

    # 6. faq structured data. strip any prior faq blocks first
    #    (idempotent), then inject fresh ones only if faq.json exists.
    html = re.sub(
        r"\n+  <!--\s*[Ss]tructured data — [Ff][Aa][Qq].*?</script>", "", html, flags=re.DOTALL
    )

    if os.path.exists("faq.json"):
        faq_injection = ""
        with open("faq.json") as fq:
            faq_raw = fq.read()
        # extract json objects from <script type="application/ld+json"> blocks
        faq_script_bodies = []
        for part in faq_raw.split("</script>"):
            marker = '<script type="application/ld+json">'
            if marker in part:
                json_str = part.split(marker, 1)[1].strip()
                if json_str:
                    try:
                        faq_script_bodies.append(json.loads(json_str))
                    except json.JSONDecodeError as exc:
                        print(f"  WARNING: Could not parse FAQ block: {exc}", file=sys.stderr)
        for block_data in faq_script_bodies:
            lang = block_data.get("inLanguage", "")
            lang_label = f" ({lang.upper()})" if lang else ""
            pretty = json.dumps(block_data, ensure_ascii=False, indent=2)
            faq_injection += f'\n\n  <!-- structured data — faq{lang_label.lower()} -->\n  <script type="application/ld+json">\n{pretty}\n  </script>'
        # inject before </head>
        html = html.replace("</head>", faq_injection + "\n</head>")
        # collapse any run of 3+ newlines between structured data blocks to exactly 2 (1 blank line)
        html = re.sub(r"(</script>)\n{3,}(  <!--\s*[Ss]tructured data)", r"\1\n\n\2", html)

    with open("index.html", "w") as f:
        f.write(html)
    print("  ✓ index.html (description, Person JSON-LD, WebSite JSON-LD, og:locale:alternate, FAQ)")

    # ─── update document-edition in all html files ───────────────

    # build rel="me" links from sameas
    rel_me_lines = "\n".join(f'  <link rel="me" href="{sa}">' for sa in canon["sameAs"])

    for filepath in HTML_FILES:
        if not os.path.exists(filepath):
            print(f"  ⚠ {filepath} not found, skipping")
            continue
        with open(filepath) as f:
            content = f.read()

        # update document-edition
        updated = re.sub(
            r'(<meta\s+name="document-edition"\s+content=")[^"]*(")', rf"\g<1>{edition}\2", content
        )

        # replace all consecutive rel="me" links with current sameas
        updated = re.sub(r'(  <link rel="me" href="[^"]*">\n)+', rel_me_lines + "\n", updated)

        if updated != content:
            with open(filepath, "w") as f:
                f.write(updated)
    print(f"  ✓ document-edition → {edition} (all {len(HTML_FILES)} HTML files)")
    print(f'  ✓ rel="me" → {len(canon["sameAs"])} links (all {len(HTML_FILES)} HTML files)')

    # ─── update integrity/index.html review date ─────────────────

    integrity_path = "integrity/index.html"
    if os.path.exists(integrity_path):
        with open(integrity_path) as f:
            content = f.read()
        updated = re.sub(
            r"(Last reviewed:\s*)\d{1,2}\s+\w+\s+\d{4}", rf"\g<1>{edition_human}", content
        )
        if updated != content:
            with open(integrity_path, "w") as f:
                f.write(updated)
        print(f"  ✓ integrity/index.html → Last reviewed: {edition_human}")

    # ─── update humans.txt review date ───────────────────────────

    humans_path = "humans.txt"
    if os.path.exists(humans_path):
        with open(humans_path) as f:
            content = f.read()
        # case-insensitive so a "last reviewed:" (lowercase l, matching the
        # rest of humans.txt's prose voice) is swept on every edition bump.
        # the previous capital-L pattern silently skipped a real lowercase
        # line in the file — the review date drifted stale across editions.
        updated = re.sub(r"((?i:last reviewed):\s*)\d{4}-\d{2}-\d{2}", rf"\g<1>{edition}", content)
        if updated != content:
            with open(humans_path, "w") as f:
                f.write(updated)
        print(f"  ✓ humans.txt → Last reviewed: {edition}")

    # ─── .htaccess CSP hashes ────────────────────────────────────
    # owned by tools/generate_htaccess.py since the 2026-05-19 refactor.
    # the generator reads tools/htaccess_config.py (single source of truth
    # for CSP_INLINE_HASHES_GLOBAL + CSP_INLINE_HASHES_SOURCE_VIEW_DELTA)
    # and rewrites both CSP headers inside the BEGIN/END CSP markers.
    # run `python3 tools/generate_htaccess.py` after editing the hashes.

    # ─── summary ─────────────────────────────────────────────────

    print()
    print(f"Generated from {CANONICAL_FILE}")
    print(f"  Name:        {person['name']}")
    print(f"  Edition:     {edition}")
    print(f"  Description: {description[:60]}...")
    print(f"  Citation:    {citation}")
    print(f"  sameAs:      {len(canon['sameAs'])} links")
    print()
    print("Next steps:")
    print("  1. python3 generate_sw.py")
    print("  2. python3 generate_integrity.py")
    print("  3. unset GNUPGHOME")
    print("  4. gpg --detach-sign --armor -o integrity.json.sig integrity.json")
    print("  5. Upload all changed files via SFTP")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
