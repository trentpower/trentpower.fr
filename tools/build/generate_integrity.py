"""
generate_integrity.py · Build /integrity.json manifest.

Policy:
integrity.json is a public manifest of intentional fetchable assets only.
It must not include licences, invoices, local audits, backups, source
tooling, generator inputs, private notes, stale snapshots, deployment
artefacts, credentials, or files from the stale inner htdocs directory.

Manifest contents (intended public fetchable assets):
- active HTML pages
- active CSS, JS (clean filenames)
- active fonts (clean filenames)
- service worker
- robots.txt, sitemap.xml, llms.txt, humans.txt, security.txt
- .well-known/* public files
- public images / icons
- architecture SVG assets
- frozen archive release pages and their local assets

Excluded (source-only, private, or duplicate-rollback):
- integrity.json itself and integrity.json.sig (signing target / circular)
- identity_canonical.json (canonical source · local-only)
- i18n/strings.json (inlined into app.js at build; not fetched at runtime)
- generate_*.py, *.template.js, *.sh, *.md (tooling and notes)
- .htaccess (server config · not in the public payload)
- README.txt, .user.ini (server-side documentation)
- licence PDFs, invoices, order documents
- _audit_*.md (local-only audit artefacts)
- CHANGES.md (local-only release log)
- backups, .bak files, .DS_Store
- old numbered rollback assets that the active site no longer references
- the stale inner htdocs/htdocs directory
"""

import json
import os

# walk the public web root rather than the tools/ directory.
# os.chdir() so all subsequent relative paths in this script resolve
# inside public/, matching the historical behaviour when this script
# lived in htdocs/.
import sys as _sys
from datetime import UTC, datetime

_sys.path.insert(
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
import public_tree  # shared public-surface walker + exclusion policy
from hashing import sri_sha256
from paths import PUBLIC_DIR as _PATHS_PUBLIC_DIR

os.chdir(_PATHS_PUBLIC_DIR)
ROOT = "."

# the public-surface exclusion policy (which files are hashed) now lives in
# public_tree.py — the single source of truth shared with
# generate_file_metadata.py, so the signed manifest and its size sidecar walk
# exactly the same set and cannot drift apart. the HARD_FAIL guard below stays
# here: it is a fail-loud security gate specific to integrity generation, not
# part of the walker's filter.

# Fail-loud guard: any of these files inside public/ is a build error.
# the hardening brief calls this out explicitly: forbidden public files
# must abort the build, not be silently skipped. predeploy step 10
# repeats the same gate as belt-and-braces.
HARD_FAIL_NAMES = {
    ".user.ini",
    ".env",
    ".htpasswd",
    "id_ed25519",
    "id_ed25519.pub",
    "Thumbs.db",
}
HARD_FAIL_DIRS = {".git", "private", "console_data", "node_modules"}
_violations = []
for _root, _dirs, _files in os.walk(ROOT):
    for _d in _dirs:
        if _d in HARD_FAIL_DIRS:
            _violations.append(os.path.join(_root, _d))
    for _f in _files:
        if _f in HARD_FAIL_NAMES:
            _violations.append(os.path.join(_root, _f))
if _violations:
    import sys as _sys_for_violations

    _sys_for_violations.stderr.write(
        f"FAIL: generate_integrity.py — {len(_violations)} forbidden public artefact(s):\n"
    )
    for _v in _violations:
        _sys_for_violations.stderr.write(f"  {_v}\n")
    _sys_for_violations.stderr.write(
        "       Remediation: remove from public/. Server-side files belong\n"
        "       under tools/server/; build-only files under tools/.\n"
    )
    _sys_for_violations.exit(1)

files = {}

# ROOT is "." (we chdir'd into public/ above), so the shared walker yields
# root-relative posix keys ("editorial/copy-review.md") — the exact manifest
# key format this script has always emitted.
for relpath, path in public_tree.iter_public_files(ROOT):
    with open(path, "rb") as f:
        content = f.read()
        files[relpath] = sri_sha256(content)

_identity_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "identity_canonical.json"
)
with open(_identity_path) as _idf:
    _identity = json.load(_idf)
_edition = _identity.get("edition")

manifest = {
    "site": "https://trentpower.fr",
    # editorial edition date from identity_canonical.json. distinct from
    # `generated` (the byte-mint date) so the footer edition slot reads
    # the editorial cycle rather than the build timestamp.
    "edition": _edition,
    # Date-resolution timestamp keeps integrity.json byte-stable across
    # multiple builds within the same day, which in turn keeps the
    # release archives (which embed integrity.json) deterministic.
    "generated": datetime.now(UTC).strftime("%Y-%m-%d"),
    "algorithm": "SHA-256",
    "files": dict(sorted(files.items())),
}

with open("integrity.json", "w") as f:
    json.dump(manifest, f, indent=2)
    f.write("\n")

print(f"{len(files)} files hashed")
