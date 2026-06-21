#!/usr/bin/env python3
"""validate_sri_coherence.py — every SRI attribute matches the asset it covers.

Statically re-derives Subresource Integrity: for every same-origin
<link rel="stylesheet"> and external <script src> in the active HTML, the
`integrity="sha384-…"` attribute must equal the SHA-384 of the file it
references. Catches the bug class the build's hand-unrolled byte-convergence is
fragile to — "a step ran after the SRI sweep, so the HTML carries a hash that no
longer matches the asset" — directly and statically, with NO re-running of
generators (see docs/adr/0003). `integrity_manifest_freshness` already covers
manifest↔disk; this covers attribute↔asset.

This deliberately re-implements generate_sri.py's resolution + hash rather than
importing it (that module os.chdir()s at import): an independent re-derivation is
exactly what a coherence check should be. The two MUST agree on: active-HTML set
(all public/**/*.html except integrity/releases/), the /print.css skip, and the
/verify/verification-data.js exception (self-referential — carries NO integrity
by design; its bytes are covered by the signed manifest instead).

Shape: ADR-0002 — `evaluate(repo) -> Result` over the injected Repo seam; main()
is the only print/exit adapter.

Exit 0 = every SRI attribute is coherent. Exit 1 = a stale, missing, or
unexpected SRI attribute, or a referenced asset is absent.
"""

from __future__ import annotations

import base64
import hashlib
import posixpath
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

FROZEN_PREFIX = "integrity/releases/"
PRINT_CSS = "/print.css"
SELF_REF_SCRIPT = "/verify/verification-data.js"

LINK_RE = re.compile(r"<link\b[^>]*?>", re.IGNORECASE)
SCRIPT_RE = re.compile(r"<script\b[^>]*?\bsrc\s*=\s*\"[^\"]+\"[^>]*></script>", re.IGNORECASE)
_ATTR_TPL = r'\b{name}\s*=\s*"([^"]*)"'


def _attr(tag: str, name: str) -> str | None:
    m = re.search(_ATTR_TPL.format(name=name), tag, re.IGNORECASE)
    return m.group(1) if m else None


def _sri384(data: bytes) -> str:
    return "sha384-" + base64.b64encode(hashlib.sha384(data).digest()).decode("ascii")


def _resolve_rel(ref: str, html_rel: str) -> str | None:
    """Map a same-origin href/src to a public/-relative path, mirroring
    generate_sri.resolve_local. Returns None for cross-origin / unsupported
    schemes. `html_rel` is public/-relative (e.g. 'en-au/index.html')."""
    if ref.startswith(("//", "http://", "https://")):
        return None
    for sep in ("?", "#"):
        ref = ref.split(sep, 1)[0]
    if ref.startswith("/"):
        return ref.lstrip("/")
    if ref.startswith(("data:", "mailto:", "javascript:")):
        return None
    # document-relative — resolve against the html file's directory.
    base = posixpath.dirname(html_rel)
    return posixpath.normpath(posixpath.join(base, ref))


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    checked: int = 0  # number of integrity attributes verified

    @property
    def ok(self) -> bool:
        return not self.fails


def _active_html(repo: Repo) -> list[str]:
    prefix = "public/"
    out = []
    for full in repo.glob("public/**/*.html"):
        rel = full[len(prefix) :]
        if rel.startswith(FROZEN_PREFIX):
            continue
        out.append(rel)
    return out


def _expected(repo: Repo, ref: str, html_rel: str, kind: str, r: Result) -> str | None:
    """Resolve + hash the referenced asset; record a fail if it is missing.
    Returns the expected sha384 attribute value, or None if unresolvable."""
    local_rel = _resolve_rel(ref, html_rel)
    if local_rel is None:
        return None  # cross-origin — out of SRI scope
    pub = f"public/{local_rel}"
    if not repo.is_file(pub):
        r.fails.append(f"{html_rel}: {kind} {ref!r} -> {local_rel} (referenced asset not found)")
        return None
    return _sri384((repo.root / pub).read_bytes())


def evaluate(repo: Repo) -> Result:
    r = Result()
    for html_rel in _active_html(repo):
        text = repo.read(f"public/{html_rel}")

        for m in LINK_RE.finditer(text):
            tag = m.group(0)
            rel_attr = (_attr(tag, "rel") or "").lower().split()
            if "stylesheet" not in rel_attr:
                continue
            href = _attr(tag, "href") or ""
            if href.split("?", 1)[0].split("#", 1)[0] == PRINT_CSS:
                continue  # print.css is intentionally un-SRI'd
            if not href:
                continue
            expected = _expected(repo, href, html_rel, "<link>", r)
            if expected is None:
                continue
            present = _attr(tag, "integrity")
            r.checked += 1
            if present is None:
                r.fails.append(f"{html_rel}: <link href={href!r}> has NO integrity (expected SRI)")
            elif present != expected:
                r.fails.append(
                    f"{html_rel}: <link href={href!r}> SRI stale "
                    f"(attr {present[:20]}… vs asset {expected[:20]}…)"
                )

        for m in SCRIPT_RE.finditer(text):
            tag = m.group(0)
            src = _attr(tag, "src") or ""
            src_path = src.split("?", 1)[0].split("#", 1)[0]
            present = _attr(tag, "integrity")
            if src_path == SELF_REF_SCRIPT:
                # self-referential — must carry NO integrity (covered by the manifest).
                if present is not None:
                    r.fails.append(
                        f"{html_rel}: <script src={src!r}> must NOT carry integrity "
                        "(self-referential; signed manifest covers it)"
                    )
                continue
            expected = _expected(repo, src, html_rel, "<script>", r)
            if expected is None:
                continue
            r.checked += 1
            if present is None:
                r.fails.append(f"{html_rel}: <script src={src!r}> has NO integrity (expected SRI)")
            elif present != expected:
                r.fails.append(
                    f"{html_rel}: <script src={src!r}> SRI stale "
                    f"(attr {present[:20]}… vs asset {expected[:20]}…)"
                )
    return r


def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    r = evaluate(repo)
    if r.fails:
        print(f"  FAIL: {len(r.fails)} SRI coherence issue(s):")
        for f in r.fails[:50]:
            print(f"    {f}")
        if len(r.fails) > 50:
            print(f"    … and {len(r.fails) - 50} more")
        return 1
    print(f"  OK: SRI coherence — {r.checked} integrity attribute(s) match their assets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
