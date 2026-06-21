#!/usr/bin/env python3
"""validate_deny_parity.py — fail the build if the two deny surfaces drift apart.

The denied-extension list is encoded twice, in two syntaxes, by two tools:

  - tools/lib/htaccess_config.py        DENY_EXTENSION_RULES   (alternation regexes,
                                        e.g. r"\\.(php|phar|…)$") — the live server's
                                        last-line request-path defence.
  - tools/build/generate_public_exposure_manifest.py
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

Shape (deep module, small interface). The filesystem is the one injected seam —
`Repo(root)` — so the parity check runs over a fixture repo with no
monkeypatching. `evaluate(repo)` is the pure compute path returning a Result;
`main()` is the only adapter that prints/exits. The AST parse + reduce logic is
byte-identical to the former inline implementation.

Exit 0 = the two deny surfaces agree. Exit 1 = they disagree (or a list is
missing).
"""

from __future__ import annotations

import ast
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
from paths import REPO_ROOT  # noqa: E402
from repo import Repo  # noqa: E402  (shared filesystem evidence seam)

# repo-relative locations of the two deny surfaces (resolved through the Repo seam).
HTACCESS_CONFIG_REL = "tools/lib/htaccess_config.py"
EXPOSURE_MANIFEST_REL = "tools/build/generate_public_exposure_manifest.py"

# htaccess extension regexes are of the shape  \.(a|b|c)$ . other DENY_EXTENSION_RULES
# entries (\.template\.js$, the case-insensitive credential matcher) are not a plain
# extension alternation and are intentionally out of scope for the parity set.
_ALTERNATION = re.compile(r"^\\\.\(([a-z0-9|]+)\)\$$")


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    warns: list[str] = field(default_factory=list)
    oks: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fails


def _literal_list(repo: Repo, rel: str, name: str) -> list:
    """Return the literal value assigned to top-level `name` in the repo-relative
    file `rel`, via AST. No import — the target modules run work at import time,
    which we must avoid."""
    tree = ast.parse(repo.read(rel))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == name:
                    return ast.literal_eval(node.value)
    raise SystemExit(f"validate_deny_parity: {name} not found in {Path(rel).name}")


def _htaccess_extension_set(repo: Repo) -> set:
    rules = _literal_list(repo, HTACCESS_CONFIG_REL, "DENY_EXTENSION_RULES")
    exts: set = set()
    for rule in rules:
        m = _ALTERNATION.match(rule)
        if m:
            exts.update(m.group(1).split("|"))
    return exts


def _manifest_extension_set(repo: Repo) -> set:
    patterns = _literal_list(repo, EXPOSURE_MANIFEST_REL, "DENY_EXTENSION_PATTERNS")
    return {p[1:] if p.startswith(".") else p for p in patterns}


def evaluate(repo: Repo) -> Result:
    r = Result()
    htaccess = _htaccess_extension_set(repo)
    manifest = _manifest_extension_set(repo)
    if htaccess == manifest:
        r.oks.append(f"deny-extension parity — {len(htaccess)} extensions agree across")
        r.oks.append("    htaccess_config.py and generate_public_exposure_manifest.py")
        return r

    only_htaccess = sorted(htaccess - manifest)
    only_manifest = sorted(manifest - htaccess)
    r.fails.append("deny-extension parity — the two deny surfaces disagree.")
    if only_htaccess:
        r.fails.append(f"  denied by .htaccess but NOT by the manifest: {', '.join(only_htaccess)}")
    if only_manifest:
        r.fails.append(f"  denied by the manifest but NOT by .htaccess: {', '.join(only_manifest)}")
    r.fails.append(
        "  Remediation: add the missing extension(s) to whichever list lacks them —\n"
        "  DENY_EXTENSION_RULES in htaccess_config.py (alternation group) and\n"
        "  DENY_EXTENSION_PATTERNS in generate_public_exposure_manifest.py."
    )
    return r


def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    r = evaluate(repo)
    if r.ok:
        # the OK contract is two stdout lines: the parity headline and its
        # continuation (the two-tool names).
        print(f"OK: {r.oks[0]}")
        for line in r.oks[1:]:
            print(line)
        return 0
    sys.stderr.write(f"FAIL: {r.fails[0]}\n")
    for line in r.fails[1:]:
        sys.stderr.write(f"{line}\n")
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
