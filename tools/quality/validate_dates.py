#!/usr/bin/env python3
"""validate_dates.py — fail the build on any date drift between the
content-history-anchored manifest and the visible date surfaces.

Single source of truth: public/file-metadata.json["files"][rel]["modified_iso"].
Every active surface that prints a date — sitemap.xml <lastmod>, JSON-LD
"dateModified", security.txt Expires, integrity.json "generated" — is
cross-checked against the manifest. Documented exceptions live in
tools/date_overrides.json with a `reason` per leaf.

The /verify/ tree owns the word "Validated"/"Validé" by policy; any
other appearance of either word is a regression of the renamed
print-evidence chip ("Edition <date>") and fails this gate.

Unresolved {{lastmod:*}} / {{datemod:*}} placeholders are a missed
sweep step and fail the gate so the operator re-runs the build.

Exit 0 = every date surface matches the manifest (or a reasoned override).
Exit 1 = at least one drift; failing paths are printed.
"""

import datetime
import json
import re
import sys
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
from paths import IDENTITY_CANONICAL, PUBLIC_DIR, TOOLS_DIR  # noqa: E402

DATE_OVERRIDES = TOOLS_DIR / "config" / "date_overrides.json"
MANIFEST = PUBLIC_DIR / "file-metadata.json"
SITEMAP = PUBLIC_DIR / "sitemap.xml"
INTEGRITY = PUBLIC_DIR / "integrity.json"
SECURITY_TXT = PUBLIC_DIR / ".well-known" / "security.txt"

# frozen historical pages — pgp-signed release snapshots whose bytes
# (and embedded dates) must not be rewritten by the current build.
FROZEN_PREFIX = "integrity/releases/"

# build-output review documents that quote raw i18n source strings,
# including the literal "validated" key used elsewhere in the system.
# they are not editorial copy and are not in the published navigation,
# so the "validated outside /verify/" policy does not apply to them.
EDITORIAL_REVIEW_PREFIXES = (
    # editorial-copy-review (system b) retired; only copy-review remains.
    "editorial/copy-review",
)

# extensions walked by the placeholder sweep — anything else is unlikely
# to embed a build-time date token.
PLACEHOLDER_EXTS = {".html", ".xml", ".json", ".js", ".css", ".txt"}

# regex toolbox.
URL_BLOCK_RE = re.compile(r"<url>(.*?)</url>", re.S)
LOC_RE = re.compile(r"<loc>([^<]+)</loc>")
LASTMOD_RE = re.compile(r"<lastmod>([^<]+)</lastmod>")
DATEMOD_RE = re.compile(r'"dateModified"\s*:\s*"([^"]+)"')
VALIDATED_RE = re.compile(r"\b(Validated|Validé)\b")
PLACEHOLDER_RE = re.compile(r"\{\{(?:lastmod|datemod):")
ISO_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
EXPIRES_RE = re.compile(r"^Expires:\s*(\S+)\s*$", re.MULTILINE)


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _url_to_disk_path(url: str) -> str:
    """map a sitemap <loc> url to its on-disk relative path under public/.
    examples:
      https://trentpower.fr/             -> index.html
      https://trentpower.fr/privacy/     -> privacy/index.html
      https://trentpower.fr/foo.json     -> foo.json
      https://trentpower.fr/.well-known/security.txt -> .well-known/security.txt
    """
    m = re.match(r"^https?://[^/]+(/.*)$", url)
    path = m.group(1) if m else url
    if path == "/" or path == "":
        return "index.html"
    path = path.lstrip("/")
    if path.endswith("/"):
        return path + "index.html"
    return path


def _override_path_key(url: str) -> str:
    """sitemap overrides are keyed by the url-side path (with leading
    slash). examples:
      https://trentpower.fr/integrity.json.sig -> /integrity.json.sig
      https://trentpower.fr/                   -> /
    """
    m = re.match(r"^https?://[^/]+(/.*)$", url)
    return m.group(1) if m else url


def _resolve_override(entry, edition: str) -> str | None:
    """return the resolved date string for an override leaf, or None
    if the leaf is not a date-bearing object."""
    if not isinstance(entry, dict):
        return None
    date = entry.get("date")
    if not date:
        return None
    if date == "edition":
        return edition
    return date


def check_overrides_have_reasons(overrides: dict, fails: list, oks: list) -> None:
    """every leaf override (anything that's not a `_doc`/`_example`
    documentation entry) must carry a non-empty `reason` field. surfaces
    the contract that overrides explain themselves; an unreasoned
    override is a silent backdoor on the date-honesty story.
    """
    counts = {"published": 0, "modified": 0, "lastmod": 0, "expires": 0}
    for section in ("published", "modified", "lastmod", "expires"):
        block = overrides.get(section, {})
        if not isinstance(block, dict):
            continue
        for key, leaf in block.items():
            if key.startswith("_"):
                continue
            if isinstance(leaf, str):
                # short form for published: { "/": "2026-02-15" }. no
                # reason required; documented at the section level.
                counts[section] += 1
                continue
            if isinstance(leaf, dict):
                counts[section] += 1
                reason = leaf.get("reason", "")
                if not isinstance(reason, str) or not reason.strip():
                    fails.append(
                        f"date_overrides.json: {section}[{key}] missing non-empty 'reason'"
                    )
    oks.append(
        f"overrides: {counts['published']} published, {counts['modified']} modified, "
        f"{counts['lastmod']} lastmod, {counts['expires']} expires (all carry reason)"
    )


def check_sitemap(manifest: dict, overrides: dict, edition: str, fails: list, oks: list) -> None:
    """every <loc>/<lastmod> pair: lastmod must equal manifest.modified_iso
    or an explicit override declaration. files excluded from the manifest
    (integrity.json, site-metadata.json, integrity.json.sig) must declare
    a lastmod override so the date surface still has an audit trail.
    """
    if not SITEMAP.exists():
        fails.append("sitemap.xml: missing")
        return
    text = SITEMAP.read_text(encoding="utf-8")
    lastmod_overrides = overrides.get("lastmod", {})
    files = manifest.get("files", {})
    seen = 0
    for block in URL_BLOCK_RE.finditer(text):
        body = block.group(1)
        loc_m = LOC_RE.search(body)
        lm_m = LASTMOD_RE.search(body)
        if not (loc_m and lm_m):
            continue
        seen += 1
        url = loc_m.group(1).strip()
        actual = lm_m.group(1).strip()
        disk_rel = _url_to_disk_path(url)
        url_path = _override_path_key(url)

        expected = None
        source = None
        override_leaf = lastmod_overrides.get(url_path)
        if isinstance(override_leaf, dict) and override_leaf.get("date"):
            expected = _resolve_override(override_leaf, edition)
            source = "override"
        else:
            rec = files.get(disk_rel)
            if rec and rec.get("modified_iso"):
                expected = rec["modified_iso"]
                source = "manifest"

        if expected is None:
            fails.append(
                f"sitemap: <loc>{url}</loc> has no manifest entry "
                f"({disk_rel}) and no lastmod override — add an entry "
                f"to date_overrides.json.lastmod with a reason"
            )
            continue
        if actual != expected:
            fails.append(
                f"sitemap: <lastmod>{actual}</lastmod> for {url} but {source} says {expected}"
            )
    oks.append(f"sitemap.xml: {seen} URLs checked")


def _iter_active_html() -> list[Path]:
    """yield every .html file under public/ except frozen archive
    snapshots and the build-output editorial-review documents."""
    out: list[Path] = []
    for p in PUBLIC_DIR.rglob("*.html"):
        rel = p.relative_to(PUBLIC_DIR).as_posix()
        if rel.startswith(FROZEN_PREFIX):
            continue
        if rel.startswith(EDITORIAL_REVIEW_PREFIXES):
            continue
        out.append(p)
    return out


def check_jsonld_datemod(manifest: dict, fails: list, oks: list) -> None:
    """every json-ld dateModified prefix (YYYY-MM-DD) must equal the
    manifest's modified_iso for the same file. catches the bug-class
    where a per-page generator hardcodes the edition or a past date
    rather than emitting the {{datemod:<path>}} placeholder."""
    files = manifest.get("files", {})
    checked_files = 0
    checked_values = 0
    for p in _iter_active_html():
        rel = p.relative_to(PUBLIC_DIR).as_posix()
        text = p.read_text(encoding="utf-8")
        matches = list(DATEMOD_RE.finditer(text))
        if not matches:
            continue
        checked_files += 1
        rec = files.get(rel)
        expected = (rec or {}).get("modified_iso")
        for m in matches:
            checked_values += 1
            val = m.group(1)
            iso_m = ISO_DATE_RE.match(val)
            if not iso_m:
                fails.append(f"{rel}: dateModified={val!r} does not start with YYYY-MM-DD")
                continue
            prefix = iso_m.group(1)
            if expected is None:
                fails.append(
                    f"{rel}: dateModified={val} present but no manifest entry "
                    f"for this path — add the file to the manifest or fix the generator"
                )
                continue
            if prefix != expected:
                line = text.count("\n", 0, m.start()) + 1
                fails.append(
                    f"{rel}:{line} dateModified={val} (date prefix {prefix}) "
                    f"but manifest says {expected}"
                )
    oks.append(
        f"json-ld dateModified: {checked_values} value(s) across {checked_files} file(s) checked"
    )


def check_integrity_generated(fails: list, oks: list) -> None:
    """integrity.json.generated must not be in the future relative to
    today utc. catches a build clock skew that would otherwise mint a
    manifest dated tomorrow."""
    if not INTEGRITY.exists():
        fails.append("integrity.json: missing")
        return
    try:
        gen = _read_json(INTEGRITY).get("generated", "")
    except json.JSONDecodeError as e:
        fails.append(f"integrity.json: invalid JSON ({e})")
        return
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", gen):
        fails.append(f"integrity.json: generated={gen!r} is not YYYY-MM-DD")
        return
    today = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
    if gen > today:
        fails.append(f"integrity.json: generated={gen} is in the future (today UTC {today})")
        return
    oks.append(f"integrity.json: generated={gen} (today UTC {today})")


def check_no_placeholders(fails: list, oks: list) -> None:
    """no file under public/ may carry an unresolved {{lastmod:*}} or
    {{datemod:*}} token. the sweep pass in generate_file_metadata.py
    rewrites these against the manifest; survivors mean the sweep was
    skipped or a generator emitted a token after the sweep ran."""
    leaks: list[str] = []
    for ext in PLACEHOLDER_EXTS:
        for p in PUBLIC_DIR.rglob(f"*{ext}"):
            rel = p.relative_to(PUBLIC_DIR).as_posix()
            if rel.startswith(FROZEN_PREFIX):
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            m = PLACEHOLDER_RE.search(text)
            if m:
                line = text.count("\n", 0, m.start()) + 1
                leaks.append(f"{rel}:{line} unresolved placeholder near {m.group(0)}")
    if leaks:
        for leak in leaks:
            fails.append(f"placeholder: {leak}")
        return
    oks.append("no unresolved placeholders")


def check_validated_word(fails: list, oks: list) -> None:
    """phase 89 · trust-vocabulary unification.

    the canonical freshness term is "Verified" / "Vérifié". the legacy
    "Validated" / "Validé" is now non-canonical anywhere on the site
    (was previously reserved for /verify/; that exception is retired).
    matches are case-sensitive on a word boundary; substrings like
    "validation" or "validator" do not trigger.

    json-ld key uses inside application/ld+json blocks remain
    tolerated — a future schema change must not trip the gate on a
    legitimate machine-readable use."""
    hits = 0
    for p in _iter_active_html():
        rel = p.relative_to(PUBLIC_DIR).as_posix()
        text = p.read_text(encoding="utf-8")
        for m in VALIDATED_RE.finditer(text):
            window_start = max(0, m.start() - 200)
            window = text[window_start : m.start()]
            if '<script type="application/ld+json">' in window and "</script>" not in window:
                continue
            line = text.count("\n", 0, m.start()) + 1
            fails.append(
                f"{rel}:{line} '{m.group(0)}' — non-canonical trust term; "
                f"the canonical freshness label is 'Verified' / 'Vérifié'"
            )
            hits += 1
    if hits == 0:
        oks.append('no non-canonical "Validated"/"Validé" anywhere')


def check_security_txt_expires(overrides: dict, fails: list, warns: list, oks: list) -> None:
    """security.txt must carry an Expires line in the future. if an
    override declares the expected expiry, mismatch surfaces as a
    warning (the override is documentation, not enforcement)."""
    if not SECURITY_TXT.exists():
        fails.append(".well-known/security.txt: missing")
        return
    text = SECURITY_TXT.read_text(encoding="utf-8")
    m = EXPIRES_RE.search(text)
    if not m:
        fails.append(".well-known/security.txt: no Expires: line found")
        return
    raw = m.group(1)
    # rfc 3339 forms — accept z or +HH:MM offsets, with optional fractional
    # seconds. python's fromisoformat needs the z stripped pre-3.11.
    try:
        norm = raw.replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(norm)
    except ValueError:
        fails.append(f".well-known/security.txt: Expires={raw!r} not parseable as RFC 3339")
        return
    now = datetime.datetime.now(datetime.UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.UTC)
    if dt <= now:
        fails.append(
            f".well-known/security.txt: Expires={raw} is in the past (now UTC {now.isoformat()})"
        )
        return
    # compare against documented override if any. mismatch is a warning.
    expires_block = overrides.get("expires", {})
    leaf = (
        expires_block.get("/.well-known/security.txt") if isinstance(expires_block, dict) else None
    )
    expected_date = None
    if isinstance(leaf, dict):
        expected_date = leaf.get("date")
    if expected_date:
        actual_date = dt.date().isoformat()
        if actual_date != expected_date:
            warns.append(
                f".well-known/security.txt: Expires date {actual_date} "
                f"differs from override {expected_date} (override is documentation)"
            )
    oks.append(f"security.txt Expires={raw} ({dt.date().isoformat()})")


def check_stale_files(manifest: dict, edition: str, warns: list) -> None:
    """surface files whose modified_iso lags the canonical edition by
    more than 60 days. not a failure — long-lived static pages legitimately
    age — but the operator should see the list."""
    try:
        ed = datetime.date.fromisoformat(edition)
    except ValueError:
        return
    for rel, rec in manifest.get("files", {}).items():
        iso = rec.get("modified_iso")
        if not iso:
            continue
        try:
            d = datetime.date.fromisoformat(iso)
        except ValueError:
            continue
        if (ed - d).days > 60:
            warns.append(
                f"stale: {rel} last changed {iso}, edition {edition} ({(ed - d).days} days)"
            )


def main() -> int:
    if not IDENTITY_CANONICAL.exists():
        print(f"FAIL: {IDENTITY_CANONICAL} not found", file=sys.stderr)
        return 1
    edition = _read_json(IDENTITY_CANONICAL).get("edition", "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", edition):
        print(f"FAIL: canonical edition '{edition}' is not YYYY-MM-DD", file=sys.stderr)
        return 1

    if not MANIFEST.exists():
        print(f"FAIL: {MANIFEST} not found — run generate_file_metadata.py", file=sys.stderr)
        return 1
    manifest = _read_json(MANIFEST)

    overrides: dict = {}
    if DATE_OVERRIDES.exists():
        try:
            overrides = _read_json(DATE_OVERRIDES)
        except json.JSONDecodeError as e:
            print(f"FAIL: date_overrides.json invalid ({e})", file=sys.stderr)
            return 1

    fails: list[str] = []
    warns: list[str] = []
    oks: list[str] = []

    print("DATE CHECK")

    check_overrides_have_reasons(overrides, fails, oks)
    check_sitemap(manifest, overrides, edition, fails, oks)
    check_jsonld_datemod(manifest, fails, oks)
    check_integrity_generated(fails, oks)
    check_no_placeholders(fails, oks)
    check_validated_word(fails, oks)
    check_security_txt_expires(overrides, fails, warns, oks)
    check_stale_files(manifest, edition, warns)

    files_total = len(manifest.get("files", {}))
    oks.append(f"file-metadata.json: {files_total} entries consulted")

    for line in oks:
        print(f"OK {line}")
    for line in warns:
        print(f"WARN {line}")
    for line in fails:
        print(f"ERROR {line}")

    if fails:
        print(f"RESULT: {len(fails)} error(s), {len(warns)} warning(s)")
        return 1
    print("RESULT: green" if not warns else f"RESULT: green, {len(warns)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
