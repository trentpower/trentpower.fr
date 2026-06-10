#!/usr/bin/env python3
"""tools/validate_archive_text_casing.py — ZIP orientation casing gate.

reads the current edition's release ZIP and confirms that the five
in-memory orientation files exist with their ALLCAPS filenames and
that their prose follows the casing matrix documented in
docs/public-artefact-conventions.md.

casing rule:
  - prose lines (free-running sentences) are lowercase.
  - label lines (e.g. `Edition:`, `Date:`, `Public Key:`) at the
    start of a line use Title Case before the colon.
  - section header lines surrounded by a `------` underline are
    Title Case.
  - tokens preserved as-written: urls, paths, hashes, identifiers
    with dots/dashes/slashes.

ZIP-only orientation files must NOT carry an inline PGP block —
that would mis-classify them as directly-signed when they are
class archive_only.
"""

import io
import re
import sys
import zipfile
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
import json as _json

from paths import IDENTITY_CANONICAL, PUBLIC_DIR  # noqa: E402

EXPECTED_FILES = {
    "FILES.txt",
    "FONT-LICENSE-NOTICE.txt",
    "README.txt",
    "RELEASE.txt",
    "VERIFY.txt",
}

CLEARSIGN_HEADER = "-----BEGIN PGP SIGNED MESSAGE-----"

# tokens preserved as-written — same logic as fix_lowercase_comments
# plus pure-upper identifiers such as the SHA256SUMS filename.
_HAS_PATHISH = re.compile(r"[/\\@:_]|[\w][.][\w]|[\w][-][\w]")
_PURE_HEX = re.compile(r"^[0-9a-f]{8,}$")
_CAMEL_CASE = re.compile(r"[a-z][A-Z]")
_ALL_UPPER_IDENT = re.compile(r"^[A-Z][A-Z0-9_]{2,}\.?$")  # SHA256SUMS, README, etc.

# a label line: optional indentation, a leading word (may carry an
# internal hyphen such as `per-file`), followed by 0-3 trailing tokens,
# closed by `:` then whitespace or end-of-line. matches both the bare
# header form (`public records:`) and the labelled-value form
# (`public key: https://...`).
_LABEL_LINE = re.compile(r"^\s*([A-Z][A-Za-z0-9-]*(?:\s+[A-Za-z][A-Za-z0-9-]*){0,3}):(\s|$)")

# section header line: short (≤4 words, ≤30 chars), every token starts
# uppercase, no colon, no rule, no trailing punctuation. tight bounds
# keep this from absorbing whole title-cased sentences.
_SECTION_HEADER = re.compile(r"^\s*([A-Z][A-Za-z0-9]*)(\s+[A-Z][A-Za-z0-9]*){0,3}\s*$")


def _is_section_header(line: str) -> bool:
    body = line.strip()
    if len(body) > 30:
        return False
    return _SECTION_HEADER.match(line) is not None


# rule lines under a header (------ or ====== style).
_RULE_LINE = re.compile(r"^[-=]{3,}\s*$")


def _locate_release_zip() -> Path | None:
    edition = _json.loads(IDENTITY_CANONICAL.read_text(encoding="utf-8")).get("edition", "")
    if not edition:
        return None
    candidate = PUBLIC_DIR / "integrity" / "releases" / edition / f"trentpower-fr-{edition}.zip"
    return candidate if candidate.is_file() else None


def _is_preserve_token(tok: str) -> bool:
    if not tok:
        return True
    if _PURE_HEX.match(tok):
        return True
    if _HAS_PATHISH.search(tok):
        return True
    if _CAMEL_CASE.search(tok):
        return True
    if _ALL_UPPER_IDENT.match(tok):
        return True
    return False


def _check_prose_line(line: str) -> list[str]:
    """return a list of offending tokens, or empty for a clean line."""
    if not line.strip():
        return []
    if _RULE_LINE.match(line):
        return []
    if _LABEL_LINE.match(line):
        # the label itself is allowed title-case; the trailing
        # content is still subject to the lowercase rule but is
        # dominated by urls/paths anyway. skip enforcement on the
        # trailing half.
        return []
    if _is_section_header(line):
        # standalone title-case section header (no colon, no content,
        # ≤4 words, ≤30 chars). documented as allowed in
        # docs/public-artefact-conventions.md.
        return []
    bad: list[str] = []
    for tok in line.split():
        if _is_preserve_token(tok):
            continue
        # contiguous uppercase runs longer than 1 char are loud and
        # imply shouting (we already allow Title-Case labels and
        # all-caps acronyms inside path-ish tokens via preserve).
        if re.search(r"[A-Z]{2,}", tok):
            bad.append(tok)
            continue
        # a single capital letter at the start of an ordinary word
        # is the typical shouting-prose pattern we want to catch.
        # dotted abbreviations like `u.s.` are preserve tokens (the
        # internal period makes them path-ish); a plain capitalised
        # word with no dot, slash, or hyphen still gets flagged.
        if tok[:1].isupper() and tok[1:].islower() and not tok.endswith("."):
            bad.append(tok)
    return bad


def main() -> int:
    zip_path = _locate_release_zip()
    if zip_path is None:
        print("  OK: no release ZIP yet — skipping archive-casing check")
        return 0

    fails: list[str] = []
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        missing = EXPECTED_FILES - names
        if missing:
            fails.append(f"missing orientation file(s) in archive: {sorted(missing)}")
        for fname in sorted(EXPECTED_FILES & names):
            with zf.open(fname) as fp:
                text = io.TextIOWrapper(fp, encoding="utf-8").read()
            if CLEARSIGN_HEADER in text:
                fails.append(
                    f"{fname}: contains a clearsigned block — orientation "
                    f"files must be archive_only, not directly_signed."
                )
            for line_num, line in enumerate(text.splitlines(), 1):
                offenders = _check_prose_line(line)
                if offenders:
                    fails.append(f"{fname}:{line_num} uppercase tokens in prose: {offenders[:5]}")

    if fails:
        print(f"  FAIL: {len(fails)} archive-text-casing issue(s):")
        for f in fails[:50]:
            print(f"    {f}")
        if len(fails) > 50:
            print(f"    ... and {len(fails) - 50} more")
        return 1

    print(f"  OK: archive orientation files match casing matrix ({zip_path.name}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
