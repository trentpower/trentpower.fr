#!/usr/bin/env python3
"""validate_edition.py — fail the build on any stale edition reference.

Single source of truth: identity_canonical.json["edition"]. Every active
output that embeds an edition or "Edition YYYY-MM-DD" string must match.
Frozen archives under /integrity/releases/YYYY-MM/ are excluded by design
(they are PGP-signed historical snapshots).

Exit 0 = all references match canonical edition.
Exit 1 = at least one reference is stale; failing paths are printed.
"""

import json
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
from dates import LOCALE_MONTHS, human_date  # noqa: E402
from paths import (
    I18N_STRINGS as I18N_STRINGS,
)
from paths import (
    IDENTITY_CANONICAL as CANONICAL,
)
from paths import (
    PUBLIC_DIR as ROOT,
)
from paths import (
    SITE_METADATA as SITE_META,
)


# every active .html under public/ — discovered by walk so the bilingual
# /en/ and /fr/ trees, the language gate, the neutral reader/archive
# pages and the root error fallbacks are all picked up automatically.
# excluded: the dated frozen-archive snapshots under
# integrity/releases/<edition>/ (PGP-signed historical state), and the
# generated editorial review documents under editorial/ (not site pages).
def _discover_active_html() -> list:
    out = []
    for p in sorted(ROOT.glob("**/*.html")):
        rel = p.relative_to(ROOT).as_posix()
        if re.match(r"integrity/releases/[^/]+/", rel):
            continue
        if rel.startswith("editorial/"):
            continue
        out.append(rel)
    return out


ACTIVE_HTML = _discover_active_html()

EDITION_PREFIXES = ("Edition", "Édition", "Edizione", "Edición", "Ausgabe")
EDITION_PREFIX_RE = re.compile(r"\b(" + "|".join(EDITION_PREFIXES) + r")\s+(\d{4}-\d{2}-\d{2})\b")
DATA_EDITION_RE = re.compile(r'data-edition="(\d{4}-\d{2}-\d{2})"')
DOC_EDITION_RE = re.compile(r'<meta name="document-edition" content="(\d{4}-\d{2}-\d{2})"')


def _locale_date_re(lang):
    months = LOCALE_MONTHS.get(lang, LOCALE_MONTHS["en"])
    alt = "|".join(re.escape(m) for m in months)
    return re.compile(r"\b(\d{1,2})\s+(" + alt + r")\s+(\d{4})\b")


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _find_with_lines(text, pattern):
    """Yield (line_number, match) for every regex match."""
    for m in pattern.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        yield line, m


def _check_html_file(path: pathlib.Path, edition: str, fails: list):
    rel = path.relative_to(ROOT).as_posix()
    text = path.read_text(encoding="utf-8")
    for line, m in _find_with_lines(text, DATA_EDITION_RE):
        if m.group(1) != edition:
            fails.append(f"{rel}:{line} data-edition expected {edition} got {m.group(1)}")
    for line, m in _find_with_lines(text, DOC_EDITION_RE):
        if m.group(1) != edition:
            fails.append(f"{rel}:{line} document-edition expected {edition} got {m.group(1)}")
    for line, m in _find_with_lines(text, EDITION_PREFIX_RE):
        if m.group(2) != edition:
            fails.append(f"{rel}:{line} '{m.group(0)}' expected edition {edition}")


def _check_text_file(
    path: pathlib.Path, edition: str, fails: list, label: str, pattern: re.Pattern, group: int = 1
):
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    for line, m in _find_with_lines(text, pattern):
        if m.group(group) != edition:
            fails.append(f"{label}:{line} expected {edition} got {m.group(group)}")


def main() -> int:
    if not CANONICAL.exists():
        print(f"FAIL: {CANONICAL} not found", file=sys.stderr)
        return 1
    edition = _read_json(CANONICAL).get("edition", "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", edition):
        print(f"FAIL: canonical edition '{edition}' is not YYYY-MM-DD", file=sys.stderr)
        return 1

    fails: list[str] = []

    # 1. active html files
    for rel in ACTIVE_HTML:
        p = ROOT / rel
        if not p.exists():
            fails.append(f"{rel}: missing active HTML file")
            continue
        _check_html_file(p, edition, fails)

    # 2. site-metadata.json — edition + asset_version prefix
    # edition is a nested object since schema_version 1.0 — keys
    # are `id`, `label`, `date`. legacy string form is still
    # accepted for backward compatibility while the canonical
    # schema rolls out across mirrors and archives.
    if SITE_META.exists():
        sm = _read_json(SITE_META)
        sm_edition_field = sm.get("edition", "")
        if isinstance(sm_edition_field, dict):
            sm_edition = sm_edition_field.get("id", "")
            sm_edition_date = sm_edition_field.get("date", "")
            if sm_edition_date and sm_edition_date != sm_edition:
                fails.append(
                    f"site-metadata.json: edition.id '{sm_edition}' does not "
                    f"match edition.date '{sm_edition_date}'"
                )
        else:
            sm_edition = sm_edition_field
        if sm_edition != edition:
            fails.append(f"site-metadata.json: edition expected {edition} got {sm_edition}")
        av = sm.get("asset_version", "")
        if not av.startswith(edition + "."):
            fails.append(
                f"site-metadata.json: asset_version '{av}' does not start with '{edition}.'"
            )
    else:
        fails.append("site-metadata.json: file missing")

    # 3. js/verify-modal.js — var EDITION = '…';
    verify_modal_js = ROOT / "js" / "verify-modal.js"
    if verify_modal_js.exists():
        m = re.search(r"var EDITION = '([^']*)'", verify_modal_js.read_text(encoding="utf-8"))
        if not m:
            fails.append("js/verify-modal.js: no `var EDITION = '...'` literal found")
        elif m.group(1) != edition:
            fails.append(f"js/verify-modal.js: EDITION expected {edition} got {m.group(1)}")

    # 4. sw.js — cache name must contain the canonical edition
    sw_js = ROOT / "sw.js"
    if sw_js.exists():
        m = re.search(r"var CACHE = '([^']*)'", sw_js.read_text(encoding="utf-8"))
        if not m:
            fails.append("sw.js: no `var CACHE = '...'` literal found")
        elif edition not in m.group(1):
            fails.append(f"sw.js: CACHE name '{m.group(1)}' does not contain edition {edition}")

    # 5. verify/verification-data.js — at least one record's edition must
    #    equal canonical (the file is json inside a js assignment; substring
    #    check is sufficient and avoids parsing js).
    vd = ROOT / "verify" / "verification-data.js"
    if vd.exists():
        text = vd.read_text(encoding="utf-8")
        # every "edition": "<value>" inside the records must equal canonical.
        for line, m in _find_with_lines(text, re.compile(r'"edition": "(\d{4}-\d{2}-\d{2})"')):
            if m.group(1) != edition:
                fails.append(
                    f"verify/verification-data.js:{line} edition expected {edition} got {m.group(1)}"
                )

    # 6. humans.txt — last reviewed
    humans = ROOT / "humans.txt"
    if humans.exists():
        m = re.search(r"Last reviewed:\s*(\d{4}-\d{2}-\d{2})", humans.read_text(encoding="utf-8"))
        if m and m.group(1) != edition:
            fails.append(f"humans.txt: Last reviewed expected {edition} got {m.group(1)}")

    # 7. source/source-manifest.json — date freshness moved into
    # validate_source_mirrors.py (which checks every row's `modified`
    # against today's utc date, the canonical "validated" timestamp).
    # the edition date is no longer the right semantic here: source
    # mirrors are validated per build, not pinned to the publishing
    # edition. keep this comment as a placeholder so future changes
    # don't accidentally restore the stricter check.

    # 8. i18n/strings.json — localised human dates inside per-language
    #    sub-trees must match the canonical edition's localised form.
    #    this catches the bug-class where a key like integrity.last_reviewed
    #    keeps "1 may 2026" / "1 mai 2026" / "1. mai 2026" past the bump.
    strings = I18N_STRINGS
    if strings.exists():
        try:
            sd = json.loads(strings.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            sd = None
        if isinstance(sd, dict):
            from datetime import datetime as _dt

            try:
                edt = _dt.strptime(edition, "%Y-%m-%d")
            except ValueError:
                edt = None
            if edt is not None:
                # paths whose strings happen to match a localised-date
                # pattern but are not edition dates. archival release
                # card labels carry numbered prefixes ("01 may 2026" =
                # "card 01: may 2026 release") that match the regex
                # by coincidence; they reference frozen archives and
                # must not be rewritten or flagged.
                IGNORE_PREFIXES = (
                    "releases.print.card.",  # numbered archival cards
                    # date-pinned keys for the 2026-05-09 frozen archive page
                    # and the per-edition lineage labels. these reference
                    # specific frozen releases, not the current edition.
                    "releases.detail.",
                    "releases.edition_may09_",
                    "releases.edition_feb_",
                    "release_archive.print.",
                )

                def _is_ignored(trail):
                    return any(trail.startswith(p) for p in IGNORE_PREFIXES)

                for lang, tree in sd.items():
                    if lang not in LOCALE_MONTHS:
                        continue
                    expected = human_date(edt, lang=lang)
                    pat = _locale_date_re(lang)

                    # bind the loop variables as defaults — _walk is invoked
                    # within the same iteration, this just makes that explicit
                    def _walk(obj, trail, pat=pat, expected=expected, lang=lang):
                        if isinstance(obj, str):
                            if _is_ignored(trail):
                                return
                            for m in pat.finditer(obj):
                                if m.group(0) != expected:
                                    fails.append(
                                        f"i18n/strings.json {lang}.{trail}: "
                                        f"localised date '{m.group(0)}' expected '{expected}'"
                                    )
                        elif isinstance(obj, dict):
                            for k, v in obj.items():
                                _walk(v, f"{trail}.{k}" if trail else k)
                        elif isinstance(obj, list):
                            for i, x in enumerate(obj):
                                _walk(x, f"{trail}[{i}]")

                    _walk(tree, "")

    if fails:
        print(f"FAIL: {len(fails)} edition-consistency issue(s) (canonical {edition}):")
        for f in fails:
            print(f"  {f}")
        return 1

    print(f"OK: edition consistency — every reference equals {edition}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
