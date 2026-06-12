#!/usr/bin/env python3
"""validate_badges.py — blocking check for the local SVG trust marks.

Fails when:
  - a badge declared in badges.json is missing or stale against
    generator output (the SVGs are committed artefacts of the metadata);
  - any badge SVG contains a script, a remote reference, or an external
    badge-service host;
  - proof-strip.svg is missing;
  - any badge SVG lacks the <title> + <desc> accessibility pair;
  - README.md, SECURITY.md, CONTRIBUTING.md or CODE_OF_CONDUCT.md
    reference an external badge service.

Exit 0 = green; exit 1 = block.

Usage:
    python3 tools/badges/validate_badges.py
"""

import json
import re
import subprocess
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
from paths import REPO_ROOT, TOOLS_DIR

BADGE_DIR = REPO_ROOT / "metadata" / "badges"
DATA_PATH = BADGE_DIR / "badges.json"
GENERATOR = TOOLS_DIR / "badges" / "generate_badges.py"

EXTERNAL_SERVICES = re.compile(r"shields\.io|img\.shields|badgen|badge\.fury", re.I)
# the SVG namespace declaration is an identifier, not a fetch — every
# other URL, script or image reference inside a badge is forbidden.
XMLNS = re.compile(r'\bxmlns(?::\w+)?="http://www\.w3\.org/[^"]*"')
REMOTE_REF = re.compile(r"https?://|<script|xlink:href|<image", re.I)

GOVERNANCE_FILES = ("README.md", "SECURITY.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md")


def main() -> int:
    fails: list[str] = []

    if not DATA_PATH.is_file():
        print("FAIL: metadata/badges/badges.json missing")
        return 1
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    declared = [m["filename"] for m in data["marks"]] + [data["proof_strip"]["filename"]]

    # presence + staleness in one pass: the generator's --check mode
    # re-renders from badges.json and diffs against the committed files.
    res = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"], capture_output=True, text=True
    )
    if res.returncode != 0:
        fails.append("generator --check reports drift:\n    " + res.stdout.strip())

    for filename in declared:
        path = BADGE_DIR / filename
        if not path.is_file():
            fails.append(f"metadata/badges/{filename} missing")
            continue
        svg = path.read_text(encoding="utf-8")
        if EXTERNAL_SERVICES.search(svg):
            fails.append(f"{filename}: references an external badge service")
        if REMOTE_REF.search(XMLNS.sub("", svg)):
            fails.append(f"{filename}: contains a script or remote reference")
        if "<title>" not in svg or "<desc>" not in svg:
            fails.append(f"{filename}: missing <title> or <desc>")

    for name in GOVERNANCE_FILES:
        path = REPO_ROOT / name
        if not path.is_file():
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if EXTERNAL_SERVICES.search(line):
                fails.append(f"{name}:{i}: references an external badge service")

    if fails:
        print(f"FAIL: {len(fails)} local-badge issue(s):")
        for f in fails[:20]:
            print(f"  {f}")
        return 1
    print(
        f"OK: {len(declared)} local badge SVGs present, fresh, self-contained; "
        "no external badge services in governance files"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
