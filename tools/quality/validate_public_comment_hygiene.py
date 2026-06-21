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

Shape (deep module, small interface). The filesystem is the one injected seam —
`Repo(root)` — so the scan runs over a fixture repo with no monkeypatching.
`evaluate(repo)` is the pure compute path returning a Result; `main()` is the
only adapter that prints/exits. Public-tree knowledge (the "public/" prefix,
recursive walks) lives here in the validator, not on Repo, and the rendered
findings stay public-relative for byte-identical output.
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


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fails


# named accessor over the shared Repo seam. the public-tree knowledge (the
# "public/" prefix, recursive walks) lives here in the validator, not on Repo.
def _public_files(repo: Repo) -> list[str]:
    """public-relative posix paths of every file under public/, sorted —
    the recursive walk the original gate ran with ROOT.rglob('*')."""
    prefix = "public/"
    return [rel[len(prefix) :] for rel in repo.glob(f"{prefix}**/*")]


def scan_file(repo: Repo, rel: str) -> list[tuple[int, str, str]]:
    """scan one public-relative file for strict tokens. returns
    (line_no, token, line) findings; honours the allowlists verbatim."""
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
        text = repo.read(f"public/{rel}")
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


# ---------------------------------------------------------------------------
# evaluate — the compute interface. one call, one Result, over the injected
# Repo. this is the test surface; it never prints or exits.
# ---------------------------------------------------------------------------
def evaluate(repo: Repo) -> Result:
    r = Result()
    for rel in _public_files(repo):
        if not rel.endswith(SCAN_SUFFIXES):
            continue
        for line_no, tok, line in scan_file(repo, rel):
            r.fails.append(f"    {rel}:{line_no} → {tok!r} in: {line[:140]}")
    return r


# ---------------------------------------------------------------------------
# main — the side-effecting adapter. evaluates, renders, returns exit code.
# the only place stdout and exit codes live. reproduces the original output.
# ---------------------------------------------------------------------------
def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    if not (repo_root / "public").is_dir():
        print(f"FAIL: public root not found at {repo_root / 'public'}")
        return 1
    r = evaluate(repo)
    if r.fails:
        print(f"  FAIL: public-comment-hygiene — {len(r.fails)} leak(s):")
        for line in r.fails[:40]:
            print(line)
        if len(r.fails) > 40:
            print(f"    … {len(r.fails) - 40} more")
        return 1
    print("  OK: public-comment-hygiene — no internal-name leaks in deployed assets")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
