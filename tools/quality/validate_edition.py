#!/usr/bin/env python3
"""validate_edition.py — fail the build on any stale edition reference.

Single source of truth: identity_canonical.json["edition"]. Every active
output that embeds an edition or "Edition YYYY-MM-DD" string must match.
Frozen archives under /integrity/releases/YYYY-MM/ are excluded by design
(they are PGP-signed historical snapshots).

Exit 0 = all references match canonical edition.
Exit 1 = at least one reference is stale; failing paths are printed.

Shape (deep module, small interface). The external interface is `main() -> int`
plus the OK/FAIL text contract. The filesystem is the injected `Repo(root)`
seam, so the whole gate runs through `evaluate(repo, edition) -> Result` over a
fixture repo — and the active-HTML set is discovered inside evaluate, not at
import time, so a fixture repo is exercised cleanly. Compute (`evaluate`) is
separate from render (`main`).
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

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
from paths import REPO_ROOT  # noqa: E402
from repo import Repo  # noqa: E402  (shared filesystem evidence seam)

CANONICAL_REL = "tools/config/identity_canonical.json"
STRINGS_REL = "tools/build/copy/strings.json"
SITE_META_REL = "public/site-metadata.json"
VERIFY_MODAL_REL = "public/js/verify-modal.js"
SW_REL = "public/sw.js"
VERIFICATION_DATA_REL = "public/verify/verification-data.js"
HUMANS_REL = "public/humans.txt"

EDITION_PREFIXES = ("Edition", "Édition", "Edizione", "Edición", "Ausgabe")
EDITION_PREFIX_RE = re.compile(r"\b(" + "|".join(EDITION_PREFIXES) + r")\s+(\d{4}-\d{2}-\d{2})\b")
DATA_EDITION_RE = re.compile(r'data-edition="(\d{4}-\d{2}-\d{2})"')
DOC_EDITION_RE = re.compile(r'<meta name="document-edition" content="(\d{4}-\d{2}-\d{2})"')


def _locale_date_re(lang):
    months = LOCALE_MONTHS.get(lang, LOCALE_MONTHS["en"])
    alt = "|".join(re.escape(m) for m in months)
    return re.compile(r"\b(\d{1,2})\s+(" + alt + r")\s+(\d{4})\b")


def _find_with_lines(text, pattern):
    """Yield (line_number, match) for every regex match."""
    for m in pattern.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        yield line, m


# every active .html under public/ — discovered by walk so the bilingual
# /en/ and /fr/ trees, the language gate, the neutral reader/archive pages
# and the root error fallbacks are all picked up automatically. excluded:
# the dated frozen-archive snapshots under integrity/releases/<edition>/
# (PGP-signed historical state), and the generated editorial review
# documents under editorial/ (not site pages).
def _active_html(repo: Repo) -> list[str]:
    out: list[str] = []
    prefix = "public/"
    for repo_rel in repo.glob("public/**/*.html"):
        rel = repo_rel[len(prefix) :]
        if re.match(r"integrity/releases/[^/]+/", rel):
            continue
        if rel.startswith("editorial/"):
            continue
        out.append(rel)
    return sorted(out, key=lambda x: x.split("/"))


def _check_html_text(rel: str, text: str, edition: str, fails: list) -> None:
    for line, m in _find_with_lines(text, DATA_EDITION_RE):
        if m.group(1) != edition:
            fails.append(f"{rel}:{line} data-edition expected {edition} got {m.group(1)}")
    for line, m in _find_with_lines(text, DOC_EDITION_RE):
        if m.group(1) != edition:
            fails.append(f"{rel}:{line} document-edition expected {edition} got {m.group(1)}")
    for line, m in _find_with_lines(text, EDITION_PREFIX_RE):
        if m.group(2) != edition:
            fails.append(f"{rel}:{line} '{m.group(0)}' expected edition {edition}")


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fails


def load(repo: Repo) -> tuple[str | None, list[str]]:
    if not repo.is_file(CANONICAL_REL):
        return None, [f"{CANONICAL_REL} not found"]
    edition = json.loads(repo.read(CANONICAL_REL)).get("edition", "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", edition):
        return None, [f"canonical edition '{edition}' is not YYYY-MM-DD"]
    return edition, []


def evaluate(repo: Repo, edition: str) -> Result:
    fails: list[str] = []

    # 1. active html files
    for rel in _active_html(repo):
        prel = f"public/{rel}"
        if not repo.is_file(prel):
            fails.append(f"{rel}: missing active HTML file")
            continue
        _check_html_text(rel, repo.read(prel), edition, fails)

    # 2. site-metadata.json — edition + asset_version prefix. edition is a
    # nested object since schema_version 1.0 (id/label/date); the legacy
    # string form is still accepted for backward compatibility.
    if repo.is_file(SITE_META_REL):
        sm = json.loads(repo.read(SITE_META_REL))
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
    if repo.is_file(VERIFY_MODAL_REL):
        m = re.search(r"var EDITION = '([^']*)'", repo.read(VERIFY_MODAL_REL))
        if not m:
            fails.append("js/verify-modal.js: no `var EDITION = '...'` literal found")
        elif m.group(1) != edition:
            fails.append(f"js/verify-modal.js: EDITION expected {edition} got {m.group(1)}")

    # 4. sw.js — cache name must contain the canonical edition
    if repo.is_file(SW_REL):
        m = re.search(r"var CACHE = '([^']*)'", repo.read(SW_REL))
        if not m:
            fails.append("sw.js: no `var CACHE = '...'` literal found")
        elif edition not in m.group(1):
            fails.append(f"sw.js: CACHE name '{m.group(1)}' does not contain edition {edition}")

    # 5. verify/verification-data.js — every record's edition must equal
    #    canonical (json inside a js assignment; substring scan suffices).
    if repo.is_file(VERIFICATION_DATA_REL):
        text = repo.read(VERIFICATION_DATA_REL)
        for line, m in _find_with_lines(text, re.compile(r'"edition": "(\d{4}-\d{2}-\d{2})"')):
            if m.group(1) != edition:
                fails.append(
                    f"verify/verification-data.js:{line} edition expected {edition} got {m.group(1)}"
                )

    # 6. humans.txt — last reviewed
    if repo.is_file(HUMANS_REL):
        m = re.search(r"Last reviewed:\s*(\d{4}-\d{2}-\d{2})", repo.read(HUMANS_REL))
        if m and m.group(1) != edition:
            fails.append(f"humans.txt: Last reviewed expected {edition} got {m.group(1)}")

    # 7. source/source-manifest.json — date freshness lives in
    # validate_source_mirrors.py (per-build, not pinned to the edition).
    # placeholder kept so future changes don't restore the stricter check.

    # 8. strings.json — localised human dates in per-language sub-trees must
    #    match the canonical edition's localised form.
    if repo.is_file(STRINGS_REL):
        try:
            sd = json.loads(repo.read(STRINGS_REL))
        except json.JSONDecodeError:
            sd = None
        if isinstance(sd, dict):
            from datetime import datetime as _dt

            try:
                edt = _dt.strptime(edition, "%Y-%m-%d")
            except ValueError:
                edt = None
            if edt is not None:
                # paths whose strings match a localised-date pattern but are not
                # edition dates: archival release-card labels carry numbered
                # prefixes that match by coincidence and reference frozen
                # archives — must not be rewritten or flagged.
                IGNORE_PREFIXES = (
                    "releases.print.card.",
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

    return Result(fails=fails)


def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    edition, errors = load(repo)
    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        return 1

    result = evaluate(repo, edition)
    if result.fails:
        print(f"FAIL: {len(result.fails)} edition-consistency issue(s) (canonical {edition}):")
        for f in result.fails:
            print(f"  {f}")
        return 1

    print(f"OK: edition consistency — every reference equals {edition}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
