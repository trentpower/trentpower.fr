#!/usr/bin/env python3
"""tools/detect_edition_changes.py — machine-assisted changelog draft.

Compares the current public/ tree against the last edition's commit
(or HEAD~10 if no edition tags / commit history). Emits a draft
summary to reports/changelog-draft.txt that the operator can use as
raw material when curating the canonical public/changelog.txt entry.

Editorial control is preserved: this script never touches the public
changelog. It is read-only over the public tree, write-only into
reports/. The build pipeline runs it to generate the draft; humans
write the actual entry.

A separate freshness gate (predeploy step 15) warns if
identity_canonical.edition has bumped past the topmost changelog
date — that is the signal to expand the draft into editorial prose.

Format: matches the existing changelog.txt rhythm: a date heading +
a 57-char rule, then a short summary block. The draft is intentionally
terse; humans elaborate.
"""

import re
import subprocess
import sys
from datetime import UTC, datetime

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
from paths import IDENTITY_CANONICAL, PUBLIC_DIR, REPO_ROOT  # noqa: E402

OUTPUT = REPO_ROOT / "reports" / "changelog-draft.txt"
CHANGELOG = PUBLIC_DIR / "changelog.txt"


def _git(*args) -> str:
    r = subprocess.run(["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def _last_edition_ref() -> str | None:
    """Find the most recent commit that mentions an edition date in
    its subject. Falls back to HEAD~20 if none."""
    log = _git(
        "log", "--all", "-i", "--grep=^Edition\\|edition.*\\d{4}-\\d{2}-\\d{2}", "--format=%H %s"
    )
    for line in log.splitlines():
        if line.strip():
            return line.split(maxsplit=1)[0]
    # fall back to ~20 commits ago.
    h = _git("rev-parse", "HEAD~20").strip()
    return h or None


def _changes_since(ref: str) -> tuple[list[str], list[str], list[str]]:
    """Return (added, modified, deleted) public-path lists vs `ref`."""
    if not ref:
        return ([], [], [])
    raw = _git("diff", "--name-status", ref, "--", "public/")
    added: list[str] = []
    modified: list[str] = []
    deleted: list[str] = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if not parts or len(parts) < 2:
            continue
        status = parts[0]
        # Renames/copies present as R<score>\told\tnew or C<score>\told\tnew
        if status[0] in ("R", "C"):
            if len(parts) >= 3:
                deleted.append(parts[1])
                added.append(parts[2])
            continue
        path = parts[1]
        if status == "A":
            added.append(path)
        elif status == "D":
            deleted.append(path)
        elif status == "M":
            modified.append(path)
    return (sorted(added), sorted(modified), sorted(deleted))


def _topmost_changelog_date() -> str:
    if not CHANGELOG.is_file():
        return ""
    text = CHANGELOG.read_text(encoding="utf-8")
    m = re.search(r"^(\d{4}-\d{2}-\d{2})\b", text, re.MULTILINE)
    return m.group(1) if m else ""


def _trim_to_public_relative(paths: list[str]) -> list[str]:
    """Strip leading 'public/' and skip the noisy generated artefacts
    that are byte-rotation rather than editorial change."""
    out: list[str] = []
    NOISY = {
        "integrity.json",
        "integrity.json.sig",
        "site-metadata.json",
        "verify/verification-data.js",
    }
    NOISY_PREFIX = (
        "integrity/releases/2026-",  # release archives rotate per build
        "source/",  # generated mirrors
    )
    for p in paths:
        if not p.startswith("public/"):
            continue
        rel = p[len("public/") :]
        if rel in NOISY:
            continue
        if any(rel.startswith(pref) for pref in NOISY_PREFIX):
            continue
        out.append(rel)
    return out


def main() -> int:
    if not IDENTITY_CANONICAL.is_file():
        print("FAIL: tools/identity_canonical.json missing", file=sys.stderr)
        return 1
    import json

    edition = json.loads(IDENTITY_CANONICAL.read_text(encoding="utf-8")).get("edition", "")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    today_utc = datetime.now(UTC).strftime("%Y-%m-%d")

    ref = _last_edition_ref()
    added, modified, deleted = _changes_since(ref) if ref else ([], [], [])
    added = _trim_to_public_relative(added)
    modified = _trim_to_public_relative(modified)
    deleted = _trim_to_public_relative(deleted)

    topmost = _topmost_changelog_date()
    edition_drift = bool(edition and topmost and edition > topmost)

    lines: list[str] = []
    a = lines.append

    a(f"changelog draft — generated {today_utc}")
    a("=" * 50)
    a("")
    a(f"  current edition          : {edition or '(unknown)'}")
    a(f"  topmost changelog date   : {topmost or '(none)'}")
    a(f"  edition / changelog drift: {'yes' if edition_drift else 'no'}")
    a(f"  diff base                : {ref[:12] + '…' if ref else '(none)'}")
    a("")
    a("This file is build machinery, not the canonical changelog. The")
    a("editorial entry lives at public/changelog.txt. Use the lists")
    a("below as raw material; collapse them into one human-readable")
    a("paragraph in the same register as the existing entries.")
    a("")
    a("If `edition / changelog drift = yes`, the canonical edition has")
    a("advanced past the topmost changelog entry — an entry is owed.")
    a("")

    def _section(title: str, paths: list[str]):
        a(title)
        a("-" * len(title))
        if paths:
            for p in paths[:30]:
                a(f"  - {p}")
            if len(paths) > 30:
                a(f"  … and {len(paths) - 30} more")
        else:
            a("  (none)")
        a("")

    _section(f"Added ({len(added)})", added)
    _section(f"Modified ({len(modified)})", modified)
    _section(f"Deleted ({len(deleted)})", deleted)

    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  → {OUTPUT.relative_to(REPO_ROOT)}")
    if edition_drift:
        print(
            f"  ⚠ edition {edition} > topmost changelog {topmost} "
            f"— add an entry to public/changelog.txt"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
