#!/usr/bin/env python3
"""validate_documentation.py — blocking gate for the /documentation/ surface.

Keeps the published documentation set honest without re-rendering it (no
Chromium in CI):

  1. presence      index.html + README.pdf + README.txt all exist.
  2. layout        the committed README.pdf passes the publication-layout
                   validator (no overlaps, no clipped text) — tools/pdf/.
  3. accuracy      the PDF's text contains none of the storage/CSP claims that
                   were corrected (a regression guard against the false
                   "no localStorage" / "forbid storage" / "connect-src 'none'"
                   wording creeping back in).
  4. coherence     the SHA-256 printed on the landing page matches the actual
                   README.pdf bytes (so the page never advertises a stale hash).

Requires PyMuPDF (fitz); the docs PDF is binary, so text/box extraction needs
it. CI installs it alongside jsonschema.
"""

from __future__ import annotations

import importlib.util
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
from hashing import sri_sha256  # noqa: E402
from paths import PUBLIC_DIR, TOOLS_DIR  # noqa: E402

DOC_DIR = PUBLIC_DIR / "documentation"
REQUIRED = ("index.html", "README.pdf", "README.txt")

# normalised substrings that must NOT appear in the published PDF. these are the
# exact false claims corrected in this edition; their return is a regression.
FORBIDDEN_PHRASES = [
    "forbid storage",
    "no localstorage or sessionstorage",
    "no analytics / cookies / storage",
    "connect-src 'none'",
    "block-all-mixed-content",
]


def _normalise(text: str) -> str:
    repl = {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "‑": "-",
        "–": "-",
        "—": "-",
        " ": " ",
    }
    for k, v in repl.items():
        text = text.replace(k, v)
    return " ".join(text.lower().split())


def _load_layout_validator():
    path = TOOLS_DIR / "quality" / "pdf" / "validate-layout.py"
    spec = importlib.util.spec_from_file_location("validate_layout", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    fails: list[str] = []

    # 1 · presence
    for name in REQUIRED:
        if not (DOC_DIR / name).is_file():
            fails.append(f"missing public/documentation/{name}")
    if fails:
        for f in fails:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1

    pdf = DOC_DIR / "README.pdf"

    try:
        import fitz  # noqa: F401
    except ImportError:
        print(
            "FAIL: PyMuPDF (fitz) required for the documentation gate.\n"
            "  install: python3 -m pip install --break-system-packages pymupdf",
            file=sys.stderr,
        )
        return 1

    # 2 · layout
    layout = _load_layout_validator()
    findings = layout.analyse(pdf)
    errors = [f for f in findings if f[0] == "ERROR"]
    for _sev, pno, kind, msg in errors:
        fails.append(f"layout p{pno} {kind}: {msg}")

    # 3 · accuracy regression guard
    import fitz

    doc = fitz.open(pdf)
    full = _normalise("\n".join(page.get_text() for page in doc))
    doc.close()
    for phrase in FORBIDDEN_PHRASES:
        if _normalise(phrase) in full:
            fails.append(f"forbidden stale claim present in README.pdf: {phrase!r}")

    # 4 · coherence — landing page advertises the real PDF hash
    sri = sri_sha256(pdf.read_bytes())
    index_html = (DOC_DIR / "index.html").read_text(encoding="utf-8")
    if sri not in index_html:
        fails.append(
            f"index.html does not show the current README.pdf hash ({sri}); "
            "re-run generate_documentation.py"
        )

    if fails:
        for f in fails:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1

    print("OK: /documentation/ surface verified (layout clean, no stale claims, hash coherent).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
