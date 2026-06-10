#!/usr/bin/env python3
"""render_pages.py — bilingual static page renderer (phase B).

Renders the clean {{ }} templates in templates/pages/ against the editorial
copy in content/<lang>/ to produce the static /en/ and /fr/ editions.

Token grammar (templates/pages/*.html):
    {{ dotted.key }}        text value, HTML-escaped on insert
    {{ html:dotted.key }}   markup value, inserted raw
    {{ list:dotted.key }}   list/newline value rendered as <li>…</li> items (raw)
    {{ attr:dotted.key }}   attribute value, attribute-escaped on insert
    {{ shared.dotted.key }} any of the above may reach into shared.yml

The merged context for a (page, lang) is content/<lang>/shared.yml spread at
top level, plus a `shared` alias, plus the page YAML's surfaces. Values may
themselves contain {{ shared.* }} references (the content/en alias system);
substitution iterates to a fixed point.

This phase covers token substitution and writes to a scratch directory for
structural verification. Wiring into build.sh, link rewriting, canonical /
hreflang injection and partial includes land in phases B/C.

Usage:
    python3 tools/render_pages.py                 # render to .build/render/
    python3 tools/render_pages.py --out DIR       # render to DIR
    python3 tools/render_pages.py --page privacy  # one route only
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("error: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

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
from paths import CONTENT_DIR, IDENTITY_CANONICAL, REPO_ROOT, TEMPLATES_DIR, TMP_DIR  # noqa: E402

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
import routes as routemap  # noqa: E402

PAGES_DIR = TEMPLATES_DIR / "pages"
MAX_PASSES = 6

# route key -> content/<lang>/pages/<file>.yml stem. routes whose copy lives
# in the bundled system.yml share that source.
PAGE_YAML = {
    "home": "home",
    "privacy": "privacy",
    "security": "security",
    "security-acknowledgments": "security",
    "integrity": "integrity",
    "integrity-releases": "integrity",
    "integrity-verify-locally": "verify",
    "verify": "verify",
    "source": "source",
    "source-view": "source",
    "403": "system",
    "404": "system",
    "500": "system",
    "maintenance": "system",
    # /local/ — single-edition english diagnostic surface. replaces
    # the legacy /sw-reset/ page; .htaccess 301-redirects /sw-reset/
    # to /local/, and the SW precache list now carries /local/ in
    # /sw-reset/'s place. content lives in its own pages/local.yml.
    "local": "local",
}


class RenderError(Exception):
    pass


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise RenderError(f"missing content file: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def build_context(lang: str, page_yaml: str) -> dict:
    """Merged substitution context for a (lang, page).

    Adds an ``edition.date`` token (today's UTC date in ISO form) so
    templates can paint the canonical build date without hand-edited
    YAML. Same formula as tools/generate_verification_map.py so the
    stamp, the verification map, and verify.js's "Validated YYYY-MM-DD"
    all agree on a given build."""
    shared = _load_yaml(CONTENT_DIR / lang / "shared.yml")
    page = _load_yaml(CONTENT_DIR / lang / "pages" / f"{page_yaml}.yml")
    page = {k: v for k, v in page.items() if k != "translation"}
    ctx: dict = {}
    ctx.update(shared)
    ctx["shared"] = shared
    ctx.update(page)
    ctx["edition"] = {"date": datetime.datetime.now(datetime.UTC).date().isoformat()}
    return ctx


def _resolve(key: str, ctx: dict) -> object:
    cur: object = ctx
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise RenderError(f"unresolved token: {{{{ {key} }}}}")
        cur = cur[part]
    return cur


def _render_list(value: object, key: str) -> str:
    """Render a {{ list:* }} value. Lists render one <li> per element; a
    newline-delimited string renders one <li> per non-empty line (the form
    the runtime data-i18n-list renderer consumed)."""
    if isinstance(value, str):
        items = [ln for ln in value.split("\n") if ln.strip()]
    elif isinstance(value, list):
        items = value
    else:
        raise RenderError(f"{{{{ list:{key} }}}} did not resolve to a list or string")
    return "".join(f"<li>{item}</li>" for item in items)


def _esc_text(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _esc_attr(s: str) -> str:
    return _esc_text(s).replace('"', "&quot;")


def substitute(html: str, ctx: dict) -> str:
    """Replace every {{ token }} in `html`, iterating to a fixed point so that
    {{ shared.* }} references inside resolved values are also expanded.

    Content YAML values are stored unescaped; text/attribute tokens are
    escaped for their insertion context, html/list tokens inserted raw."""
    import re

    token_re = re.compile(r"\{\{\s*(html:|list:|attr:|url:)?([a-zA-Z0-9_.\-]+)\s*\}\}")

    def one(m: re.Match) -> str:
        kind, key = m.group(1), m.group(2)
        value = _resolve(key, ctx)
        if kind == "list:":
            return _render_list(value, key)
        if not isinstance(value, str):
            raise RenderError(f"{{{{ {key} }}}} resolved to {type(value).__name__}, not a string")
        if kind == "attr:":
            return _esc_attr(value)
        if kind == "url:":
            # url-encode for query-string / mailto-subject contexts. nu html
            # checker rejects bare spaces and non-ascii inside href, so any
            # yaml value with em-dashes, apostrophes or spaces needs this
            # mode rather than {{ attr: }} (which only html-escapes).
            from urllib.parse import quote

            return quote(value, safe="")
        result = value if kind == "html:" else _esc_text(value)
        # a multi-line value (authored as a YAML literal block) keeps its
        # wrapping in the rendered source: continuation lines are indented
        # to the token's own column so the paragraph reads as one tidy
        # block. HTML collapses the whitespace, so the page is byte-for-byte
        # identical to a browser and to every machine reader.
        if "\n" in result:
            line_start = html.rfind("\n", 0, m.start()) + 1
            prefix = html[line_start : m.start()]
            indent = prefix if not prefix.strip() else " " * (len(prefix) - len(prefix.lstrip()))
            result = result.replace("\n", "\n" + indent)
        return result

    for _ in range(MAX_PASSES):
        new = token_re.sub(one, html)
        if new == html:
            return new
        html = new
    raise RenderError("token substitution did not converge (cyclic {{ }} reference?)")


# route key -> meta.* key in content/<lang>/pages/<yaml>.yml
META_KEY = {
    "home": "home",
    "privacy": "privacy",
    "security": "security",
    "security-acknowledgments": "acknowledgments",
    "integrity": "integrity",
    "integrity-releases": "releases",
    "integrity-verify-locally": "verify_locally",
    "verify": "verify",
    "source": "source",
    "source-view": "source",
    "403": "403",
    "404": "404",
    "500": "500",
    "maintenance": "maintenance",
}
OG_LOCALE = {"en": "en_AU", "fr": "fr_FR"}

# canonical identity — feeds the per-language homepage JSON-LD. the gate
# graph (generate_site.py) carries english; the bilingual editions are
# localised here from the same single source of truth.
_CANON: dict | None = None


def _load_canon() -> dict:
    global _CANON
    if _CANON is None:
        _CANON = json.loads(IDENTITY_CANONICAL.read_text(encoding="utf-8"))
    return _CANON


# editorial definition of clienteling, per language. the english copy is
# also held in generate_site.py for the gate graph; the french rendering
# is authored here for the /fr/ edition.
_CLIENTELING_DESC = {
    "en": (
        "Clienteling is the disciplined practice of transforming "
        "what a Client Advisor knows into something a Client feels. The "
        "moment interactions become mechanical, it stops being Clienteling."
    ),
    "fr": (
        "Le clienteling est la pratique disciplinée qui transforme "
        "ce qu’un Conseiller Client sait en quelque chose qu’un Client "
        "ressent. Dès que les interactions deviennent mécaniques, ce "
        "n’est plus du clienteling."
    ),
}
_DEFINITIONS_SET_NAME = {
    "en": "Definitions used on trentpower.fr",
    "fr": "Définitions utilisées sur trentpower.fr",
}
# homepage section names for the ProfilePage hasPart entries, per edition.
_PROFILE_PART_NAMES = {
    "en": {"approach": "Approach", "trajectory": "Trajectory", "contact": "Contact"},
    "fr": {"approach": "Approche", "trajectory": "Parcours", "contact": "Contact"},
}


def _localise_homepage_jsonld(html: str, lang: str) -> str:
    """Rewrite the homepage JSON-LD @graph so each edition exposes its own
    language's machine data. The cross-edition entity @id anchors (Person,
    WebSite, ProfilePage) stay site-rooted so the graph reads as one
    entity; the clienteling DefinedTerm @id is localised, because that
    term is defined on the per-language homepage, not at the root."""
    import re

    m = re.search(
        r'(<script type="application/ld\+json">)(.*?)(</script>)',
        html,
        re.S,
    )
    if not m:
        return html
    try:
        data = json.loads(m.group(2))
    except json.JSONDecodeError:
        return html
    base = routemap.base_url()
    seg = routemap.lang_url_segment(lang)
    tag = routemap.lang_bcp47(lang)
    person = _load_canon()["person"]
    clienteling_url = f"{base}/{seg}/#clienteling-definition"

    for node in data.get("@graph", []):
        node_type = node.get("@type")
        if node_type == "Person":
            if lang != "en":
                node["jobTitle"] = person["jobTitle"][lang]
                node["description"] = person["entity_summary"][lang]
                node["disambiguatingDescription"] = person["description"][lang]
                node["knowsAbout"] = person["knowsAbout"][lang]
            for item in node.get("knowsAbout", []):
                if isinstance(item, dict) and item.get("@type") == "DefinedTerm":
                    item["@id"] = clienteling_url
                    item["url"] = clienteling_url
            # mainEntityOfPage follows the per-edition ProfilePage @id
            # (see ProfilePage branch below).
            mep = node.get("mainEntityOfPage")
            if isinstance(mep, dict) and mep.get("@id"):
                mep["@id"] = f"{base}/{seg}/#profile-page"
        elif node_type == "WebSite":
            # one website, one stable @id — one canonical url at the
            # site root (not a language subdirectory). inLanguage stays
            # as the array carried from the template (["en-AU","fr"]);
            # the website is a global entity, not a page entity, so it
            # is NOT rewritten to a per-edition single tag.
            node["url"] = f"{base}/"
            if lang != "en":
                node["description"] = person["description"][lang]
        elif node_type == "ProfilePage":
            # /en-au/ and /fr/ are genuinely different pages — each is its
            # own ProfilePage entity, so the @id is per-edition (the
            # cross-edition Person/WebSite/ImageObject @ids stay rooted).
            node["@id"] = f"{base}/{seg}/#profile-page"
            node["url"] = f"{base}/{seg}/"
            node["inLanguage"] = tag
            # the section entries live on this per-edition page, so each
            # hasPart @id moves into the language tree; names localise too.
            for part in node.get("hasPart", []):
                pid = part.get("@id", "")
                if "#" in pid:
                    frag = pid.split("#", 1)[1]
                    part["@id"] = f"{base}/{seg}/#{frag}"
                    localised = _PROFILE_PART_NAMES.get(lang, {}).get(frag)
                    if localised:
                        part["name"] = localised
        elif node_type == "DefinedTerm":
            # the clienteling definition lives on the localized homepage
            # (<dfn id="clienteling-definition"> on /en-au/ and /fr/), so
            # its @id moves with it — the root / is the language vestibule
            # and no longer carries the anchor. @id and url stay in lockstep.
            node["@id"] = clienteling_url
            node["url"] = clienteling_url
            node["description"] = _CLIENTELING_DESC.get(lang, _CLIENTELING_DESC["en"])
            term_set = node.get("inDefinedTermSet")
            if isinstance(term_set, dict):
                # one definitions set, one stable @id → one root url.
                term_set["url"] = f"{base}/"
                term_set["name"] = _DEFINITIONS_SET_NAME.get(lang, _DEFINITIONS_SET_NAME["en"])

    new_json = "\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n  "
    return html[: m.start(2)] + new_json + html[m.end(2) :]


def _legacy_path_map() -> dict:
    """Single-tree path (as it appears in the extracted templates) -> route key."""

    out = {}
    for key in routemap.route_keys():
        en_slug = routemap.route_slug(key, "en")
        out["/" + en_slug + "/" if en_slug else "/"] = key
    return out


def _rewrite_links(html: str, lang: str) -> str:
    """Rewrite internal single-tree links to the language tree via routes.yml.
    Leaves files, archive paths and the root-level /sw-reset/ untouched."""
    import re

    legacy = _legacy_path_map()

    def repl(m):
        path, suffix = m.group(1), m.group(2) or ""
        key = legacy.get(path)
        if key is None:
            return m.group(0)
        return f'href="{routemap.route_path(key, lang)}{suffix}"'

    return re.sub(r'href="(/[^"#?]*?/?)([#?][^"]*)?"', repl, html)


def _rewrite_source_registry(html: str, lang: str) -> str:
    """Rewrite the source-page mirror registry into the language tree.

    The source.html template carries a hand-authored registry that
    links each trust page's plain-text mirror and its source-reader
    deep link. The mirror of a page now lives under the language tree
    (/source/en/privacy/index.html.txt, /source/fr/confidentialite/…),
    so each edition's registry must point at its own tree. Asset
    mirrors (app.js.txt, …) and root-error mirrors stay language-
    neutral and are left untouched.
    """
    for key in routemap.route_keys():
        en_slug = routemap.route_slug(key, "en")
        if not en_slug:
            continue  # home — its mirror is the neutral gate
        out_lang = routemap.route_output(key, lang)
        html = html.replace(
            f'href="/source/{en_slug}/index.html.txt"',
            f'href="/source/{out_lang}.txt"',
        )
        old_q = "%2F" + en_slug.replace("/", "%2F") + "%2F"
        new_q = routemap.route_path(key, lang).replace("/", "%2F")
        html = html.replace(f'?path={old_q}"', f'?path={new_q}"')
    return html


def _rewrite_lang_switcher(html: str, route_key: str, lang: str) -> str:
    """Footer language switcher: the runtime <button data-lang> controls
    become static <a href> links to each edition of the current page. The
    current edition is marked aria-current; no JavaScript involved."""
    import re

    if route_key not in routemap.route_keys():
        return html

    def repl(m: re.Match) -> str:
        target, attrs, text = m.group(1), m.group(2), m.group(3)
        attrs = re.sub(r'\s*aria-pressed="(?:true|false)"', "", attrs)
        current = ' aria-current="page"' if target == lang else ""
        href = routemap.route_path(route_key, target)
        return f'<a href="{href}"{attrs}{current}>{text}</a>'

    return re.sub(
        r'<button type="button" data-lang="(en|fr)"([^>]*?)>([^<]*)</button>',
        repl,
        html,
    )


def _split_hero_lines(inner_html: str) -> str:
    """Wrap each <br>-separated line of a hero-statement's inner HTML in
    <span class="hero-line">…</span>, joined by literal <br>. Drives the
    per-line settle on direct edition arrivals (gate v2 motion brief).
    <mark> stays inside its line span — the YAML sources never cross
    <mark> over <br>, so a flat split on <br> is safe.

    Phase 96 · the per-element style="--line-index: N;" attribute was
    a CSP style-src-attr violation. styles.src.css now carries a six-
    rule general-sibling chain (.hero-line ~ .hero-line { --line-index:
    1; } …) so the index is derived from sibling position at zero
    runtime cost.

    Idempotent: if the inner already contains .hero-line spans, return
    unchanged (so calling this twice does not nest)."""
    import re

    if 'class="hero-line"' in inner_html:
        return inner_html
    parts = re.split(r"<br\s*/?>", inner_html, flags=re.IGNORECASE)
    wrapped = []
    for raw in parts:
        seg = raw.strip()
        if not seg:
            continue
        wrapped.append(f'<span class="hero-line">{seg}</span>')
    return "<br>".join(wrapped)


def _apply_hero_line_settle(html: str) -> str:
    """Apply _split_hero_lines() to the inner of every hero-statement
    element in the rendered HTML — covers both the single-language home
    page's <h1 class="hero-statement..."> and the gate background's
    bilingual <p class="hero-statement..."> wrapping data-gate spans.
    In the bilingual case the <span data-gate> wrappers are themselves
    wrapped — each side carries its own per-line indices. The outer
    regex matches the hero-statement element shell; the inner walker
    handles data-gate spans if present."""
    import re

    def _wrap_data_gate_spans(inner: str) -> str:
        """If the inner contains <span data-gate="…">…</span> pairs,
        wrap the contents of each independently. Otherwise wrap the
        whole inner once."""
        pattern = re.compile(
            r'(<span data-gate="(?:en|fr)">)(.*?)(</span>)',
            re.DOTALL,
        )
        if pattern.search(inner):
            return pattern.sub(
                lambda m: m.group(1) + _split_hero_lines(m.group(2)) + m.group(3),
                inner,
            )
        return _split_hero_lines(inner)

    return re.sub(
        r'(<(?:h1|p) class="hero-statement[^"]*"[^>]*>)(.*?)(</(?:h1|p)>)',
        lambda m: m.group(1) + _wrap_data_gate_spans(m.group(2)) + m.group(3),
        html,
        flags=re.DOTALL,
    )


def postprocess(html: str, route_key: str, lang: str) -> str:
    """Phase B SEO/locale corrections: <html lang>, canonical, hreflang,
    og:url/locale, JSON-LD inLanguage, internal-link rewriting, and the
    per-language <title>/description from the meta YAML."""
    import re

    base = routemap.base_url()

    html = re.sub(
        r'<html lang="[a-zA-Z-]+"', f'<html lang="{routemap.lang_bcp47(lang)}"', html, count=1
    )

    # bilingual routes carry self-canonical + an hreflang cluster. error /
    # maintenance pages are per-tree flat files — no canonical rewrite.
    if route_key in routemap.route_keys():
        old_canonical = base + (
            "/" + routemap.route_slug(route_key, "en") + "/"
            if routemap.route_slug(route_key, "en")
            else "/"
        )
        new_canonical = base + routemap.route_path(route_key, lang)
        # rewrite the page URL (followed by " or ?) into the localised
        # tree. a fragment ('#') is deliberately NOT rewritten: the
        # JSON-LD entity @id values (#trent-power, #website,
        # #profile-page, …) are canonical, language-neutral identifiers
        # and must stay site-rooted so the graph stays one entity.
        html = re.sub(re.escape(old_canonical) + r'(?=["?])', new_canonical, html)

        cluster = routemap.hreflang_cluster(route_key)
        links = "\n".join(
            f'  <link rel="alternate" hreflang="{hl}" href="{url}">' for hl, url in cluster.items()
        )
        html = re.sub(
            r'(  <link rel="canonical"[^>]*>)',
            lambda m: m.group(1) + "\n" + links,
            html,
            count=1,
        )

    html = re.sub(
        r'(<meta property="og:locale" content=")[^"]*(">)',
        rf"\g<1>{OG_LOCALE[lang]}\g<2>",
        html,
        count=1,
    )
    # drop any alternate-locale tags carried by the template, then emit
    # exactly one per other language so neither edition duplicates a tag.
    html = re.sub(r'\n\s*<meta property="og:locale:alternate"[^>]*>', "", html)
    others = [other for other in routemap.languages() if other != lang]
    alt = "".join(
        f'\n  <meta property="og:locale:alternate" content="{OG_LOCALE[o]}">' for o in others
    )
    html = re.sub(
        r'(<meta property="og:locale" content="[^"]*">)', lambda m: m.group(1) + alt, html, count=1
    )

    html = re.sub(
        r'"inLanguage":\s*"[a-zA-Z-]+"', f'"inLanguage": "{routemap.lang_bcp47(lang)}"', html
    )
    html = _rewrite_links(html, lang)
    html = _rewrite_source_registry(html, lang)
    html = _rewrite_lang_switcher(html, route_key, lang)

    meta_key = META_KEY.get(route_key)
    if meta_key:
        page = _load_yaml(CONTENT_DIR / lang / "pages" / f"{PAGE_YAML[route_key]}.yml")
        meta = page.get("meta", {}).get(meta_key, {})
        title, desc = meta.get("title"), meta.get("description")
        if title:
            t = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            ta = t.replace('"', "&quot;")
            html = re.sub(
                r"<title>.*?</title>", f"<title>{t}</title>", html, count=1, flags=re.DOTALL
            )
            html = re.sub(
                r'(<meta property="og:title" content=").*?(">)',
                lambda m: m.group(1) + ta + m.group(2),
                html,
                count=1,
                flags=re.DOTALL,
            )
            # og:image:alt tracks the localised title (no-op where absent).
            html = re.sub(
                r'(<meta property="og:image:alt" content=").*?(">)',
                lambda m: m.group(1) + ta + m.group(2),
                html,
                count=1,
                flags=re.DOTALL,
            )
        if desc:
            da = (
                desc.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
            )
            html = re.sub(
                r'(<meta name="description"\s+content=").*?(">)',
                lambda m: m.group(1) + da + m.group(2),
                html,
                count=1,
                flags=re.DOTALL,
            )
            html = re.sub(
                r'(<meta property="og:description" content=").*?(">)',
                lambda m: m.group(1) + da + m.group(2),
                html,
                count=1,
                flags=re.DOTALL,
            )

    # provenance links — the citation anchor follows the page itself; the
    # policy links follow the language tree. all three are no-ops on pages
    # without the provenance head section.
    if route_key in routemap.route_keys():
        cite_url = base + routemap.route_path(route_key, lang)
    else:
        cite_url = f"{base}/{lang}/{route_key}.html"
    html = re.sub(
        r'(<link rel="cite-as" href=")[^"]*(">)',
        lambda m: m.group(1) + cite_url + m.group(2),
        html,
        count=1,
    )
    html = re.sub(
        r'(<link rel="privacy-policy" href=")[^"]*(">)',
        lambda m: m.group(1) + base + routemap.route_path("privacy", lang) + m.group(2),
        html,
        count=1,
    )
    html = re.sub(
        r'(<link rel="help" href=")[^"]*(">)',
        lambda m: m.group(1) + base + routemap.route_path("security", lang) + m.group(2),
        html,
        count=1,
    )

    if route_key == "home":
        html = _localise_homepage_jsonld(html, lang)
        # gate v2 · wrap each <br>-separated line of the hero statement in
        # <span class="hero-line"> so the per-line settle animates on direct
        # edition arrivals. /en-au/ and /fr/ both get this; the gate's own
        # bilingual hero is wrapped separately in _bilingual_hero().
        html = _apply_hero_line_settle(html)
    return html


# cached shared-yml loads · keyed by lang. used by the construction
# rail injector below, which has to resolve the "construction_rail.label"
# string for each edition without rebuilding a full page context.
_SHARED_CACHE: dict[str, dict] = {}


def _shared_for(lang: str) -> dict:
    if lang not in _SHARED_CACHE:
        _SHARED_CACHE[lang] = _load_yaml(CONTENT_DIR / lang / "shared.yml")
    return _SHARED_CACHE[lang]


def _render_construction_rail(lang: str, *, bilingual: bool = False) -> str:
    """The global "under construction" rail. Pinned to viewport bottom
    by CSS (.construction-rail, position: fixed); rendered once per
    page just before </body>. Decorative, aria-hidden, no focusable
    elements — see the construction-rail CSS block in styles.src.css.

    For the language vestibule (root /) the rail carries both labels
    as bilingual [data-gate] spans, matching the gate's other dual-
    language strings. For every other page (en-au, fr, error pages,
    /local/, source viewer, …) the rail carries that page's single
    edition label resolved from content/<lang>/shared.yml."""
    if bilingual:
        en_label = _shared_for("en").get("construction_rail", {}).get("label", "Under Construction")
        fr_label = _shared_for("fr").get("construction_rail", {}).get("label", "En Construction")
        label_inner = (
            f'<span data-gate="en">{_esc_text(en_label)}</span>'
            f'<span data-gate="fr">{_esc_text(fr_label)}</span>'
        )
    else:
        label = _shared_for(lang).get("construction_rail", {}).get("label", "Under Construction")
        label_inner = _esc_text(label)
    return (
        "\n<!-- body · construction rail -->\n"
        '<div class="construction-rail" data-construction-rail aria-hidden="true">\n'
        '  <span class="construction-rail__stripe" aria-hidden="true"></span>\n'
        '  <span class="construction-rail__label">\n'
        '    <span class="construction-rail__dot" aria-hidden="true"></span>\n'
        f"    {label_inner}\n"
        "  </span>\n"
        '  <span class="construction-rail__stripe" aria-hidden="true"></span>\n'
        "</div>\n"
    )


def _inject_construction_rail(html: str, lang: str, *, bilingual: bool = False) -> str:
    """Splice the rail markup in just before </body>. Idempotent: if
    the marker [data-construction-rail] is already present (e.g. a
    page authored an inline rail before the global injector existed)
    the call is a no-op so we never double-render."""
    if "data-construction-rail" in html:
        return html
    rail = _render_construction_rail(lang, bilingual=bilingual)
    if "</body>" not in html:
        # never expected, but a malformed page should not crash the
        # build — append the rail at the end and let validate_html
        # surface the missing </body> closure.
        return html + rail
    return html.replace("</body>", rail + "</body>", 1)


def render_page(route_key: str, lang: str) -> str:
    template = PAGES_DIR / f"{route_key}.html"
    if not template.exists():
        raise RenderError(f"missing template: {template}")
    ctx = build_context(lang, PAGE_YAML[route_key])
    html = substitute(template.read_text(encoding="utf-8"), ctx)
    html = postprocess(html, route_key, lang)
    return _inject_construction_rail(html, lang, bilingual=False)


# stable HTML-comment markers in templates/pages/home.html that bound the
# masthead-through-hero region. the gate background is sliced between them,
# so a homepage edit that drops a marker fails the build loudly rather than
# silently emitting an empty vestibule.
_GATE_SLICE_START = "<!-- body · masthead -->"
_GATE_SLICE_END = "<!-- primary · 02 · approach -->"


def _slice_home_masthead_hero(home_html: str) -> str:
    """Cut the masthead-through-hero region out of the rendered homepage.
    The slice leaves <main>/<article> open; the caller closes them."""
    start = home_html.find(_GATE_SLICE_START)
    end = home_html.find(_GATE_SLICE_END)
    if start == -1 or end == -1:
        raise RenderError(
            "language gate: masthead/hero markers not found in the rendered "
            "homepage — has templates/pages/home.html changed?"
        )
    return home_html[start:end]


def _neutralise_gate_background(slice_html: str) -> str:
    """Make the homepage slice safe to embed in the vestibule: it is
    aria-hidden and inert, must emit no second h-card identity graph, and
    must not duplicate element ids."""
    import re

    # drop the hidden microformat h-card block
    slice_html = re.sub(r"\s*<div hidden>.*?</div>", "", slice_html, flags=re.S)
    # drop the visually-hidden masthead description (referenced by an
    # aria-describedby that is removed just below)
    slice_html = re.sub(
        r'\s*<span class="visually-hidden"[^>]*>.*?</span>',
        "",
        slice_html,
        flags=re.S,
    )
    # strip ids and the now-dangling aria-describedby / aria-labelledby
    # (both reference ids removed just above)
    slice_html = re.sub(r'\s+id="[^"]*"', "", slice_html)
    slice_html = re.sub(r'\s+aria-describedby="[^"]*"', "", slice_html)
    slice_html = re.sub(r'\s+aria-labelledby="[^"]*"', "", slice_html)
    # demote the home-profile <article> landmark to a plain <div>: the
    # slice is aria-hidden and inert decoration, and its only heading (the
    # hero <h1>) is demoted to <p> below — an article without a heading is
    # an a11y/html flag, and this block is not a real article anyway. the
    # closing tag is appended as </div> by render_gate().
    slice_html = re.sub(r'<article(\s+class="home-profile)', r"<div\1", slice_html, count=1)
    # drop microformat class tokens so the gate carries no second h-card
    for cls in ("h-card", "p-name", "u-url", "u-uid", "p-note"):
        slice_html = re.sub(rf'\s+{cls}(?=[\s"])', "", slice_html)
    return slice_html


def _bilingual_hero(slice_html: str, ctx_en: dict, ctx_fr: dict) -> str:
    """Replace the hero statement/body inner content with bilingual
    data-gate spans, so the vestibule background follows the visitor's
    stored language exactly as the choice card's copy does."""
    import re

    def pair(en_val: str, fr_val: str) -> str:
        return f'<span data-gate="en">{en_val}</span><span data-gate="fr">{fr_val}</span>'

    # hero.statement is markup (raw); hero.body is text (escaped on insert)
    # gate v2 · wrap each <br>-separated line of the statement in
    # <span class="hero-line"> per-language. each side carries its own
    # 0-based --line-index sequence, so when CSS reveals the active
    # language via [data-gate], the indices read 0,1,2,3 not 4,5,6,7.
    statement = pair(
        _split_hero_lines(_resolve("hero.statement", ctx_en)),
        _split_hero_lines(_resolve("hero.statement", ctx_fr)),
    )
    body = pair(_esc_text(_resolve("hero.body", ctx_en)), _esc_text(_resolve("hero.body", ctx_fr)))

    # demote the hero <h1> to <p>: the gate background is aria-hidden,
    # so a real heading there would hide from assistive tech (same class,
    # same paint — the choice card keeps the page's only real <h1>).
    slice_html = re.sub(
        r'<h1 class="(hero-statement[^"]*)"[^>]*>.*?</h1>',
        lambda m: f'<p class="{m.group(1)}">{statement}</p>',
        slice_html,
        count=1,
        flags=re.S,
    )
    slice_html = re.sub(
        r'(<p class="hero-body">).*?(</p>)',
        lambda m: m.group(1) + body + m.group(2),
        slice_html,
        count=1,
        flags=re.S,
    )
    return slice_html


def render_gate() -> str:
    """Render the root / language gate. The background is the real
    homepage: the masthead + hero are sliced out of the rendered homepage
    build (substitution only — no per-edition SEO) and injected, so / and
    /en/ are one composition. Bilingual copy from content/shared/gate.yml;
    canonical/hreflang are static in the template (lang-neutral)."""
    template = PAGES_DIR / "language-gate.html"
    if not template.exists():
        raise RenderError(f"missing template: {template}")

    home_template = PAGES_DIR / "home.html"
    if not home_template.exists():
        raise RenderError(f"missing template: {home_template}")
    ctx_en = build_context("en", "home")
    ctx_fr = build_context("fr", "home")
    home_html = substitute(home_template.read_text(encoding="utf-8"), ctx_en)

    background = _slice_home_masthead_hero(home_html)
    background = _neutralise_gate_background(background)
    background = _bilingual_hero(background, ctx_en, ctx_fr)
    background = background.rstrip() + "\n    </div>\n  </main>\n"

    ctx = _load_yaml(CONTENT_DIR / "shared" / "gate.yml")
    ctx["gate_background"] = background
    gate_html = substitute(template.read_text(encoding="utf-8"), ctx)
    # bilingual rail — root / shows the gate to first visitors; the
    # rail's label carries both editions' phrasing via [data-gate]
    # spans so the visible label tracks the gate's other dual-language
    # strings as the visitor's stored language preference resolves.
    return _inject_construction_rail(gate_html, "en", bilingual=True)


def main() -> int:
    argv = sys.argv[1:]
    out_dir = REPO_ROOT / TMP_DIR / "render"
    only = None
    if "--out" in argv:
        out_dir = Path(argv[argv.index("--out") + 1]).resolve()
    if "--page" in argv:
        only = argv[argv.index("--page") + 1]

    bilingual = [k for k in routemap.route_keys()]
    error_root = ["403", "404", "500", "maintenance"]
    # single-edition routes — language-neutral, english copy only.
    # render_page() would fail trying to load content/fr/pages/<x>.yml,
    # so skip the second-language iteration entirely.
    english_only = {"local"}
    fails = 0
    written = 0

    for route_key in PAGE_YAML:
        if only and route_key != only:
            continue
        for lang in routemap.languages():
            if route_key in english_only and lang != "en":
                continue
            try:
                html = render_page(route_key, lang)
            except RenderError as exc:
                print(f"  ✗ {lang}/{route_key}: {exc}", file=sys.stderr)
                fails += 1
                continue
            if route_key in [k for k in bilingual]:
                rel = routemap.route_output(route_key, lang)
            elif route_key in error_root:
                rel = f"{routemap.lang_url_segment(lang)}/{route_key}.html"
            else:  # local — single english diagnostic page
                if lang != "en":
                    continue
                # the route key is the directory slug under /
                rel = f"{route_key}/index.html"
            dest = out_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(html, encoding="utf-8")
            written += 1
            print(f"  ✓ {rel}")

            # root-level error pages are the gate-path fallback for a
            # request that matches neither /en/ nor /fr/. emit the
            # english edition's bytes at the root so the fallback has
            # tree-correct links instead of stale single-tree ones.
            if route_key in error_root and lang == "en":
                (out_dir / f"{route_key}.html").write_text(html, encoding="utf-8")
                written += 1
                print(f"  ✓ {route_key}.html (root fallback)")

    # root language gate + its behaviour script
    if not only or only in ("gate", "language-gate"):
        try:
            gate_html = render_gate()
            (out_dir / "index.html").write_text(gate_html, encoding="utf-8")
            written += 1
            print("  ✓ index.html (language gate)")
            gate_js = TEMPLATES_DIR / "language-gate.template.js"
            if gate_js.exists():
                gate_out = out_dir / "js" / "language-gate.js"
                gate_out.parent.mkdir(parents=True, exist_ok=True)
                # phase 96 · minify alongside every other generated js
                # so the gate script ships ~half the on-the-wire bytes.
                # the authored source stays in templates/language-gate.template.js
                # (and mirrors at /source/language-gate.js.txt — see
                # source-mirror map) for readable security review.
                src_text = gate_js.read_text(encoding="utf-8")
                try:
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
                    from minify import minify_js  # type: ignore

                    min_text = minify_js(src_text)
                    header = (
                        "/*! trentpower.fr · /js/language-gate.js · "
                        "generated · signed via /integrity.json */\n"
                    )
                    gate_out.write_text(header + min_text, encoding="utf-8")
                except Exception as exc:  # noqa: BLE001
                    # if the minifier is unavailable in this venv, fall
                    # back to the authored source so the build doesn't
                    # fail; just print a warning.
                    print(
                        f"  warn: language-gate minify failed ({exc}); shipping authored source",
                        file=sys.stderr,
                    )
                    gate_out.write_text(src_text, encoding="utf-8")
                written += 1
                print("  ✓ js/language-gate.js")
        except RenderError as exc:
            print(f"  ✗ language gate: {exc}", file=sys.stderr)
            fails += 1

    print(f"\n{written} file(s) -> {out_dir}")
    if fails:
        print(f"✗ {fails} render failure(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
