#!/usr/bin/env python3
"""validate_html_correctness.py — block obvious structural HTML defects
in the active deployed pages.

Checks
- mismatched heading open/close tags (e.g. <h3>…</h2>)
- duplicate `id="…"` values within one document
- duplicate `<link rel="canonical">`
- duplicate `<meta name="description">`
- duplicate `<meta property="og:title">`
- duplicate `<meta property="og:url">`
- exactly one visible <h1> per page (descendants of aria-hidden="true"
  excluded). Print-only sections must be aria-hidden and use <p>, not
  duplicate <h1>.
- no <h1> anywhere inside an aria-hidden="true" subtree.
- no <a> with empty visible text and no aria-label (icon-only or JS-
  populated anchors must declare an accessible name).

Scoped narrowly: parser-level structural defects only. No
attribute-ordering preferences, no whitespace policing, no semantic
opinions. Quiet on success, precise on failure.

Shape (deep module, small interface). The filesystem is the one injected seam —
`Repo(root)` — so the whole gate runs over a fixture repo with no
monkeypatching. `evaluate(repo)` is the pure compute path returning a Result;
`main()` is the only adapter that prints/exits. The `_Validator(HTMLParser)`
subclass and the per-page parse logic are unchanged — `validate_page` takes the
HTML text (read through the seam), not a path.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
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

HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


# every active .html under public/ — discovered by walk so the
# bilingual /en/ and /fr/ trees are covered. excluded:
#   - the dated frozen-archive snapshots under integrity/releases/<ed>/
#   - the generated editorial review documents under editorial/
#   - the source-view reader shells (/source/view/, /en/source/view/,
#     /fr/source/voir/) — JS-driven app shells whose heading is
#     rendered at runtime, so they carry no static <h1> by design.
def _discover_active_pages(repo: Repo) -> list[str]:
    out: list[str] = []
    prefix = "public/"
    for full in repo.glob(f"{prefix}**/*.html"):
        rel = full[len(prefix) :]
        if re.match(r"integrity/releases/[^/]+/", rel):
            continue
        if rel.startswith("editorial/"):
            continue
        if re.search(r"(^|/)source/(view|voir)/index\.html$", rel):
            continue
        out.append(rel)
    return out


class _Validator(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.errors: list[str] = []
        self.heading_stack: list[tuple[str, int]] = []
        self.ids_seen: dict[str, int] = {}
        self.canonical_count = 0
        self.description_count = 0
        self.og_title_count = 0
        self.og_url_count = 0
        # element stack tracks every non-void open tag with a flag for
        # whether it pushed an aria-hidden=true frame. lets us answer
        # "is the current point inside an aria-hidden subtree?" without
        # re-parsing.
        self._element_stack: list[tuple[str, bool]] = []
        self._aria_hidden_depth = 0
        self.h1_visible_count = 0
        self.h1_in_aria_hidden_lines: list[int] = []
        # anchor accumulator. each entry is the open <a> with its line,
        # an aria-label flag, and a buffer of visible text data. closed
        # anchors are evaluated immediately and dropped.
        self._anchor_stack: list[dict] = []

    def _in_aria_hidden(self) -> bool:
        return self._aria_hidden_depth > 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrd = {k.lower(): (v or "") for k, v in attrs}
        if tag not in VOID_TAGS:
            pushed_aria = attrd.get("aria-hidden", "").lower() == "true"
            if pushed_aria:
                self._aria_hidden_depth += 1
            self._element_stack.append((tag, pushed_aria))
        if tag in HEADING_TAGS:
            self.heading_stack.append((tag, self.getpos()[0]))
        if tag == "h1":
            if self._in_aria_hidden():
                self.h1_in_aria_hidden_lines.append(self.getpos()[0])
            else:
                self.h1_visible_count += 1
        if tag == "a":
            self._anchor_stack.append(
                {
                    "line": self.getpos()[0],
                    "has_aria_label": bool(attrd.get("aria-label", "").strip()),
                    "in_aria_hidden": self._in_aria_hidden(),
                    "text": [],
                }
            )
        if "id" in attrd and attrd["id"]:
            id_val = attrd["id"]
            if id_val in self.ids_seen:
                self.errors.append(
                    f"duplicate id={id_val!r} at line {self.getpos()[0]} "
                    f"(first seen at line {self.ids_seen[id_val]})"
                )
            else:
                self.ids_seen[id_val] = self.getpos()[0]
        if tag == "link" and attrd.get("rel", "").lower() == "canonical":
            self.canonical_count += 1
        if tag == "meta":
            name = attrd.get("name", "").lower()
            prop = attrd.get("property", "").lower()
            if name == "description":
                self.description_count += 1
            if prop == "og:title":
                self.og_title_count += 1
            if prop == "og:url":
                self.og_url_count += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in HEADING_TAGS:
            if not self.heading_stack:
                self.errors.append(f"</{tag}> with no matching open at line {self.getpos()[0]}")
            else:
                opened, opened_line = self.heading_stack.pop()
                if opened != tag:
                    self.errors.append(
                        f"heading mismatch: <{opened}> opened at line {opened_line} "
                        f"closed as </{tag}> at line {self.getpos()[0]}"
                    )
        if tag == "a" and self._anchor_stack:
            a = self._anchor_stack.pop()
            if not a["in_aria_hidden"] and not a["has_aria_label"]:
                visible = "".join(a["text"]).replace("\xa0", "").strip()
                if not visible:
                    self.errors.append(
                        f"empty <a> with no aria-label at line {a['line']} "
                        "(icon-only or JS-populated anchors need an accessible name)"
                    )
        if tag not in VOID_TAGS:
            # pop matching frame from the element stack. htmlparser
            # already gives us well-nested events from this codebase
            # (validated by the existing heading-mismatch check), so a
            # single pop suffices; if mis-nesting is ever introduced
            # the heading check will fire first.
            while self._element_stack and self._element_stack[-1][0] != tag:
                _, popped_aria = self._element_stack.pop()
                if popped_aria:
                    self._aria_hidden_depth -= 1
            if self._element_stack:
                _, popped_aria = self._element_stack.pop()
                if popped_aria:
                    self._aria_hidden_depth -= 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Self-closing form, treat as void: never opens a frame.
        attrd = {k.lower(): (v or "") for k, v in attrs}
        if "id" in attrd and attrd["id"]:
            id_val = attrd["id"]
            if id_val in self.ids_seen:
                self.errors.append(
                    f"duplicate id={id_val!r} at line {self.getpos()[0]} "
                    f"(first seen at line {self.ids_seen[id_val]})"
                )
            else:
                self.ids_seen[id_val] = self.getpos()[0]

    def handle_data(self, data: str) -> None:
        if self._anchor_stack:
            self._anchor_stack[-1]["text"].append(data)

    def finish(self) -> list[str]:
        if self.canonical_count > 1:
            self.errors.append(f"duplicate <link rel=canonical> ({self.canonical_count})")
        if self.description_count > 1:
            self.errors.append(f"duplicate <meta name=description> ({self.description_count})")
        if self.og_title_count > 1:
            self.errors.append(f"duplicate <meta property=og:title> ({self.og_title_count})")
        if self.og_url_count > 1:
            self.errors.append(f"duplicate <meta property=og:url> ({self.og_url_count})")
        if self.h1_visible_count != 1:
            self.errors.append(
                f"expected exactly one visible <h1> (excluding aria-hidden subtrees), "
                f"found {self.h1_visible_count}"
            )
        for line in self.h1_in_aria_hidden_lines:
            self.errors.append(
                f'<h1> at line {line} is inside an aria-hidden="true" subtree '
                "(use <p> with the same class for print-only titles)"
            )
        return self.errors


def validate_page(text: str) -> list[str]:
    # strip JSON-LD <script> bodies — they contain `</…>` only as json
    # strings and htmlparser handles them, but json `<` chars inside
    # body text can still trip strict heading detection. safer to
    # leave them in place since htmlparser treats <script> body as
    # raw text data — proven by handle_data being called, not
    # handle_starttag. no stripping needed.
    v = _Validator()
    v.feed(text)
    v.close()
    return v.finish()


# ---------------------------------------------------------------------------
# Result — the value that flows through the interface. evaluate() produces it;
# main() renders it. tests assert on Result, never on stdout. `summary` carries
# the green one-liner's page count so the render stays a thin adapter.
# ---------------------------------------------------------------------------
@dataclass
class Result:
    fails: list[tuple[str, str]] = field(default_factory=list)
    warns: list[str] = field(default_factory=list)
    page_count: int = 0

    @property
    def ok(self) -> bool:
        return not self.fails


# ---------------------------------------------------------------------------
# evaluate — the compute interface. one call, one Result, over the injected
# Repo. this is the test surface.
# ---------------------------------------------------------------------------
def evaluate(repo: Repo) -> Result:
    r = Result()
    active_pages = _discover_active_pages(repo)
    r.page_count = len(active_pages)
    for rel in active_pages:
        prel = f"public/{rel}"
        if not repo.is_file(prel):
            r.fails.append((rel, "missing"))
            continue
        text = repo.read(prel)
        for err in validate_page(text):
            r.fails.append((rel, err))
    return r


# ---------------------------------------------------------------------------
# main — the side-effecting adapter. evaluates, renders, returns exit code. the
# only place stdout and exit codes live.
# ---------------------------------------------------------------------------
def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    public_root = repo_root / "public"
    if not public_root.is_dir():
        print(f"FAIL: public root not found at {public_root}")
        return 1

    r = evaluate(repo)

    if r.fails:
        print(f"  FAIL: html-correctness — {len(r.fails)} issue(s):")
        for rel, err in r.fails[:40]:
            print(f"    {rel}: {err}")
        if len(r.fails) > 40:
            print(f"    … {len(r.fails) - 40} more")
        return 1
    print(
        f"  OK: html-correctness — {r.page_count} active pages parse cleanly with no structural defects"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
