#!/usr/bin/env python3
"""prune_single_tree.py — remove the superseded single-tree page HTML.

Runs in build.sh right after render_pages.py has emitted the bilingual
/en/ and /fr/ trees. It deletes ONLY the old single-tree page documents
that the bilingual editions replace — surgically, file by file, never a
blanket directory wipe — because page HTML is interleaved with
language-neutral assets (verify.js, source-view.js, the /source/*.txt
mirrors, the frozen /integrity/releases/ archives) that must survive.

Root error pages (/403.html /404.html /500.html /maintenance.html) are
LEFT in place: they are the gate-path fallback for requests that match
neither /en/ nor /fr/ (see the .htaccess ErrorDocument routing).
"""

from __future__ import annotations

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
from paths import PUBLIC_DIR  # noqa: E402

# superseded single-tree page documents — the bilingual renderer now
# owns these surfaces under /en/ and /fr/.
SUPERSEDED_PAGES = [
    "privacy/index.html",
    "security/index.html",
    "security/acknowledgments/index.html",
    "integrity/index.html",
    "integrity/releases/index.html",
    "integrity/verify-locally/index.html",
    "verify/index.html",
    "source/index.html",
    "source/view/index.html",
]


def main() -> int:
    removed = 0
    for rel in SUPERSEDED_PAGES:
        p = PUBLIC_DIR / rel
        if p.is_file():
            p.unlink()
            removed += 1
    # drop any directory left empty by the prune (keeps the tree tidy;
    # never touches a directory that still holds assets or archives).
    for rel in SUPERSEDED_PAGES:
        d = (PUBLIC_DIR / rel).parent
        try:
            if d != PUBLIC_DIR and d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        except OSError:
            pass
    print(f"OK: pruned {removed} superseded single-tree page(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
