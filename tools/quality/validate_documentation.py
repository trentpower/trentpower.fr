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

Shape (deep module, small interface). The filesystem is the one injected seam:
`Repo(root)` reads the landing-page HTML and the PDF bytes, and `.root` resolves
the on-disk PDF path that fitz needs (it opens a file, not bytes). fitz and the
dynamically-loaded layout validator stay direct imports — they are libraries,
not seams. Compute (`evaluate`) returns a Result and never prints or exits;
`main()` is the only side-effecting adapter, and it owns the fitz-absent
environment precondition.
"""

from __future__ import annotations

import importlib.util
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
from hashing import sri_sha256  # noqa: E402
from paths import PUBLIC_DIR, REPO_ROOT, TOOLS_DIR  # noqa: E402
from repo import Repo  # noqa: E402  (shared filesystem evidence seam)

# repo-relative locations of the inputs (resolved through the Repo seam).
DOC_DIR_REL = "public/documentation"
REQUIRED = ("index.html", "README.pdf", "README.txt")

# kept for any caller that referenced the absolute documentation dir.
DOC_DIR = PUBLIC_DIR / "documentation"

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
        " ": " ",
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


# ---------------------------------------------------------------------------
# Result — the value that flows through the interface. evaluate() produces it;
# main() renders it. tests assert on Result, never on stdout.
# ---------------------------------------------------------------------------
@dataclass
class Result:
    fails: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fails


# ---------------------------------------------------------------------------
# evaluate — the compute interface. one call, one Result, over the injected
# Repo. assumes fitz is importable (main() enforces that precondition first).
# ---------------------------------------------------------------------------
def evaluate(repo: Repo) -> Result:
    r = Result()

    # 1 · presence
    for name in REQUIRED:
        if not repo.is_file(f"{DOC_DIR_REL}/{name}"):
            r.fails.append(f"missing public/documentation/{name}")
    if r.fails:
        return r

    pdf_rel = f"{DOC_DIR_REL}/README.pdf"
    # fitz opens a file, not bytes — resolve the on-disk path off the seam root.
    pdf = repo.root / pdf_rel

    # 2 · layout
    layout = _load_layout_validator()
    findings = layout.analyse(pdf)
    errors = [f for f in findings if f[0] == "ERROR"]
    for _sev, pno, kind, msg in errors:
        r.fails.append(f"layout p{pno} {kind}: {msg}")

    # 3 · accuracy regression guard
    import fitz

    doc = fitz.open(pdf)
    full = _normalise("\n".join(page.get_text() for page in doc))
    doc.close()
    for phrase in FORBIDDEN_PHRASES:
        if _normalise(phrase) in full:
            r.fails.append(f"forbidden stale claim present in README.pdf: {phrase!r}")

    # 4 · coherence — landing page advertises the real PDF hash
    sri = sri_sha256((repo.root / pdf_rel).read_bytes())
    index_html = repo.read(f"{DOC_DIR_REL}/index.html")
    if sri not in index_html:
        r.fails.append(
            f"index.html does not show the current README.pdf hash ({sri}); "
            "re-run generate_documentation.py"
        )

    return r


# ---------------------------------------------------------------------------
# main — the side-effecting adapter. enforces the fitz precondition, evaluates,
# renders, returns exit code. the only place stdout and exit codes live.
# ---------------------------------------------------------------------------
def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)

    # presence is checked inside evaluate, but the fitz precondition must hold
    # before evaluate can extract text. mirror the original ordering: presence
    # first, then fitz, then the rest — so a missing file still wins.
    for name in REQUIRED:
        if not repo.is_file(f"{DOC_DIR_REL}/{name}"):
            r = evaluate(repo)  # re-derives the same presence fails
            for f in r.fails:
                print(f"FAIL: {f}", file=sys.stderr)
            return 1

    try:
        import fitz  # noqa: F401
    except ImportError:
        print(
            "FAIL: PyMuPDF (fitz) required for the documentation gate.\n"
            "  install: python3 -m pip install --break-system-packages pymupdf",
            file=sys.stderr,
        )
        return 1

    r = evaluate(repo)
    if r.fails:
        for f in r.fails:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1

    print("OK: /documentation/ surface verified (layout clean, no stale claims, hash coherent).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
