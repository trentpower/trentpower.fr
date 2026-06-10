#!/usr/bin/env python3
"""tools/lib/routes.py — bilingual route map helper.

Single point of resolution for the /en/ and /fr/ URL architecture. Loads
content/shared/routes.yml and exposes the queries every downstream tool
needs:

    load_routes()                  -> the parsed route map (cached)
    languages()                    -> ["en", "fr"]
    base_url()                     -> "https://trentpower.fr"
    route_keys()                   -> bilingual route keys, in file order
    route_slug(key, lang)          -> "confidentialite"        (no slashes added)
    route_path(key, lang)          -> "/fr/confidentialite/"   (absolute, on-site)
    route_url(key, lang)           -> "https://trentpower.fr/fr/confidentialite/"
    route_output(key, lang)        -> "fr/confidentialite/index.html" (under public/)
    counterpart_path(key, lang)    -> the other language's route_path
    hreflang_cluster(key)          -> {"en": url, "fr": url, "x-default": url}
    route_for_file(rel_path)       -> (key, lang) | None  (reverse lookup)
    legacy_redirects()             -> {old_path: new_path}

The renderer, sitemap, .htaccess generator, service-worker generator and the
SEO validators all consume this module so the route surface is defined exactly
once.

Run directly for a self-check:
    python3 tools/lib/routes.py
"""

from __future__ import annotations

import re
import sys
from functools import lru_cache

try:
    import yaml
except ImportError:  # pragma: no cover
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
from paths import ROUTES_YML  # noqa: E402


@lru_cache(maxsize=1)
def load_routes() -> dict:
    """Parse content/shared/routes.yml. Cached for the process lifetime."""
    if not ROUTES_YML.exists():
        raise FileNotFoundError(f"route map not found: {ROUTES_YML}")
    with ROUTES_YML.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    _validate(data)
    return data


# a slug is either empty (the home/index route) or a /-joined path whose every
# segment is lowercase letters, digits and hyphens. this is an allowlist: it
# rejects path traversal ("..", "../../etc/passwd"), absolute/leading-slash
# slugs, backslashes, whitespace and uppercase before any of them can reach a
# generated path, canonical url or the public file tree.
_SLUG_SEGMENT = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _check_slug(key: str, lang: str, slug: object) -> None:
    if not isinstance(slug, str):
        raise ValueError(f"routes.yml: route '{key}' slug for '{lang}' must be a string")
    if slug == "":
        return  # the home / index route
    if slug != slug.strip() or "\\" in slug or slug.startswith("/") or slug.endswith("/"):
        raise ValueError(f"routes.yml: route '{key}' slug for '{lang}' is malformed: {slug!r}")
    for seg in slug.split("/"):
        if not _SLUG_SEGMENT.match(seg):
            raise ValueError(
                f"routes.yml: route '{key}' slug for '{lang}' has an unsafe segment {seg!r} "
                "(allowed: lowercase letters, digits, hyphens; no traversal, no absolute paths)"
            )


def _validate(data: dict) -> None:
    """Fail loud on a malformed route map — every consumer depends on it."""
    for top in ("site", "routes", "error_routes", "root_routes", "legacy_redirects"):
        if top not in data:
            raise ValueError(f"routes.yml: missing top-level key '{top}'")
    langs = data["site"].get("languages")
    if not langs or not isinstance(langs, list):
        raise ValueError("routes.yml: site.languages must be a non-empty list")
    if data["site"].get("default_language") not in langs:
        raise ValueError("routes.yml: site.default_language must be one of site.languages")
    for key, spec in data["routes"].items():
        slug = spec.get("slug")
        if not isinstance(slug, dict):
            raise ValueError(f"routes.yml: route '{key}' has no slug map")
        for lang in langs:
            if lang not in slug:
                raise ValueError(f"routes.yml: route '{key}' missing slug for '{lang}'")
            _check_slug(key, lang, slug[lang])


def languages() -> list[str]:
    return list(load_routes()["site"]["languages"])


# three orthogonal axes for an internal language key:
#   url segment   — the URL path component (lowercase, per RFC 3986 advice)
#   BCP47 tag     — the <html lang>, hreflang, and JSON-LD inLanguage tag
#   og:locale     — open graph spec syntax (xx_YY, always)
#
# the english edition publishes as australian English: /en-au/, lang="en-AU",
# og:locale="en_AU". french stays plain `fr` deliberately — the region tag
# only carries meaning where it disambiguates, and there is no fr-CA
# rendering. og:locale stays fr_FR because the OG spec requires xx_YY.
LANG_URL_SEGMENT = {"en": "en-au", "fr": "fr"}
LANG_BCP47 = {"en": "en-AU", "fr": "fr"}
LANG_OG_LOCALE = {"en": "en_AU", "fr": "fr_FR"}


def lang_url_segment(lang: str) -> str:
    return LANG_URL_SEGMENT.get(lang, lang)


def lang_bcp47(lang: str) -> str:
    return LANG_BCP47.get(lang, lang)


def lang_og_locale(lang: str) -> str:
    return LANG_OG_LOCALE.get(lang, lang)


def default_language() -> str:
    return load_routes()["site"]["default_language"]


def base_url() -> str:
    return load_routes()["site"]["base_url"].rstrip("/")


def route_keys() -> list[str]:
    """Bilingual route keys, in routes.yml declaration order."""
    return list(load_routes()["routes"].keys())


def _route(key: str) -> dict:
    routes = load_routes()["routes"]
    if key not in routes:
        raise KeyError(f"unknown route key: {key!r}")
    return routes[key]


def template_name(key: str) -> str:
    return _route(key)["template"]


def route_slug(key: str, lang: str) -> str:
    """The raw slug for a route in a language — no leading/trailing slashes."""
    slug = _route(key)["slug"].get(lang)
    if slug is None:
        raise KeyError(f"route {key!r} has no slug for language {lang!r}")
    return slug.strip("/")


def route_path(key: str, lang: str) -> str:
    """Absolute on-site path, e.g. '/fr/confidentialite/' or '/en-au/' for home.

    The URL segment is derived via lang_url_segment(lang) so the English
    edition publishes under /en-au/ while staying keyed by the internal
    `en` lang code everywhere else (content/, data-lang, localStorage).
    """
    slug = route_slug(key, lang)
    seg = lang_url_segment(lang)
    if slug:
        return f"/{seg}/{slug}/"
    return f"/{seg}/"


def route_url(key: str, lang: str) -> str:
    """Fully-qualified canonical URL for a route in a language."""
    return base_url() + route_path(key, lang)


def route_output(key: str, lang: str) -> str:
    """Path of the rendered file, relative to public/."""
    return route_path(key, lang).lstrip("/") + "index.html"


def counterpart_path(key: str, lang: str) -> str:
    """The route_path of the same page in the *other* language."""
    others = [other for other in languages() if other != lang]
    if len(others) != 1:
        raise ValueError("counterpart_path assumes exactly two languages")
    return route_path(key, others[0])


def hreflang_cluster(key: str) -> dict[str, str]:
    """The full hreflang cluster for a route: every language + x-default.

    Keys are BCP47 tags (en-AU, fr) — what the emitted hreflang attribute
    actually carries — not internal language keys. x-default points at the
    root language gate ('/'), per the SEO strategy.
    """
    cluster = {lang_bcp47(lang): route_url(key, lang) for lang in languages()}
    cluster["x-default"] = base_url() + "/"
    return cluster


@lru_cache(maxsize=1)
def _file_index() -> dict[str, tuple[str, str]]:
    """Map every rendered public/ file path -> (route key, lang)."""
    index: dict[str, tuple[str, str]] = {}
    for key in route_keys():
        for lang in languages():
            index[route_output(key, lang)] = (key, lang)
    return index


def route_for_file(rel_path: str) -> tuple[str, str] | None:
    """Reverse lookup: a public/-relative file path -> (route key, lang).

    Returns None for non-bilingual surfaces (root gate, sw-reset, error pages).
    """
    return _file_index().get(rel_path.lstrip("/"))


def legacy_redirects() -> dict[str, str]:
    """Old single-tree path -> new /en/ path (permanent 301, one hop)."""
    return dict(load_routes()["legacy_redirects"])


def _self_check() -> int:
    """Print a resolved view of the route map and assert internal consistency."""
    load_routes()  # parse-validity check: raises if routes.yml is malformed
    langs = languages()
    print(f"base_url           : {base_url()}")
    print(f"languages          : {langs}")
    print(f"default_language   : {default_language()}")
    print(f"bilingual routes   : {len(route_keys())}")
    print()
    width = max(len(k) for k in route_keys())
    for key in route_keys():
        cells = "  ".join(f"{lang}:{route_path(key, lang)}" for lang in langs)
        print(f"  {key.ljust(width)}  {cells}")
        # round-trip: every rendered file resolves back to its (key, lang)
        for lang in langs:
            rt = route_for_file(route_output(key, lang))
            assert rt == (key, lang), f"round-trip failed for {key}/{lang}: {rt}"
    print()
    print(f"legacy redirects   : {len(legacy_redirects())}")
    en_seg = lang_url_segment("en")
    for old, new in legacy_redirects().items():
        print(f"  {old}  ->  {new}")
        assert new.startswith(f"/{en_seg}/"), f"legacy redirect target not /{en_seg}/: {new}"
    print()
    print("self-check OK")
    return 0


if __name__ == "__main__":
    sys.exit(_self_check())
