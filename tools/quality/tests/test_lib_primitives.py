#!/usr/bin/env python3
"""Tests for the canonical tools/lib helpers: hashing, dates, slugs, sizes."""

import datetime
import pathlib
import sys
import tempfile
import unittest

_TOOLS = pathlib.Path(__file__).resolve().parents[2]
for _sub in ("lib", "build", "quality", "verify", "release"):
    sys.path.insert(0, str(_TOOLS / _sub))

from dates import LOCALE_MONTHS, human_date  # noqa: E402
from hashing import sha256_b64, sha256_file_hex, sha256_hex, sri_sha256  # noqa: E402
from sizes import humanise_bytes  # noqa: E402
from slugs import i18n_slug  # noqa: E402

# sha-256 of b"abc" — the classic FIPS 180 test vector.
ABC_HEX = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
ABC_B64 = "ungWv48Bz+pBQUDeXa4iI7ADYaOWF3qctBD/YfIAFa0="


class Hashing(unittest.TestCase):
    def test_hex_shape(self):
        self.assertEqual(sha256_hex(b"abc"), ABC_HEX)

    def test_b64_shape(self):
        self.assertEqual(sha256_b64(b"abc"), ABC_B64)

    def test_sri_shape(self):
        self.assertEqual(sri_sha256(b"abc"), "sha256-" + ABC_B64)

    def test_file_hex_matches_bytes_hex(self):
        with tempfile.NamedTemporaryFile(delete=False) as fh:
            fh.write(b"abc")
            path = pathlib.Path(fh.name)
        try:
            self.assertEqual(sha256_file_hex(path), ABC_HEX)
        finally:
            path.unlink()


class Dates(unittest.TestCase):
    def test_en_from_string(self):
        self.assertEqual(human_date("2026-05-23"), "23 May 2026")

    def test_fr_from_string(self):
        self.assertEqual(human_date("2026-05-23", lang="fr"), "23 mai 2026")

    def test_from_date_object(self):
        self.assertEqual(human_date(datetime.date(2026, 6, 2)), "2 June 2026")

    def test_none_is_empty(self):
        self.assertEqual(human_date(None), "")

    def test_unknown_lang_falls_back_to_en(self):
        self.assertEqual(human_date("2026-01-01", lang="xx"), "1 January 2026")

    def test_tables_cover_twelve_months(self):
        for lang, months in LOCALE_MONTHS.items():
            self.assertEqual(len(months), 12, lang)


class Slugs(unittest.TestCase):
    # the documented examples from tools/lib/slugs.py
    CASES = {
        "index.html.txt": "index_html_txt",
        ".well-known/person.json.txt": "well_known_person_json_txt",
        "i18n/it.js.txt": "i18n_it_js_txt",
        "htaccess.txt": "htaccess_txt",
        "integrity.json": "integrity_json",
        "SHA256SUMS": "sha256sums",
    }

    def test_documented_examples(self):
        for name, slug in self.CASES.items():
            self.assertEqual(i18n_slug(name), slug, name)

    def test_mirror_suffix_stays_distinguishable(self):
        self.assertNotEqual(i18n_slug("sitemap.xml.sha256"), i18n_slug("sitemap.xml.sha256.txt"))


class Sizes(unittest.TestCase):
    def test_sub_kilobyte(self):
        self.assertEqual(humanise_bytes(1), "1 byte")
        self.assertEqual(humanise_bytes(842), "842 bytes")
        self.assertEqual(humanise_bytes(842, lang="fr"), "842 octets")

    def test_kilobytes_one_decimal(self):
        self.assertEqual(humanise_bytes(27 * 1024), "27.0 KB")
        self.assertEqual(humanise_bytes(27 * 1024, lang="fr"), "27,0 Ko")

    def test_megabytes(self):
        self.assertEqual(humanise_bytes(int(1.4 * 1024 * 1024)), "1.4 MB")

    def test_negative_raises(self):
        with self.assertRaises(ValueError):
            humanise_bytes(-1)


if __name__ == "__main__":
    unittest.main()
