#!/usr/bin/env python3
"""Property-based (fuzz) tests over the build tooling's parser surfaces.

Hypothesis drives arbitrary inputs through the {{ }} token engine, the
slug helper, the locale date renderer and the badge SVG generator, and
asserts the invariants each one promises: escaping is total, failures
are always the declared error type, slugs are idempotent, and generated
SVG stays well-formed XML. See docs/fuzzing.md for scope and rationale.
"""

import html
import pathlib
import re
import sys
import unittest

# parses only SVG produced in-process by colophon_svg — never untrusted
# input — so the stdlib parser's XXE surface is not reachable here.
import xml.etree.ElementTree as ET
from datetime import date

from hypothesis import given, settings
from hypothesis import strategies as st

_TOOLS = pathlib.Path(__file__).resolve().parents[2]
for _sub in ("lib", "build", "quality", "verify", "release", "badges"):
    sys.path.insert(0, str(_TOOLS / _sub))

from dates import human_date  # noqa: E402
from generate_badges import colophon_svg, esc  # noqa: E402
from render_pages import RenderError, substitute  # noqa: E402
from slugs import i18n_slug  # noqa: E402

# CI runners and the local build machine are slow enough that the default
# per-example deadline produces flaky timing failures; the property still
# runs the full example budget.
settings.register_profile("ci", deadline=None)
settings.load_profile("ci")

# text that cannot itself open a new {{ token }}, so a single substitution
# pass is also the fixed point.
_TOKEN_FREE = st.text(max_size=200).filter(lambda s: "{{" not in s)

# the documented contract: lowercased alphanumerics (unicode included),
# runs of everything else collapsed to single underscores, edges trimmed.
_SLUG_SHAPE = re.compile(r"^(?:[^\W_]+)(?:_[^\W_]+)*$")


class TokenEngineProperties(unittest.TestCase):
    @given(_TOKEN_FREE)
    def test_plain_token_escapes_totally(self, value):
        out = substitute("<p>{{ v }}</p>", {"v": value})
        body = out[len("<p>") : -len("</p>")]
        self.assertNotIn("<", body)
        self.assertNotIn(">", body)
        self.assertEqual(html.unescape(body), value)

    @given(st.text(max_size=200))
    def test_arbitrary_template_raises_only_rendererror(self, template):
        try:
            substitute(template, {})
        except RenderError:
            pass  # the declared failure mode: unresolved or malformed tokens

    @given(_TOKEN_FREE)
    def test_attr_token_safe_inside_quoted_attribute(self, value):
        out = substitute('<a title="{{ attr:v }}">x</a>', {"v": value})
        # the attribute value must not be able to close the quote or the tag
        inner = out[len('<a title="') : out.index('">x</a>')]
        self.assertNotIn('"', inner)
        self.assertNotIn("<", inner)


class SlugProperties(unittest.TestCase):
    @given(st.text(max_size=200))
    def test_idempotent(self, name):
        once = i18n_slug(name)
        self.assertEqual(i18n_slug(once), once)

    @given(st.text(max_size=200))
    def test_shape(self, name):
        slug = i18n_slug(name)
        if slug:
            self.assertRegex(slug, _SLUG_SHAPE)
            self.assertEqual(slug, slug.lower())


class DateProperties(unittest.TestCase):
    @given(
        st.dates(min_value=date(1, 1, 1), max_value=date(9999, 12, 31)),
        st.sampled_from(["en", "fr"]),
    )
    def test_canonical_string_round_trip(self, d, lang):
        rendered = human_date(d.isoformat(), lang=lang)
        self.assertIn(str(d.year), rendered)
        self.assertIn(str(d.day), rendered.split()[0])


class BadgeSvgProperties(unittest.TestCase):
    @given(st.text(max_size=100))
    def test_esc_neutralises_markup(self, text):
        out = esc(text)
        self.assertNotIn("<", out)
        self.assertNotIn(">", out)
        self.assertNotIn('"', out)
        # esc drops XML-invalid C0 controls; everything else round-trips
        kept = "".join(ch for ch in text if ch >= " " or ch in "\t\n")
        self.assertEqual(html.unescape(out), kept)

    @given(st.text(max_size=60), st.text(max_size=60))
    def test_svg_stays_well_formed(self, label, value):
        svg = colophon_svg(label, value)
        root = ET.fromstring(svg)
        self.assertTrue(root.tag.endswith("svg"))


if __name__ == "__main__":
    unittest.main()
