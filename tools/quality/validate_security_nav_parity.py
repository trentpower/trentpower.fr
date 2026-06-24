#!/usr/bin/env python3
"""validate_security_nav_parity.py — the Security page's contents nav must
match its body.

The Security & Threat Model page opens with a numbered "contents" list that
promises a set of sections; the body then delivers them. That promise is a
trust surface — a page about precision must not announce one structure and show
another. This gate fails the build if they drift (issue #57: the nav listed 9
sections while the body had 10).

For each rendered edition (public/en-au/security/, public/fr/securite/) it
asserts, read-only:
  - the `.security-contents-list` nav exists;
  - the set of nav anchor targets (`<a href="#…">`) equals the set of body
    section heading ids (`<h2 class="security-section-heading" id="…">`) — so no
    section is missing from the nav and no nav link is dead;
  - every body heading id is unique.
And across the two languages: the section counts match (bilingual parity).

Shape (deep module, small interface): the injected seam is the `Repo`
filesystem; `evaluate(repo)` is the pure compute path returning a Result;
`main()` is the only adapter that prints/exits.

Exit 0 = nav and body agree in both languages. Exit 1 = a drift.
"""

from __future__ import annotations

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

# the two rendered security pages (en-au / fr).
PAGES = (("en-au", "public/en-au/security/index.html"), ("fr", "public/fr/securite/index.html"))


def nav_targets(text: str) -> list[str] | None:
    """fragment ids the contents nav links to, in order. None if the nav list
    is absent (itself a failure)."""
    m = re.search(
        r'<ol\b[^>]*class="[^"]*\bsecurity-contents-list\b[^"]*"[^>]*>(.*?)</ol>',
        text,
        re.DOTALL,
    )
    if not m:
        return None
    return re.findall(r'href="#([\w-]+)"', m.group(1))


def section_heading_ids(text: str) -> list[str]:
    """ids of the body section headings, in order (attr order independent)."""
    ids: list[str] = []
    for m in re.finditer(r"<h2\b([^>]*)>", text):
        attrs = m.group(1)
        if "security-section-heading" in attrs:
            idm = re.search(r'\bid="([\w-]+)"', attrs)
            if idm:
                ids.append(idm.group(1))
    return ids


def check_page(lang: str, rel: str, text: str) -> tuple[list[str], int]:
    """returns (errors, body_section_count) for one rendered page."""
    errors: list[str] = []
    nav = nav_targets(text)
    body = section_heading_ids(text)

    dupes = {i for i in body if body.count(i) > 1}
    for d in sorted(dupes):
        errors.append(f"{lang}: body heading id {d!r} is not unique")

    if nav is None:
        errors.append(f"{lang}: no .security-contents-list nav found in {rel}")
        return errors, len(body)

    nav_set, body_set = set(nav), set(body)
    for missing in sorted(body_set - nav_set):
        errors.append(
            f"{lang}: body section #{missing} has no entry in the contents nav "
            f"(nav promises {len(nav_set)} sections, body has {len(body_set)})"
        )
    for dead in sorted(nav_set - body_set):
        errors.append(f"{lang}: contents nav links to #{dead} but no such body section exists")

    return errors, len(body)


@dataclass
class Result:
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def evaluate(repo: Repo) -> Result:
    result = Result()
    counts: dict[str, int] = {}
    for lang, rel in PAGES:
        if not repo.is_file(rel):
            result.errors.append(f"missing file: {rel}")
            continue
        errs, n = check_page(lang, rel, repo.read(rel))
        result.errors.extend(errs)
        counts[lang] = n

    if len(counts) == 2 and len(set(counts.values())) != 1:
        result.errors.append(
            f"bilingual section-count mismatch: "
            + ", ".join(f"{lang}={n}" for lang, n in counts.items())
        )
    return result


def main(repo_root: Path = REPO_ROOT) -> int:  # pragma: no cover (side-effecting adapter)
    result = evaluate(Repo(repo_root))
    if result.errors:
        print(f"FAIL: security-nav parity — {len(result.errors)} issue(s):")
        for e in result.errors:
            print(f"  {e}")
        return 1
    print("OK: security-nav parity — contents nav matches the body sections in both languages")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
