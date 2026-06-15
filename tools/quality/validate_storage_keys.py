#!/usr/bin/env python3
"""validate_storage_keys.py — block undocumented browser-storage keys.

Goal
----
The privacy promise says client storage is limited to a small, named set of
reader-preference keys (language, appearance, first-visit markers, service-worker
metadata). This gate enforces that promise *before* deploy, statically, over the
shipped bytes — complementing the live-site score-ledger runtime check, which can
only observe keys after a page has run in a real browser.

Allowlist — single source of truth
----------------------------------
The approved keys live in ONE place: the ``LOCAL_KEYS`` array in
``public/js/local.js`` (the runtime privacy contract the /local/ page renders).
``tools/score-ledger/config.yml`` already documents itself as mirroring that
array. This gate reads ``local.js`` directly (regex, no YAML dependency) so the
deploy gate stays dependency-light and never imports the score-ledger.

What is scanned
---------------
Every storage *operation* in the deployed surface:
  - ``public/**/*.js``
  - inline ``<script>…</script>`` blocks in ``public/**/*.html``
matching ``localStorage|sessionStorage . (get|set|remove)Item( ARG`` or the
bracket form ``localStorage|sessionStorage[ ARG ]``.

Key resolution (static)
-----------------------
ARG is resolved to a literal key three ways:
  1. a string literal at the call site — ``getItem('tp-theme')``;
  2. a module constant — ``var K = 'tp-last-edition'; getItem(K)`` (we resolve
     ``var|const|let NAME = 'tp-…'`` assignments within the same file/block);
  3. the literal *root* of a concatenation — ``setItem('tp-last-read:/' + v, …)``
     contributes the prefix ``'tp-last-read:/'``.
A genuinely dynamic key (computed identifier we cannot resolve) is reported as an
unresolved note and skipped — static analysis cannot prove it, and failing on it
would be a false positive. This limitation is intentional and documented.

Match rule
----------
A resolved literal U is approved iff:
  - U equals an exact allowlist entry, OR
  - U starts with an allowlist prefix entry, OR
  - U is a concatenation root of an allowlisted full key
    (some exact entry starts with U, with len(U) >= 8 to exclude the bare ``tp-`` stem).

Quiet on success, precise on failure.
"""

from __future__ import annotations

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
from script_blocks import iter_script_blocks  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PUBLIC = REPO_ROOT / "public"
ALLOWLIST_SRC = PUBLIC / "js" / "local.js"

# frozen, sealed historical snapshots. these are immutable (enforced by the
# frozen_archives_immutable gate) and release.yml excludes them from the site
# archive too; they legitimately contain retired keys (e.g. the pre-rename
# 'tp-lang') from the edition they sealed. the storage-key contract governs the
# LIVE surface, so this gate skips the frozen release tree.
SKIP_PREFIXES = ("integrity/releases/",)


def _skip(rel: str) -> bool:
    return rel.startswith(SKIP_PREFIXES)


# concatenation-root clause floor: a literal shorter than this cannot earn
# approval purely by being a prefix of an allowlisted key (kills the bare
# "tp-" loophole). "tp-last-read:/" is length 14; 8 is a safe floor.
CONCAT_ROOT_MIN_LEN = 8

# storage operations: localStorage/sessionStorage .getItem/.setItem/.removeItem(
# or bracket access. capture the operand text up to the first delimiter.
_DOT_CALL = re.compile(r"\b(?:local|session)Storage\s*\.\s*(?:get|set|remove)Item\s*\(\s*([^,)]+)")
_BRACKET = re.compile(r"\b(?:local|session)Storage\s*\[\s*([^\]]+)")

# module constant assignment of a tp-* literal: var NAME = 'tp-...'.
_CONST = re.compile(r"(?:var|const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*[\"'](tp-[^\"']*)[\"']")

# a leading string literal (covers 'k', "k", and the root of 'k' + x).
_LEADING_LITERAL = re.compile(r"""^[\s(]*["']([^"']*)["']""")
_IDENT = re.compile(r"^[\s(]*([A-Za-z_$][\w$]*)\s*$")


def parse_allowlist(text: str) -> tuple[set[str], set[str]]:
    """Return (exact_keys, prefix_keys) from local.js LOCAL_KEYS entries."""
    exact: set[str] = set()
    prefix: set[str] = set()
    for m in re.finditer(r"key:\s*['\"]([^'\"]+)['\"][^}]*?prefix:\s*(true|false)", text):
        key, is_prefix = m.group(1), m.group(2) == "true"
        (prefix if is_prefix else exact).add(key)
    return exact, prefix


def approved(literal: str, exact: set[str], prefix: set[str]) -> bool:
    if literal in exact:
        return True
    if any(literal.startswith(p) for p in prefix):
        return True
    if len(literal) >= CONCAT_ROOT_MIN_LEN and any(e.startswith(literal) for e in exact):
        return True
    return False


def resolve(operand: str, consts: dict[str, str]) -> str | None:
    """Resolve a storage-call operand to a literal key, or None if dynamic."""
    m = _LEADING_LITERAL.match(operand)
    if m:
        return m.group(1)
    m = _IDENT.match(operand)
    if m and m.group(1) in consts:
        return consts[m.group(1)]
    return None


def scan_text(text: str) -> tuple[list[tuple[int, str]], list[int]]:
    """Return (resolved (line, key) hits, unresolved-line list) for one body."""
    consts = {m.group(1): m.group(2) for m in _CONST.finditer(text)}
    hits: list[tuple[int, str]] = []
    unresolved: list[int] = []
    for pat in (_DOT_CALL, _BRACKET):
        for m in pat.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            key = resolve(m.group(1), consts)
            if key is None:
                unresolved.append(line_no)
            else:
                hits.append((line_no, key))
    return hits, unresolved


def main() -> int:
    if not ALLOWLIST_SRC.is_file():
        print(f"  FAIL: storage-key allowlist source missing: {ALLOWLIST_SRC}")
        return 1
    exact, prefix = parse_allowlist(ALLOWLIST_SRC.read_text(encoding="utf-8"))
    if not (exact or prefix):
        print("  FAIL: storage-key allowlist (local.js LOCAL_KEYS) parsed empty")
        return 1

    failures: list[tuple[str, int, str]] = []
    unresolved_total = 0

    for path in sorted(PUBLIC.rglob("*.js")):
        rel = str(path.relative_to(PUBLIC))
        if _skip(rel):
            continue
        hits, unresolved = scan_text(path.read_text(encoding="utf-8", errors="replace"))
        unresolved_total += len(unresolved)
        for line_no, key in hits:
            if not approved(key, exact, prefix):
                failures.append((rel, line_no, key))

    for path in sorted(PUBLIC.rglob("*.html")):
        rel = str(path.relative_to(PUBLIC))
        if _skip(rel):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for blk in iter_script_blocks(text):
            body = blk.body
            if not body.strip():
                continue
            block_line = text.count("\n", 0, blk.body_start) + 1
            hits, unresolved = scan_text(body)
            unresolved_total += len(unresolved)
            for sub_line, key in hits:
                if not approved(key, exact, prefix):
                    failures.append((rel, block_line + sub_line - 1, key))

    if failures:
        print(f"  FAIL: storage-key allowlist — {len(failures)} undocumented key(s):")
        for rel, line_no, key in failures[:30]:
            print(f"    {rel}:{line_no} → '{key}' not in public/js/local.js LOCAL_KEYS")
        if len(failures) > 30:
            print(f"    … {len(failures) - 30} more")
        print(
            "    add the key to LOCAL_KEYS (and its config.yml/privacy-doc mirrors) "
            "or remove the storage write."
        )
        return 1

    note = f" ({unresolved_total} dynamic key(s) skipped)" if unresolved_total else ""
    print(f"  OK: storage-keys — every resolvable storage key is on the local.js allowlist{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
