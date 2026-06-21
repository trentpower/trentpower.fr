#!/usr/bin/env python3
"""Tests for tools/lib/htaccess_config.py — the .htaccess CSP + rule builder.

The module is pure (it only imports the routes lib), so these tests assert
behaviour and invariants of the rendered CSP headers and the rule families
rather than touching disk or the network.
"""

import re
import unittest

import _fixture  # noqa: E402

_fixture.bootstrap()

import htaccess_config as hc  # noqa: E402
import routes as _routes  # noqa: E402


class CspRender(unittest.TestCase):
    def test_global_has_core_directives(self):
        # the global header must lock everything down by default and carry
        # the directives that the wire format has been shipping.
        csp = hc.csp_global()
        for directive in (
            "default-src 'none'",
            "upgrade-insecure-requests",
            "script-src 'self'",
            "script-src-attr 'none'",
            "style-src 'self'",
            "style-src-attr 'none'",
            "font-src 'self'",
            "frame-ancestors 'none'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'none'",
            "require-trusted-types-for 'script'",
        ):
            self.assertIn(directive, csp)

    def test_global_carries_global_script_hashes_and_policy(self):
        # every owned inline-script hash is authorised, and the trusted-types
        # policy name comes from TRUSTED_TYPES_GLOBAL.
        csp = hc.csp_global()
        for h, _label in hc.CSP_INLINE_HASHES_GLOBAL:
            self.assertIn(f"'{h}'", csp)
        self.assertIn("trusted-types tp-app", csp)

    def test_global_omits_source_view_delta(self):
        # the source-reader-only hashes and policy must NOT leak into global.
        csp = hc.csp_global()
        delta_hash = hc.CSP_INLINE_HASHES_SOURCE_VIEW_DELTA[0][0]
        self.assertNotIn(delta_hash, csp)
        self.assertNotIn("tp-source-view", csp)

    def test_source_view_extends_global(self):
        # source-view authorises everything global does plus the reader delta.
        glob = hc.csp_global()
        sv = hc.csp_source_view()
        self.assertNotEqual(glob, sv)
        for h, _ in hc.CSP_INLINE_HASHES_GLOBAL:
            self.assertIn(f"'{h}'", sv)
        # the reader bootstrap hash and inline-style hash appear only here.
        self.assertIn(f"'{hc.CSP_INLINE_HASHES_SOURCE_VIEW_DELTA[0][0]}'", sv)
        self.assertIn(f"'{hc.CSP_INLINE_STYLE_HASHES_SOURCE_VIEW_DELTA[0][0]}'", sv)

    def test_source_view_widens_trusted_types(self):
        sv = hc.csp_source_view()
        self.assertIn("trusted-types tp-app tp-source-view", sv)

    def test_source_view_style_src_includes_style_hash(self):
        # globally style-src is bare 'self'; source-view adds the empty-style
        # hash so source-view.template.js can mutate the cssom.
        glob = hc.csp_global()
        sv = hc.csp_source_view()
        style_hash = hc.CSP_INLINE_STYLE_HASHES_SOURCE_VIEW_DELTA[0][0]
        glob_style = re.search(r"style-src ([^;]*);", glob).group(1)
        sv_style = re.search(r"style-src ([^;]*);", sv).group(1)
        self.assertEqual(glob_style.strip(), "'self'")
        self.assertIn(style_hash, sv_style)

    def test_service_worker_is_strict(self):
        sw = hc.csp_service_worker()
        self.assertEqual(sw, hc._CSP_SW_TEMPLATE)
        self.assertIn("default-src 'none'", sw)
        self.assertIn("script-src 'self'", sw)
        self.assertIn("base-uri 'none'", sw)
        # no trusted-types / style machinery on the worker header.
        self.assertNotIn("trusted-types", sw)
        self.assertNotIn("style-src", sw)

    def test_render_helper_formats_hashes_and_policies(self):
        # exercise _render directly with a tiny template so the formatting
        # contract (quoted hashes, space-joined policies) is pinned.
        out = hc._render(
            "s={script_src}|t={style_src}|tt={trusted_types}",
            [("sha256-AAA", "a")],
            [("sha256-BBB", "b")],
            ["p1", "p2"],
        )
        self.assertEqual(out, "s='self' 'sha256-AAA'|t='self' 'sha256-BBB'|tt=p1 p2")

    def test_render_with_empty_hash_lists(self):
        out = hc._render("{script_src}|{style_src}|{trusted_types}", [], [], ["only"])
        self.assertEqual(out, "'self'|'self'|only")


class BilingualRouteRules(unittest.TestCase):
    def setUp(self):
        self.rules = hc._bilingual_route_allow_rules()

    def test_non_empty_and_well_formed(self):
        self.assertTrue(self.rules)
        for rule in self.rules:
            # each rule must be a compilable, anchored regex string.
            self.assertIsInstance(rule, str)
            re.compile(rule)
            self.assertTrue(rule.startswith("^"))

    def test_covers_both_language_trees(self):
        # the home route in both languages must appear as a directory rule.
        for lang in _routes.languages():
            slug = _routes.route_path("home", lang).strip("/")
            self.assertIn(rf"^{re.escape(slug)}/?$", self.rules)
        # both language segments anchor their own rules.
        self.assertIn(r"^en\-au/?$", self.rules)
        self.assertIn(r"^fr/?$", self.rules)

    def test_every_route_has_dir_and_index_rule(self):
        for key in _routes.route_keys():
            for lang in _routes.languages():
                slug = _routes.route_path(key, lang).strip("/")
                esc = re.escape(slug)
                self.assertIn(rf"^{esc}/?$", self.rules)
                self.assertIn(rf"^{esc}/index\.html$", self.rules)

    def test_per_language_error_documents(self):
        for lang in _routes.languages():
            seg = re.escape(_routes.lang_url_segment(lang))
            self.assertIn(rf"^{seg}/(403|404|500|maintenance)\.html$", self.rules)

    def test_neutral_surfaces_present(self):
        # gate-neutral surfaces that are not route-map entries.
        for neutral in (r"^local/?$", r"^source/?$", r"^source/view/?$"):
            self.assertIn(neutral, self.rules)

    def test_source_view_index_matches_reader_app(self):
        pat = next(r for r in self.rules if r == r"^source/view/index\.html$")
        self.assertRegex("source/view/index.html", pat)


class LegacyRedirects(unittest.TestCase):
    def test_lang_redirect_family(self):
        rules = hc._legacy_lang_redirect_rules()
        seg = _routes.lang_url_segment("en")
        self.assertIn((r"^en/?$", f"/{seg}/"), rules)
        # the catch-all preserves the captured path via the apache backref.
        self.assertIn((r"^en/(.*)$", f"/{seg}/$1"), rules)

    def test_legacy_redirect_maps_old_to_new(self):
        rules = hc._legacy_redirect_rules()
        self.assertTrue(rules)
        for pattern, target in rules:
            re.compile(pattern)
            self.assertTrue(pattern.startswith("^"))
            self.assertTrue(target.startswith("/"))
        # a known single-tree path 301s to its /en-au/ edition.
        targets = {t for _, t in rules}
        self.assertIn("/en-au/privacy/", targets)

    def test_kept_live_paths_are_not_redirected(self):
        # /source/ and /source/view/ stay served even though routes.yml
        # lists them; they must be excluded from the legacy redirects.
        rules = hc._legacy_redirect_rules()
        for pattern, _ in rules:
            self.assertNotRegex("source", pattern)
            self.assertNotRegex("source/view", pattern)
        # sanity: the keep-live set is actually present in the source data.
        for keep in hc._LEGACY_REDIRECT_KEEP_LIVE:
            self.assertIn(keep, _routes.legacy_redirects())

    def test_rename_redirect_rules_point_at_local(self):
        for pattern, target in hc._RENAME_REDIRECT_RULES:
            re.compile(pattern)
            self.assertEqual(target, "/local/")
        # the bare /sw-reset/ and its index both redirect.
        patterns = {p for p, _ in hc._RENAME_REDIRECT_RULES}
        self.assertIn(r"^sw-reset/?$", patterns)

    def test_combined_order_lang_then_legacy_then_rename(self):
        combined = hc.LEGACY_REDIRECT_RULES
        lang = hc._legacy_lang_redirect_rules()
        rename = hc._RENAME_REDIRECT_RULES
        # the /en/ cut-over rules come first, the renames last.
        self.assertEqual(combined[: len(lang)], lang)
        self.assertEqual(combined[-len(rename):], rename)

    def test_versioned_asset_redirects_match_dated_shapes(self):
        rules = hc.LEGACY_VERSIONED_ASSET_REDIRECTS
        font_pat, font_target = rules[0]
        self.assertEqual(font_target, "/fonts-full.css")
        self.assertRegex("fonts-full.2026-02-01.abc123.css", font_pat)
        self.assertNotRegex("fonts-full.css", font_pat)
        verify_pat, verify_target = rules[1]
        self.assertEqual(verify_target, "/verify/verification-data.js")
        self.assertRegex(
            "verify/verification-data.2026-02-01.deadbeef.js", verify_pat
        )


class DenyRules(unittest.TestCase):
    def _match_any(self, rules, candidate):
        return any(re.search(p, candidate) for p in rules)

    def test_path_rules_block_secrets_and_lockfiles(self):
        for blocked in (
            ".git/config",
            ".github/workflows/ci.yml",
            ".env",
            ".env.production",
            ".user.ini",
            ".htpasswd",
            "id_ed25519",
            "id_ed25519.pub",
            "identity_canonical.json",
            "composer.json",
            "composer.lock",
            "package.json",
            "package-lock.json",
            "yarn.lock",
            "pnpm-lock.yaml",
            "sub/dir/.git/HEAD",
        ):
            self.assertTrue(
                self._match_any(hc.DENY_PATH_RULES, blocked),
                f"{blocked} should be denied",
            )

    def test_path_rules_allow_ordinary_files(self):
        for ok in ("index.html", "styles.css", "images/og/card.png"):
            self.assertFalse(self._match_any(hc.DENY_PATH_RULES, ok))

    def test_extension_rules_block_code_and_config(self):
        for blocked in (
            "shell.php",
            "x.phar",
            "page.phtml",
            "run.py",
            "cache.pyc",
            "deploy.sh",
            "lib.so",
            "config.yaml",
            "data.yml",
            "notes.md",
            "db.sqlite",
            "build.log",
            "home.template.js",
            "invoice-2026.pdf",
            "my-key.txt",
        ):
            self.assertTrue(
                self._match_any(hc.DENY_EXTENSION_RULES, blocked),
                f"{blocked} should be denied",
            )

    def test_extension_rules_allow_public_assets(self):
        for ok in ("app.js", "styles.css", "card.png", "logo.svg", "font.woff2"):
            self.assertFalse(self._match_any(hc.DENY_EXTENSION_RULES, ok))

    def test_directory_rules_block_build_and_source_trees(self):
        for blocked in (
            "node_modules/x",
            "vendor/lib.php",
            "private/",
            "src/main.py",
            "tools/build.sh",
            "docs/readme",
            "_archives/old.zip",
            "console_data/log",
            "reports/r.json",
        ):
            self.assertTrue(
                self._match_any(hc.DENY_DIRECTORY_RULES, blocked),
                f"{blocked} should be denied",
            )

    def test_directory_rules_only_match_at_root(self):
        # these are root-anchored, so a nested 'src' segment is allowed.
        self.assertFalse(self._match_any(hc.DENY_DIRECTORY_RULES, "images/src/x.svg"))


class PrivatePatterns(unittest.TestCase):
    def test_dotfile_glob_matches_dotfiles(self):
        self.assertRegex(".env", hc.PRIVATE_DOTFILE_GLOB)
        self.assertRegex(".htpasswd", hc.PRIVATE_DOTFILE_GLOB)
        self.assertNotRegex("index.html", hc.PRIVATE_DOTFILE_GLOB)

    def test_ops_extensions_match_operational_files(self):
        for blocked in ("notes.md", "run.py", "db.sqlite", "config.yaml", "data.yml"):
            self.assertRegex(blocked, hc.PRIVATE_OPS_EXTENSIONS)
        self.assertNotRegex("app.js", hc.PRIVATE_OPS_EXTENSIONS)

    def test_basenames_match_lockfiles_and_secrets(self):
        for blocked in (
            ".user.ini",
            ".env",
            ".htpasswd",
            "composer.json",
            "composer.lock",
            "package.json",
            "package-lock.json",
            "yarn.lock",
            "pnpm-lock.yaml",
        ):
            self.assertRegex(blocked, hc.PRIVATE_BASENAMES)
        self.assertNotRegex("index.html", hc.PRIVATE_BASENAMES)

    def test_name_patterns_match_sensitive_words_case_insensitive(self):
        for blocked in ("Invoice", "credential", "LICENSE", "licence", "secret"):
            self.assertRegex(blocked, hc.PRIVATE_NAME_PATTERNS)
        self.assertNotRegex("about", hc.PRIVATE_NAME_PATTERNS)


class AllowFamilies(unittest.TestCase):
    def test_families_well_formed(self):
        # each family is (heading, [pattern, ...]); patterns must compile.
        self.assertTrue(hc.ALLOW_RULE_FAMILIES)
        for heading, patterns in hc.ALLOW_RULE_FAMILIES:
            self.assertIsInstance(heading, str)
            self.assertTrue(patterns)
            for p in patterns:
                re.compile(p)

    def test_bilingual_family_embeds_route_rules(self):
        # the public-routes family is built from _bilingual_route_allow_rules.
        family = dict(hc.ALLOW_RULE_FAMILIES)
        bilingual_heading = next(
            h for h, _ in hc.ALLOW_RULE_FAMILIES if "bilingual" in h
        )
        self.assertEqual(
            family[bilingual_heading], hc._bilingual_route_allow_rules()
        )

    def test_root_and_error_pages_match(self):
        family = dict(hc.ALLOW_RULE_FAMILIES)
        patterns = family["root + error pages"]
        self.assertTrue(any(re.fullmatch(p, "") for p in patterns))
        self.assertTrue(any(re.fullmatch(p, "index.html") for p in patterns))
        self.assertTrue(any(re.fullmatch(p, "404.html") for p in patterns))

    def test_forward_look_keys_exist_in_families(self):
        all_patterns = {
            p for _, pats in hc.ALLOW_RULE_FAMILIES for p in pats
        }
        for key in hc.ALLOW_RULE_FORWARD_LOOK:
            self.assertIn(key, all_patterns)


class CompressMime(unittest.TestCase):
    def test_includes_text_and_structured_types(self):
        types = hc.COMPRESS_MIME_TYPES
        for mime in (
            "text/html",
            "text/css",
            "application/javascript",
            "application/json",
            "application/ld+json",
            "image/svg+xml",
            "text/plain",
        ):
            self.assertIn(mime, types)

    def test_is_space_joined_single_line(self):
        self.assertNotIn("\n", hc.COMPRESS_MIME_TYPES)
        self.assertGreater(len(hc.COMPRESS_MIME_TYPES.split(" ")), 5)


if __name__ == "__main__":
    unittest.main()
