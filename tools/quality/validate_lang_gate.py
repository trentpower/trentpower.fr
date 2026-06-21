#!/usr/bin/env python3
"""validate_lang_gate.py — invariants for the root / language vestibule.

Scans the deployable vestibule (default public/index.html, or --root DIR)
and asserts:

  · index,follow — the vestibule is the indexable x-default edition gate
    for indexing
  · self-canonical to https://trentpower.fr/
  · hreflang en/fr/x-default present
  · the pre-paint script reads localStorage tp-last-edition (gate v2)
    or tp-lang (legacy, migrated on first paint) only to set the
    display language — it must NOT location.replace / auto-redirect.
    The root is a deliberate choice page shown on every visit.
  · the two choices are real <a href="/en-au/"> / <a href="/fr/"> links
    carrying data-lang-choice, so the vestibule works with no JavaScript

Usage:
    python3 tools/validate_lang_gate.py [--root DIR]

Shape (deep module, small interface). The filesystem is the one injected seam —
`Repo(root)` — so the whole gate runs over a fixture repo with no monkeypatching.
`evaluate(repo, gate_rel)` is the pure compute path returning a Result; `main()`
is the only adapter that reads argv, prints, and exits. The invariants,
constants, and messages are lifted verbatim from the former inline scan.
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

# repo-relative location of the vestibule (resolved through the Repo seam).
GATE_REL = "public/index.html"

# the OK line printed verbatim when every invariant holds.
OK_MESSAGE = "✓ language vestibule OK (index, self-canonical, hreflang,no auto-redirect, <a> choices)"


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    # set when the vestibule file itself is absent — a load failure, not an
    # invariant failure; main() renders it with the original run-hint message.
    missing: str | None = None

    @property
    def ok(self) -> bool:
        return not self.fails and self.missing is None


def evaluate(repo: Repo, gate_rel: str = GATE_REL) -> Result:
    r = Result()
    if not repo.is_file(gate_rel):
        r.missing = gate_rel
        return r

    html = repo.read(gate_rel)
    errors: list[str] = r.fails

    # the root / is the x-default edition gate — a legitimate indexable
    # entry point. the rich editorial graph lives on /en-au/ and /fr/.
    if not re.search(r'<meta name="robots" content="index[, ]+follow">', html):
        errors.append("missing <meta robots=index,follow>")
    if '<link rel="canonical" href="https://trentpower.fr/">' not in html:
        errors.append("vestibule must self-canonical to https://trentpower.fr/")
    for hl in ("en-AU", "fr", "x-default"):
        if f'hreflang="{hl}"' not in html:
            errors.append(f"missing hreflang {hl}")

    head = html.split("</head>", 1)[0]
    # gate v2 storage key is tp-last-edition; legacy tp-lang is migrated
    # on first paint, so either key satisfies the invariant. tightening
    # back to tp-last-edition only is a follow-up cleanup once the
    # migration window has elapsed.
    # match the key string + a localStorage call anywhere in head — the
    # minified boot script binds the key to a const ("L='tp-last-edition'"
    # then "localStorage.getItem(L)"), so a literal getItem('tp-last-edition')
    # substring isn't present.
    uses_storage = "localStorage.getItem(" in head
    names_new = "'tp-last-edition'" in head or '"tp-last-edition"' in head
    names_old = "'tp-lang'" in head or '"tp-lang"' in head
    if not (uses_storage and (names_new or names_old)):
        errors.append("pre-paint script does not read localStorage (tp-last-edition or tp-lang)")
    # the root must NOT auto-redirect — it is a deliberate choice page
    # shown on every visit. a stored preference only sets the display
    # language; it never bypasses the choice.
    if "location.replace(" in html or "location.href" in html or re.search(r"location\s*=", html):
        errors.append(
            "vestibule must not auto-redirect (no location.replace / "
            "location.href / location= — the root is a choice page)"
        )

    if not re.search(r'<a [^>]*href="/en-au/"[^>]*data-lang-choice="en"', html) and not re.search(
        r'<a [^>]*data-lang-choice="en"[^>]*href="/en-au/"', html
    ):
        errors.append("no <a href=/en-au/ data-lang-choice=en> choice")
    if not re.search(r'<a [^>]*href="/fr/"', html):
        errors.append("no <a href=/fr/> choice")

    return r


def main(repo_root: Path = REPO_ROOT) -> int:
    argv = sys.argv[1:]
    gate_rel = GATE_REL
    if "--root" in argv:
        # --root points at an arbitrary deployable tree; resolve its
        # index.html relative to repo_root so the Repo seam can read it.
        root = Path(argv[argv.index("--root") + 1]).resolve()
        try:
            gate_rel = (root / "index.html").relative_to(repo_root).as_posix()
        except ValueError:
            # outside the repo tree — read it directly via its own Repo root.
            return _run(Repo(root), "index.html")
    return _run(Repo(repo_root), gate_rel)


def _run(repo: Repo, gate_rel: str) -> int:
    r = evaluate(repo, gate_rel)
    if r.missing is not None:
        gate = repo.root / r.missing
        print(
            f"✗ vestibule not found: {gate}\n  run: python3 tools/render_pages.py", file=sys.stderr
        )
        return 1
    for e in r.fails:
        print(f"  ✗ {e}", file=sys.stderr)
    if r.fails:
        print(f"\n✗ language vestibule: {len(r.fails)} error(s)", file=sys.stderr)
        return 1
    print(OK_MESSAGE)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
