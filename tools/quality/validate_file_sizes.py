#!/usr/bin/env python3
"""validate_file_sizes.py — cross-check every recorded file size against disk.

phase a/b/c shipped a unified file-metadata manifest plus per-entry
size fields across source-manifest and verification-data. this
validator is the gate that keeps those numbers honest: every
displayed or recorded size value must equal the actual filesystem
bytes of the file it claims to describe.

checks:
  1. file-metadata.json: every entry's `bytes` equals disk st_size and
     `size_human_en` / `size_human_fr` equal humanise_bytes() output.
  2. source-manifest.json: every entry's `size` equals the canonical
     live file (live_path), `mirror_bytes` equals the .txt mirror, and
     both human labels match the fmt_size compat formatter.
  3. verify/verification-data.js: every route's `size_bytes` equals
     the on-disk size of its file (label format is historical and not
     enforced).
  4. no hardcoded KB/MB/Ko/Mo literals in homepage print-evidence
     chip context (hard error); other prose mentions of byte literals
     in html are reported as warnings only.

exit 0 = every size on disk; warnings allowed.
exit 1 = at least one hard mismatch.
"""

import json
import pathlib
import re
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
from paths import PUBLIC_DIR as ROOT
from script_blocks import strip_script_blocks
from sizes import humanise_bytes

# ── helpers ─────────────────────────────────────────────────────


def _fmt_size_compat(n: int) -> str:
    """mirror generate_source_view.fmt_size — short "n b" form below
    1024, otherwise the unified humanise_bytes(en) output. this keeps
    the formatter used by source-manifest decoupled from the en/fr
    helpers used by file-metadata."""
    if n < 1024:
        return f"{n} B"
    return humanise_bytes(n, lang="en")


def _read_json(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8"))


# ── 1. file-metadata.json ───────────────────────────────────────


def check_file_metadata(errors: list, oks: list) -> None:
    path = ROOT / "file-metadata.json"
    if not path.exists():
        errors.append("file-metadata.json: file missing")
        return
    try:
        data = _read_json(path)
    except json.JSONDecodeError as e:
        errors.append(f"file-metadata.json: invalid JSON ({e})")
        return
    files = data.get("files") or {}
    if not isinstance(files, dict):
        errors.append("file-metadata.json: missing 'files' dict")
        return
    bad = 0
    for rel, entry in files.items():
        disk = ROOT / rel
        if not disk.is_file():
            errors.append(f"file-metadata.json: {rel} listed but missing on disk")
            bad += 1
            continue
        recorded = entry.get("bytes")
        actual = disk.stat().st_size
        if recorded != actual:
            errors.append(f"file-metadata.json: /{rel} bytes={recorded} but disk={actual}")
            bad += 1
            continue
        # human labels are pure functions of the byte count.
        for lang, key in (("en", "size_human_en"), ("fr", "size_human_fr")):
            recorded_label = entry.get(key)
            expected_label = humanise_bytes(actual, lang=lang)
            if recorded_label != expected_label:
                errors.append(
                    f"file-metadata.json: /{rel} {key}={recorded_label!r} "
                    f"but humanise_bytes({actual}, {lang!r})={expected_label!r}"
                )
                bad += 1
    if bad == 0:
        oks.append(f"file-metadata.json: {len(files)} entries; bytes + human labels match disk")


# ── 2. source-manifest.json ─────────────────────────────────────


def check_source_manifest(errors: list, oks: list) -> None:
    path = ROOT / "source" / "source-manifest.json"
    if not path.exists():
        errors.append("source/source-manifest.json: file missing")
        return
    try:
        data = _read_json(path)
    except json.JSONDecodeError as e:
        errors.append(f"source/source-manifest.json: invalid JSON ({e})")
        return
    entries = data.get("files") or []
    if not isinstance(entries, list):
        errors.append("source/source-manifest.json: 'files' is not a list")
        return
    bad = 0
    for entry in entries:
        name = entry.get("name") or entry.get("display_name") or "<unnamed>"
        live_path = entry.get("live_path") or ""
        # canonical live file: strip leading slash, resolve under public/.
        if live_path:
            live = ROOT / live_path.lstrip("/")
            recorded_size = entry.get("size")
            if not live.is_file():
                errors.append(f"source-manifest.json: {name} live_path {live_path} missing on disk")
                bad += 1
            else:
                actual = live.stat().st_size
                if recorded_size != actual:
                    errors.append(
                        f"source-manifest.json: {name} size={recorded_size} "
                        f"but disk({live_path})={actual}"
                    )
                    bad += 1
                else:
                    expected_label = _fmt_size_compat(actual)
                    if entry.get("size_human") != expected_label:
                        errors.append(
                            f"source-manifest.json: {name} size_human="
                            f"{entry.get('size_human')!r} but expected "
                            f"{expected_label!r}"
                        )
                        bad += 1
        # mirror file: /source/<name>
        mirror_rel = entry.get("name")
        if mirror_rel:
            mirror_path = ROOT / "source" / mirror_rel
            recorded_mirror = entry.get("mirror_bytes")
            if not mirror_path.is_file():
                errors.append(
                    f"source-manifest.json: {name} mirror source/{mirror_rel} missing on disk"
                )
                bad += 1
            else:
                actual_mirror = mirror_path.stat().st_size
                if recorded_mirror != actual_mirror:
                    errors.append(
                        f"source-manifest.json: {name} mirror_bytes="
                        f"{recorded_mirror} but disk(source/{mirror_rel})="
                        f"{actual_mirror}"
                    )
                    bad += 1
                else:
                    expected_label = _fmt_size_compat(actual_mirror)
                    if entry.get("mirror_size_human") != expected_label:
                        errors.append(
                            f"source-manifest.json: {name} mirror_size_human="
                            f"{entry.get('mirror_size_human')!r} but expected "
                            f"{expected_label!r}"
                        )
                        bad += 1
    if bad == 0:
        oks.append(f"source-manifest.json: {len(entries)} entries (canonical + mirror sizes match)")


# ── 3. verify/verification-data.js ──────────────────────────────

_VD_OBJECT_RE = re.compile(
    r"window\.TP_VERIFICATION_MAP\s*=\s*(\{.*?\});\s*$",
    re.S,
)


def check_verification_data(errors: list, oks: list) -> None:
    path = ROOT / "verify" / "verification-data.js"
    if not path.exists():
        # absent verification data is not a hard error here; the
        # validate_edition + freshness gates own its presence story.
        return
    text = path.read_text(encoding="utf-8")
    m = _VD_OBJECT_RE.search(text)
    if not m:
        errors.append(
            "verify/verification-data.js: could not locate "
            "window.TP_VERIFICATION_MAP object literal"
        )
        return
    try:
        records = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        errors.append(f"verify/verification-data.js: object literal not valid JSON ({e})")
        return
    if not isinstance(records, dict):
        errors.append("verify/verification-data.js: TP_VERIFICATION_MAP is not an object")
        return
    bad = 0
    for route, rec in records.items():
        if not isinstance(rec, dict):
            continue
        recorded = rec.get("size_bytes")
        # `manifest_entry_path` carries the on-disk path with leading slash;
        # fall back to `path` if absent.
        rel = (rec.get("manifest_entry_path") or rec.get("path") or "").lstrip("/")
        if not rel:
            continue
        disk = ROOT / rel
        if not disk.is_file():
            errors.append(f"verify/verification-data.js: {route} → {rel} missing on disk")
            bad += 1
            continue
        actual = disk.stat().st_size
        if recorded != actual:
            errors.append(
                f"verify/verification-data.js: {route} size_bytes={recorded} "
                f"but disk({rel})={actual}"
            )
            bad += 1
    if bad == 0:
        oks.append(f"verify/verification-data.js: {len(records)} routes (size_bytes match disk)")


# ── 4. hardcoded KB/MB/Ko/Mo literals in html ───────────────────

# matches "27 kb", "27.0 kb", "27,0 ko" — both english and french units.
# the optional whitespace between number and unit is `\s?` to allow
# nbsp-free or thin-space markup; we strip nbsp before scanning.
_BYTE_LITERAL_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s?(?:KB|MB|Ko|Mo)\b")

# strip <script> blocks and html comments so editorial prose is the
# only surface scanned.
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)


def _scan_html_for_literals(text: str):
    """yield (line_number, match_text) for every byte-literal in
    visible content. drops script blocks and comments first."""
    cleaned = strip_script_blocks(text)
    cleaned = _HTML_COMMENT_RE.sub("", cleaned)
    # also drop nbsp so "5 kb" reads as "5 kb" before the regex.
    cleaned = cleaned.replace(" ", " ")
    for m in _BYTE_LITERAL_RE.finditer(cleaned):
        line = cleaned.count("\n", 0, m.start()) + 1
        yield line, m.group(0)


def check_html_byte_literals(errors: list, warnings: list, oks: list) -> None:
    fails_chip = 0
    found_anywhere = 0
    for html in sorted(ROOT.rglob("*.html")):
        rel = html.relative_to(ROOT).as_posix()
        # frozen-archive html under /integrity/releases/ is excluded
        # by design — those bytes are immutable historical snapshots.
        if rel.startswith("integrity/releases/"):
            continue
        try:
            text = html.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line, literal in _scan_html_for_literals(text):
            found_anywhere += 1
            # find the print-evidence chip context: the brief calls out
            # the previous homepage "28 kb" chip specifically. detect by
            # looking at the surrounding 200 chars for the class name.
            start = max(0, text.find(literal) - 200)
            window = text[start : text.find(literal) + len(literal) + 100]
            if "print-evidence" in window:
                errors.append(
                    f"{rel}:{line} print-evidence chip contains byte "
                    f"literal {literal!r} — chip must say 'Edition <date>' only"
                )
                fails_chip += 1
            else:
                warnings.append(f"{rel}: prose byte literal {literal!r} near line {line}")
    if fails_chip == 0:
        oks.append("no hardcoded KB/MB literals in print-evidence chips")


# ── main ────────────────────────────────────────────────────────


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    oks: list[str] = []

    print("SIZE CHECK")

    check_file_metadata(errors, oks)
    check_source_manifest(errors, oks)
    check_verification_data(errors, oks)
    check_html_byte_literals(errors, warnings, oks)

    for line in oks:
        print(f"OK {line}")
    for line in warnings:
        print(f"WARN {line}")
    for line in errors:
        print(f"ERROR {line}")

    n_err = len(errors)
    n_warn = len(warnings)
    print(
        f"RESULT: {n_err} error{'s' if n_err != 1 else ''}, "
        f"{n_warn} warning{'s' if n_warn != 1 else ''}"
    )
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
