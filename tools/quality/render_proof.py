#!/usr/bin/env python3
"""render_proof.py — the source→committed-PDF hash binding for docs/pdf.

README.pdf is hand-rendered from docs/pdf/readme.html (pagedjs-cli + Chromium)
and committed; there is no reproducible source→PDF function, so the build cannot
"regenerate and diff" it (ADR-0003). What it CAN do is bind the committed PDF to
the exact source bytes that produced it: a small proof file recording the sha256
of the editorial HTML, of the tracked render assets, and of the PDF itself.

`docs/pdf/build.sh` calls `main()` after a successful render so the proof is
committed alongside the new PDF. `validate_docs_freshness.py` imports `compute()`
and compares — a mismatch is a WARNING (the source changed but the committed PDF
was not re-rendered), not a hard failure (the render is non-reproducible and the
public PDF's own hash is already gated by validate_documentation.py).

Licensed fonts (docs/pdf/fonts/) are deliberately excluded: they are fetched on
demand and are not tracked, so hashing them would be non-deterministic across a
fresh checkout. The asset set below is the tracked subset readme.html pulls in.

Shape: a single pure `compute(root) -> dict` plus a thin `main()` write adapter.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(
    0,
    str(next(_a for _a in Path(__file__).resolve().parents if _a.name == "tools") / "lib"),
)
from paths import REPO_ROOT  # noqa: E402

README_HTML_REL = "docs/pdf/readme.html"
PDF_REL = "README.pdf"
PROOF_REL = "docs/pdf/.render-proof.json"

# the tracked files readme.html + its stylesheets pull in. fonts/ is excluded on
# purpose (untracked, fetched on demand). keep sorted for a stable assets hash.
ASSET_RELS = (
    "docs/pdf/assets/terminal.png",
    "docs/pdf/guide.css",
    "docs/pdf/paper-noise.svg",
    "docs/pdf/print-paged.css",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "MISSING"


def compute(root: Path) -> dict:
    """The three hashes that bind the committed PDF to its source. Pure: reads
    files under `root`, returns a dict, never writes."""
    readme_html = _sha(root / README_HTML_REL)
    # assets hash = hash of the per-asset "rel:sha" lines, so the digest is
    # stable regardless of filesystem ordering and names a missing asset clearly.
    lines = "\n".join(f"{rel}:{_sha(root / rel)}" for rel in sorted(ASSET_RELS))
    assets = hashlib.sha256(lines.encode("utf-8")).hexdigest()
    pdf = _sha(root / PDF_REL)
    return {
        "readme_html_sha256": readme_html,
        "assets_sha256": assets,
        "pdf_sha256": pdf,
    }


def main(repo_root: Path = REPO_ROOT) -> int:  # pragma: no cover - thin write adapter
    proof = compute(repo_root)
    out = repo_root / PROOF_REL
    out.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {PROOF_REL}")
    for k, v in proof.items():
        print(f"  {k} = {v}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
