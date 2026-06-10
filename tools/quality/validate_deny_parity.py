#!/usr/bin/env python3
"""validate_deny_parity.py — fail the build if the two deny surfaces drift apart.

The denied-extension list is encoded twice, in two syntaxes, by two tools:

  - tools/htaccess_config.py            DENY_EXTENSION_RULES   (alternation regexes,
                                        e.g. r"\\.(php|phar|…)$") — the live server's
                                        last-line request-path defence.
  - tools/generate_public_exposure_manifest.py
                                        DENY_EXTENSION_PATTERNS (flat ".ext" suffix
                                        list emitted into the public-exposure manifest)
                                        — the build-time exposure validator's check.

They are meant to deny the same set of file extensions. Nothing cross-checked
that, so a new dangerous extension added to one but not the other would silently
leave a gap (server denies but manifest believes it safe, or vice versa). This
validator parses both — by AST, with no import side effects — reduces each to a
set of bare extensions, and fails if they disagree.

Scope note: only the *extension* axis is checked here. Directory and basename
deny rules are deliberately layered differently between the two tools
(htaccess splits path vs dir vs dotfile; the manifest splits path-glob vs
basename-glob), so a naive set comparison there would false-positive. Extensions
are the single unambiguous, most drift-prone axis — an explicit, low-noise gate.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTACCESS_CONFIG = ROOT / "lib" / "htaccess_config.py"
EXPOSURE_MANIFEST = ROOT / "build" / "generate_public_exposure_manifest.py"

# htaccess extension regexes are of the shape  \.(a|b|c)$ . other DENY_EXTENSION_RULES
# entries (\.template\.js$, the case-insensitive credential matcher) are not a plain
# extension alternation and are intentionally out of scope for the parity set.
_ALTERNATION = re.compile(r"^\\\.\(([a-z0-9|]+)\)\$$")


def _literal_list(path: Path, name: str) -> list:
    """Return the literal value assigned to top-level `name` in `path`, via AST.
    No import — the target modules run work at import time, which we must avoid."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == name:
                    return ast.literal_eval(node.value)
    raise SystemExit(f"validate_deny_parity: {name} not found in {path.name}")


def _htaccess_extension_set() -> set:
    rules = _literal_list(HTACCESS_CONFIG, "DENY_EXTENSION_RULES")
    exts: set = set()
    for rule in rules:
        m = _ALTERNATION.match(rule)
        if m:
            exts.update(m.group(1).split("|"))
    return exts


def _manifest_extension_set() -> set:
    patterns = _literal_list(EXPOSURE_MANIFEST, "DENY_EXTENSION_PATTERNS")
    return {p[1:] if p.startswith(".") else p for p in patterns}


def main() -> int:
    htaccess = _htaccess_extension_set()
    manifest = _manifest_extension_set()
    if htaccess == manifest:
        print(f"OK: deny-extension parity — {len(htaccess)} extensions agree across")
        print("    htaccess_config.py and generate_public_exposure_manifest.py")
        return 0

    only_htaccess = sorted(htaccess - manifest)
    only_manifest = sorted(manifest - htaccess)
    sys.stderr.write("FAIL: deny-extension parity — the two deny surfaces disagree.\n")
    if only_htaccess:
        sys.stderr.write(
            f"  denied by .htaccess but NOT by the manifest: {', '.join(only_htaccess)}\n"
        )
    if only_manifest:
        sys.stderr.write(
            f"  denied by the manifest but NOT by .htaccess: {', '.join(only_manifest)}\n"
        )
    sys.stderr.write(
        "  Remediation: add the missing extension(s) to whichever list lacks them —\n"
        "  DENY_EXTENSION_RULES in htaccess_config.py (alternation group) and\n"
        "  DENY_EXTENSION_PATTERNS in generate_public_exposure_manifest.py.\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
