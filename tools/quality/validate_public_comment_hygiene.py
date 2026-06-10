#!/usr/bin/env python3
"""validate_public_comment_hygiene.py — block deployed assets from
leaking internal build-pipeline names.

Goal
----
The public site is part of the artefact. Generated CSS, JS, HTML and
JSON-LD must read as one author rather than betraying the build
pipeline behind them. This gate scans deployed bytes for explicit
internal names and fails the build if any are found in non-allowlisted
files.

Strict tokens (cause failure in any non-allowlisted public file)
- tools/
- generate_site.py
- generate_sw.py
- generate_source_view.py
- generate_integrity.py
- generate_verification_map.py
- generate_sri.py
- inline_checks.py
- predeploy_check.py (historical name of inline_checks.py)
- generated_by

Softer words (predeploy / pipeline / swept / build script) are NOT
checked here — they remain acceptable in changelog and operational
prose, where they belong.

Allowlist
- public/changelog.txt           — editorial archive of the project
- public/source/changelog.txt.txt — its source mirror
- public/source/htaccess.txt     — literal mirror of the server config
- public/source/source-manifest.json — internal manifest metadata

Quiet on success, precise on failure.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2] / "public"

STRICT_TOKENS = [
    "tools/",
    "generate_site.py",
    "generate_sw.py",
    "generate_source_view.py",
    "generate_integrity.py",
    "generate_verification_map.py",
    "generate_sri.py",
    "inline_checks.py",
    # historical name of inline_checks.py — kept so the retired name
    # never resurfaces in public bytes (frozen-archive HTML is still
    # scanned; only non-HTML archive bodies are skipped).
    "predeploy_check.py",
    "generated_by",
]

SCAN_SUFFIXES = (
    ".html",
    ".css",
    ".js",
    ".webmanifest",
    ".json",
    ".txt",
)

ALLOWLIST_RELATIVE = {
    # editorial archive — operational language belongs here.
    "changelog.txt",
    "source/changelog.txt.txt",
    # literal mirrors of internal documents (server config, build
    # manifests).
    "source/htaccess.txt",
    "source/source-manifest.json",
    "source/source-manifest.json.txt",
    # /source/ asset mirrors that intentionally expose authored
    # source. the whole point is editorial transparency; the authored
    # comments document the build from inside the source.
    "source/styles.css.txt",
    "source/print.css.txt",
    "source/fonts-full.css.txt",
    "source/theme.js.txt",
    "source/sw-register.js.txt",
    "source/reveal.js.txt",
    "source/verify-modal.js.txt",
    "source/copy.js.txt",
    "source/edition.js.txt",
    "source/overlay.js.txt",
    "source/fonts.js.txt",
    # /local/ device-console diagnostics module; the authored header
    # documents the templates/local.template.js → public/js/local.js
    # generator path for editorial transparency, same as the other
    # /js/*.js mirrors above.
    "source/local.js.txt",
    # the public documentation README — its entire purpose is to document
    # the build pipeline (tools/build.sh, tools/gate.py, …) for a public
    # reader. naming the machinery here is the deliverable, not a leak; the
    # repository is being prepared for an open-source release.
    "documentation/README.txt",
}

# Path-prefix allowlist. previously editorial/ was exempt because the
# copy-review documents listed `tools/build/copy/strings.json` as the source
# of each entry. those references have been rewritten to "editorial
# copy register" so no exemption is required.
ALLOWLIST_PREFIXES: tuple[str, ...] = ()

# Per-file fragment allowlist. some banners legitimately embed paths
# that are public-architectural rather than build-internal. the page
# provenance record (tp-page-record + comment) on machine-assembled
# surfaces names its generator module deliberately — the repository is
# public and the generator path resolves to a public GitHub URL, so
# the reference is provenance, not leakage. only the record's own
# lines are exempt; any other tools/ mention still fails.
_PROVENANCE_FRAGMENTS = {
    '"sourcePath": "tools/build/generate_',
    "blob/main/tools/build/generate_",
}
FRAGMENT_ALLOWLIST: dict[str, set[str]] = {
    "documentation/index.html": _PROVENANCE_FRAGMENTS,
    "tests/index.html": _PROVENANCE_FRAGMENTS,
    "source/index.html": _PROVENANCE_FRAGMENTS,
    "source/view/index.html": _PROVENANCE_FRAGMENTS,
    # /source/ mirrors of the two machine-assembled pages above carry
    # the same record bytes.
    "source/documentation/index.html.txt": _PROVENANCE_FRAGMENTS,
    "source/tests/index.html.txt": _PROVENANCE_FRAGMENTS,
}


def relpath(p: pathlib.Path) -> str:
    return str(p.relative_to(ROOT)).replace("\\", "/")


def scan_file(path: pathlib.Path) -> list[tuple[int, str, str]]:
    rel = relpath(path)
    if rel in ALLOWLIST_RELATIVE:
        return []
    if any(rel.startswith(pref) for pref in ALLOWLIST_PREFIXES):
        return []
    # skip release archives + signatures + binary detached signatures.
    if rel.startswith("integrity/releases/") and not rel.endswith(".html"):
        return []
    if rel.endswith((".sig", ".sha256", ".asc", ".gz", ".zip", ".docx", ".pdf")):
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    findings: list[tuple[int, str, str]] = []
    fragment_allowed = FRAGMENT_ALLOWLIST.get(rel, set())
    for tok in STRICT_TOKENS:
        for m in re.finditer(re.escape(tok), text):
            line_no = text.count("\n", 0, m.start()) + 1
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.end())
            if line_end < 0:
                line_end = len(text)
            line = text[line_start:line_end]
            if any(frag in line for frag in fragment_allowed):
                continue
            findings.append((line_no, tok, line.strip()))
    return findings


def main() -> int:
    if not ROOT.is_dir():
        print(f"FAIL: public root not found at {ROOT}")
        return 1
    failures: list[tuple[str, int, str, str]] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        if not str(path).endswith(SCAN_SUFFIXES):
            continue
        for line_no, tok, line in scan_file(path):
            failures.append((relpath(path), line_no, tok, line))
    if failures:
        print(f"  FAIL: public-comment-hygiene — {len(failures)} leak(s):")
        for rel, line_no, tok, line in failures[:40]:
            print(f"    {rel}:{line_no} → {tok!r} in: {line[:140]}")
        if len(failures) > 40:
            print(f"    … {len(failures) - 40} more")
        return 1
    print("  OK: public-comment-hygiene — no internal-name leaks in deployed assets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
