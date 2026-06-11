"""
script_blocks.py · single source of truth for locating <script> blocks.

several validators and fixers need to find inline <script> elements in
generated html — to hash their bodies (csp), to skip them (comment
case-folding, byte-literal scans) or to scan inside them (runtime
contamination). they used to each carry a `<script…>…</script>` regex;
regexes over html are both a codeql finding (incomplete filtering) and
a drift risk between the five copies. this module parses with the
stdlib html.parser instead and reports exact character offsets, so a
caller can slice the ORIGINAL text byte-for-byte — nothing here ever
re-serialises markup, which is what keeps csp hashes stable.

parity notes (deliberate, matching the old regexes): a literal
"</script" inside a js string terminates the block, and a start tag
with no closing </script> is ignored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser

# csp only governs *executable* inline scripts: a <script> with no
# type, or with a javascript mime type. data blocks (application/json,
# application/ld+json, importmap, speculationrules, ...) carry a type
# the browser does not execute.
EXECUTABLE_SCRIPT_TYPES = {
    "",
    "text/javascript",
    "application/javascript",
    "application/ecmascript",
    "text/ecmascript",
    "module",
}


@dataclass(frozen=True)
class ScriptBlock:
    """one <script> element, located by exact offsets into the source text.

    every string field is a verbatim slice of the input:
      text[start:end]            — the whole element
      text[start:body_start]     — the start tag
      text[body_start:body_end]  — the body (== .body)
    """

    start: int  # offset of '<' of the start tag
    body_start: int  # offset just past '>' of the start tag
    body_end: int  # offset of '<' of '</script'
    end: int  # offset just past '>' of the end tag
    line: int  # 1-based line number of the start tag
    attrs: dict = field(compare=False)  # parsed attrs, names lowercased
    raw_start_tag: str  # exact source text of the start tag
    body: str  # exact source text of the body

    @property
    def src(self) -> str | None:
        """the src attribute value, or None for an inline script."""
        return self.attrs.get("src")

    @property
    def type_attr(self) -> str:
        """normalised type attribute — lowercased, '' when absent."""
        value = self.attrs.get("type")
        return (value or "").strip().lower()

    def is_executable(self) -> bool:
        """True when csp governs this block: inline + executable type."""
        return "src" not in self.attrs and self.type_attr in EXECUTABLE_SCRIPT_TYPES


class _ScriptCollector(HTMLParser):
    def __init__(self, text: str) -> None:
        super().__init__(convert_charrefs=True)
        self._text = text
        # cumulative offset of each line start — getpos() speaks in
        # (1-based line, 0-based column), offsets need absolute indexes.
        starts = [0]
        for chunk in text.split("\n")[:-1]:
            starts.append(starts[-1] + len(chunk) + 1)
        self._line_starts = starts
        self.blocks: list[ScriptBlock] = []
        self._pending: tuple[int, int, int, dict, str] | None = None

    def _abs(self) -> int:
        lineno, col = self.getpos()
        return self._line_starts[lineno - 1] + col

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "script" and self._pending is None:
            start = self._abs()
            raw = self.get_starttag_text() or ""
            self._pending = (start, start + len(raw), self.getpos()[0], dict(attrs), raw)

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        # `<script/>` — never emitted by the generators; recorded as an
        # empty-bodied block for completeness.
        if tag == "script" and self._pending is None:
            start = self._abs()
            raw = self.get_starttag_text() or ""
            end = start + len(raw)
            self.blocks.append(
                ScriptBlock(start, end, end, end, self.getpos()[0], dict(attrs), raw, "")
            )

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._pending is not None:
            start, body_start, line, attrs, raw = self._pending
            body_end = self._abs()
            gt = self._text.find(">", body_end)
            end = gt + 1 if gt >= 0 else len(self._text)
            self.blocks.append(
                ScriptBlock(
                    start,
                    body_start,
                    body_end,
                    end,
                    line,
                    attrs,
                    raw,
                    self._text[body_start:body_end],
                )
            )
            self._pending = None


def iter_script_blocks(text: str) -> list[ScriptBlock]:
    """parse text and return every closed <script> block, in source order."""
    collector = _ScriptCollector(text)
    collector.feed(text)
    collector.close()
    # an unterminated start tag (no </script>) is discarded — parity
    # with the regexes this module replaces.
    return collector.blocks


def strip_script_blocks(text: str, replacement: str = "") -> str:
    """return text with every closed <script> element removed."""
    out: list[str] = []
    pos = 0
    for blk in iter_script_blocks(text):
        out.append(text[pos : blk.start])
        out.append(replacement)
        pos = blk.end
    out.append(text[pos:])
    return "".join(out)
