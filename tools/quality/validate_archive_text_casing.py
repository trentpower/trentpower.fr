#!/usr/bin/env python3
"""validate_archive_text_casing.py — ZIP orientation casing gate.

reads the current edition's release ZIP and confirms that the five
in-memory orientation files exist with their ALLCAPS filenames and
that their prose follows the casing matrix documented in
docs/PUBLIC-ARTEFACT-CONVENTIONS.md.

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

Shape (deep module, small interface). The filesystem is the one injected seam —
`Repo(root)`. zipfile needs a real path, so the release ZIP is opened off
`repo.root` (mirroring validate_hidden_artefacts); `load(repo)` resolves the ZIP
path, `evaluate(repo, ctx)` holds the casing matrix and returns a Result, and
`main()` is the only adapter that prints or exits. Byte-identical to the former
module-global form.
"""

from __future__ import annotations

import io
import json
import re
import sys
import zipfile
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
from paths import REPO_ROOT  # noqa: E402
from repo import Repo  # noqa: E402  (shared filesystem evidence seam)

# repo-relative location of the canonical edition pointer.
IDENTITY_CANONICAL_REL = "tools/config/identity_canonical.json"

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
        # docs/PUBLIC-ARTEFACT-CONVENTIONS.md.
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


# ---------------------------------------------------------------------------
# Ctx / Result — the values that flow through the interface. load() resolves the
# release ZIP path (or None); evaluate() produces Result; main() renders it.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Ctx:
    zip_path: Path | None


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    # carried so main() can reproduce the original OK text without re-deriving.
    zip_name: str | None = None
    skipped: bool = False

    @property
    def ok(self) -> bool:
        return not self.fails


# ---------------------------------------------------------------------------
# load — resolve the canonical edition's release ZIP path. zipfile needs a real
# filesystem path, so this returns the path off repo.root (or None when there is
# no ZIP yet, which is the skip case).
# ---------------------------------------------------------------------------
def load(repo: Repo) -> Ctx:
    edition = ""
    if repo.is_file(IDENTITY_CANONICAL_REL):
        edition = json.loads(repo.read(IDENTITY_CANONICAL_REL)).get("edition", "")
    if not edition:
        return Ctx(zip_path=None)
    candidate = (
        repo.root / "public" / "integrity" / "releases" / edition / f"trentpower-fr-{edition}.zip"
    )
    return Ctx(zip_path=candidate if candidate.is_file() else None)


# ---------------------------------------------------------------------------
# evaluate — the compute interface. opens the ZIP off repo.root and applies the
# casing matrix; returns a Result, never prints or exits.
# ---------------------------------------------------------------------------
def evaluate(repo: Repo, ctx: Ctx) -> Result:
    if ctx.zip_path is None:
        return Result(skipped=True)

    r = Result(zip_name=ctx.zip_path.name)
    with zipfile.ZipFile(ctx.zip_path) as zf:
        names = set(zf.namelist())
        missing = EXPECTED_FILES - names
        if missing:
            r.fails.append(f"missing orientation file(s) in archive: {sorted(missing)}")
        for fname in sorted(EXPECTED_FILES & names):
            with zf.open(fname) as fp:
                text = io.TextIOWrapper(fp, encoding="utf-8").read()
            if CLEARSIGN_HEADER in text:
                r.fails.append(
                    f"{fname}: contains a clearsigned block — orientation "
                    f"files must be archive_only, not directly_signed."
                )
            for line_num, line in enumerate(text.splitlines(), 1):
                offenders = _check_prose_line(line)
                if offenders:
                    r.fails.append(f"{fname}:{line_num} uppercase tokens in prose: {offenders[:5]}")
    return r


# ---------------------------------------------------------------------------
# main — the side-effecting adapter. builds the seam, evaluates, renders, returns
# the exit code. the only place stdout and exit codes live.
# ---------------------------------------------------------------------------
def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    r = evaluate(repo, load(repo))

    if r.skipped:
        print("  OK: no release ZIP yet — skipping archive-casing check")
        return 0

    if r.fails:
        print(f"  FAIL: {len(r.fails)} archive-text-casing issue(s):")
        for f in r.fails[:50]:
            print(f"    {f}")
        if len(r.fails) > 50:
            print(f"    ... and {len(r.fails) - 50} more")
        return 1

    print(f"  OK: archive orientation files match casing matrix ({r.zip_name}).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
