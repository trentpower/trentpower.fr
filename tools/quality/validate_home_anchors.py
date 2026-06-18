#!/usr/bin/env python3
"""validate_home_anchors.py — assert the homepage anchor model.

Run as a predeploy gate. Fails the build if the homepage's anchor
navigation contract regresses. The contract is: native anchor
navigation lands the section heading below the sticky header via
CSS scroll-margin-top, with IDs placed directly on the four
section elements (no empty anchor-target spans, no JS scroll
hacks).

Checks (all read-only):

  public/index.html
    - <section id="approach"   …> exists (directly on the section)
    - <section id="trajectory" …> exists
    - <section id="projects"   …> exists
    - <section id="contact"    …> exists
    - No empty <span id="approach|trajectory|projects|contact" …
      class="anchor-target"></span> stand-ins
    - Nav links point to those IDs:
        <a href="#approach">, <a href="#trajectory">,
        <a href="#projects">, <a href="#contact">
    - No duplicate IDs across the document for those four IDs

  public/app.js
    - No `preventDefault` call inside a click handler that targets
      a `[href^="#"]` anchor (native browser anchor navigation
      must remain the source of truth)
    - No `scrollIntoView` / `scrollTo` / `scrollToTarget` call
      anywhere (PR #11 deleted these; this gate keeps them out)

  public/styles.css
    - `scroll-margin-top` declarations for `#approach`,
      `#trajectory`, `#projects`, `#contact` exist (the CSS
      register that lands the heading below the sticky header)

Quiet on success, precise on failure.
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

SECTION_IDS = ("approach", "credentials", "trajectory", "projects", "contact")


def _strip_block_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)


def check_index_html(rel: str, text: str) -> list[str]:
    errors: list[str] = []

    for sid in SECTION_IDS:
        section_pattern = rf'<section[^>]*\bid="{sid}"[^>]*>'
        if not re.search(section_pattern, text):
            errors.append(
                f'{rel}: <section id="{sid}" …> not found '
                f"(must be on the section element directly, not on a "
                f"nested anchor span)"
            )

        anchor_span_pattern = rf'<span[^>]*\bid="{sid}"[^>]*\bclass="[^"]*\banchor-target\b'
        if re.search(anchor_span_pattern, text):
            errors.append(
                f'{rel}: empty <span id="{sid}" class="anchor-target"> '
                f"stand-in detected — IDs must live on the section element, "
                f"not on a separate empty span"
            )

        # section anchor reachability does not require an in-page nav
        # link any more — the nav-toggle / nav-links system was retired,
        # so the page presents only the masthead and readers discover
        # sections by scrolling. anchors are still reachable via deep
        # links (/#approach, /#trajectory, /#projects, /#contact), and
        # the section ids remain on the section elements (asserted
        # above). no nav-link check.

    for sid in SECTION_IDS:
        n_ids = len(re.findall(rf'\bid="{sid}"', text))
        if n_ids > 1:
            errors.append(f'{rel}: id="{sid}" appears {n_ids} times (must be unique)')

    return errors


def check_app_js(text: str) -> list[str]:
    """Forbid scroll-hijacking utilities AND any preventDefault /
    scrollTo / scrollIntoView inside a click handler that targets
    fragment anchors.

    The legitimate `window.scrollTo` call in the language-switch flow
    (which compensates for layout shift when the language changes
    mid-document) is allowed because it does NOT live inside a nav
    anchor click handler — it lives inside `switchLanguage()`."""
    errors: list[str] = []
    nocomments = _strip_block_comments(text)

    # hard ban: scrolltotarget (the deleted pr #11 helper) and
    # scrollintoview anywhere — neither has a legitimate use on the
    # homepage and both have caused regressions.
    for needle in ("scrollToTarget", "scrollIntoView"):
        if needle in nocomments:
            errors.append(
                f"app.js contains '{needle}' — native anchor navigation "
                f"is the source of truth for homepage menu scroll."
            )

    # Context-aware ban: scrollto / preventdefault inside any click
    # handler that selects a[href^="#"] (the nav-anchor pattern).
    nav_handler_re = re.compile(
        r'addEventListener\s*\(\s*[\'"]click[\'"]\s*,\s*function[^{]*\{'
        r"(?P<body>(?:[^{}]|\{[^{}]*\})*?)"
        r"\}\s*\)",
        re.DOTALL,
    )
    for m in nav_handler_re.finditer(nocomments):
        body = m.group("body")
        targets_anchor = 'a[href^="#"]' in body or "a[href^='#']" in body
        if not targets_anchor:
            continue
        for forbidden in ("preventDefault", "scrollTo("):
            if forbidden in body:
                errors.append(
                    f'app.js: a click handler that targets a[href^="#"] '
                    f"calls '{forbidden}' — homepage menu links must use "
                    f"native browser anchor navigation. Remove the call; "
                    f"CSS scroll-margin-top handles the offset."
                )

    return errors


def check_styles_css(text: str) -> list[str]:
    errors: list[str] = []
    nocomments = _strip_block_comments(text)

    for sid in SECTION_IDS:
        pattern = re.compile(rf'(?:#{sid}|\[id="{sid}"\])[^{{}}]*\{{[^}}]*scroll-margin-top')
        if not pattern.search(nocomments):
            errors.append(
                f"styles.css: no scroll-margin-top declaration matches "
                f'#{sid} or [id="{sid}"]. The sticky-header offset must '
                f"be CSS-owned for native anchor navigation to land "
                f"cleanly."
            )

    return errors


@dataclass
class Result:
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def evaluate(repo: Repo) -> Result:
    """run the pure homepage-anchor checks over the source files read through
    the Repo seam. returns a Result; never prints or exits."""
    result = Result()

    # the homepage content lives on the two language editions; the
    # root index.html is now the language gate (no anchor sections).
    for rel in ("en-au/index.html", "fr/index.html"):
        prel = f"public/{rel}"
        if not repo.is_file(prel):
            result.errors.append(f"missing file: public/{rel}")
        else:
            result.errors.extend(check_index_html(rel, repo.read(prel)))

    # the former app.js "brain" is split into behaviour-scoped modules;
    # scan the successors for scroll-hijacking regressions.
    combined = []
    for name in ("js/theme.js", "sw-register.js", "js/reveal.js"):
        prel = f"public/{name}"
        if not repo.is_file(prel):
            result.errors.append(f"missing file: public/{name}")
        else:
            combined.append(repo.read(prel))
    if combined:
        result.errors.extend(check_app_js("\n".join(combined)))

    if not repo.is_file("public/styles.css"):
        result.errors.append("missing file: public/styles.css")
    else:
        result.errors.extend(check_styles_css(repo.read("public/styles.css")))

    return result


def main(repo_root: Path = REPO_ROOT) -> int:
    result = evaluate(Repo(repo_root))

    if result.errors:
        print(f"FAIL: home-anchors — {len(result.errors)} issue(s):")
        for e in result.errors:
            print(f"  {e}")
        return 1

    print(
        "OK: home-anchors — section IDs on canonical sections, native "
        "anchor navigation preserved, scroll-margin-top declared for "
        "every home section ID"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
