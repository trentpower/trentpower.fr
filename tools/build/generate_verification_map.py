#!/usr/bin/env python3
"""
trentpower.fr
Build /verify/verification-data.js from the public integrity manifest.

Inputs:
- /integrity.json (preliminary pass)
- identity_canonical.json
- site-metadata.json

Outputs:
- /verify/verification-data.js (the only on-disk file; clean stable
  filename matching every other asset on the site)
- All active HTML pages re-swept so every <script src> for this
  asset lands as `/verify/verification-data.js?v={edition}.{sha8}`,
  using query-string cache busting in the same shape as the rest of
  the site (styles.css, print.css, js/verify-modal.js, …).

The legacy dated variant `verification-data.<edition>.<sha8>.js` is
no longer written. The script tag is exempt from SRI by
generate_sri.py (verification-data embeds its own file hashes — a
self-referential cycle); that exemption matches on the clean path
after the query string is stripped, so it continues to apply.

Constraints:
- Same-origin static data; verify.js reads it client-side without
  fetch(), so CSP connect-src 'none' is preserved.
- Run after generate_integrity.py so per-file SHA-256 hashes exist.
- Does not include the hash of integrity.json itself; that file is
  re-hashed by the final generate_integrity.py pass.
"""

import datetime
import hashlib
import json
import os
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
from paths import (
    IDENTITY_CANONICAL as CANONICAL,
)
from paths import (
    PUBLIC_DIR as ROOT,
)
from sizes import humanise_bytes  # noqa: E402

os.chdir(ROOT)

INTEGRITY = pathlib.Path("integrity.json")
OUTPUT = pathlib.Path("verify/verification-data.js")
SITE_META = pathlib.Path("site-metadata.json")


def file_type_from_path(path: str) -> str:
    """Return a human file-type label from a path extension."""
    p = pathlib.Path(path)
    ext = p.suffix.lstrip(".").lower()
    if ext == "html":
        return "HTML"
    if ext == "js":
        return "JavaScript"
    if ext == "css":
        return "CSS"
    if ext == "json":
        return "JSON"
    if ext == "svg":
        return "SVG"
    if ext == "txt":
        return "Text"
    if ext == "xml":
        return "XML"
    if ext == "asc":
        return "Public key"
    if ext == "sig":
        return "Signature"
    return ext.upper() if ext else "File"


# canonical public routes covered by the verification map. each entry
# resolves to a manifest file path; if the manifest entry is missing
# the route is silently dropped (so we never expose stale data). the
# canonical edition is read from identity_canonical.json at runtime ,
# never hardcoded here, so a row cannot drift past a real edition bump.
#
# Source-mirror paths use the directory-preserving convention from
# generate_source_view.py: append .txt to the full live url. so
# /privacy/ → /source/privacy/index.html.txt. the flat-name convention
# (e.g. /source/privacy.html.txt) was used pre-reorg and is no longer
# generated; the previous routes table referenced those stale flat
# names, which produced null source_sha256 values on every record.
def _release_path() -> str | None:
    """Return the canonical /integrity/releases/<edition>/ path, or
    None if identity_canonical.json is unreadable. Reads at module load
    so a single-script test invocation works the same as a full build."""
    try:
        ed = json.loads(CANONICAL.read_text(encoding="utf-8")).get("edition", "")
        if ed:
            return f"/integrity/releases/{ed}/"
    except Exception:
        pass
    return None


_REL = _release_path()


# ─── page availability history ──────────────────────────────────
# walk every public/integrity/releases/<edition>/ folder, read its
# per-release manifest (integrity-redistributable.json, or the
# minimal integrity.json fallback for the 2026-02 edition), and
# build a {manifest_path → [{edition, sha256}, ...]} lookup. each
# manifest_path's list is sorted newest-first; verification-map
# records read from this lookup to surface a per-page provenance
# trail beneath the verify card.
_RELEASES_DIR = pathlib.Path("integrity/releases")
_EDITION_RE = re.compile(r"^\d{4}-\d{2}(?:-\d{2})?$")


def _collect_release_history() -> dict:
    """Return {manifest_path: [(edition_date, sha256), ...]}
    where the list is sorted newest-first (descending edition date).
    Edition dates are stable string sortable (YYYY-MM-DD), and the
    2026-02 short form sorts correctly because YYYY-MM < YYYY-MM-DD
    lexicographically when the date suffix is absent."""
    history: dict[str, list[tuple[str, str]]] = {}
    if not _RELEASES_DIR.is_dir():
        return history
    editions: list[tuple[str, pathlib.Path]] = []
    for child in _RELEASES_DIR.iterdir():
        if not child.is_dir():
            continue
        if not _EDITION_RE.match(child.name):
            continue
        editions.append((child.name, child))
    # newest first so each list pop emits in display order.
    editions.sort(key=lambda pair: pair[0], reverse=True)
    for edition_date, edition_dir in editions:
        manifest_data = None
        for candidate in (
            "integrity-redistributable.json",
            "integrity.json",
        ):
            candidate_path = edition_dir / candidate
            if candidate_path.is_file():
                try:
                    manifest_data = json.loads(candidate_path.read_text(encoding="utf-8"))
                    break
                except Exception:
                    continue
        if not manifest_data:
            continue
        files = manifest_data.get("files") or {}
        for mp, sha in files.items():
            # only HTML pages enter the history; other assets (fonts,
            # css, js, source mirrors) are not page records.
            if not mp.endswith(".html"):
                continue
            history.setdefault(mp, []).append((edition_date, sha))
    return history


_HISTORY_INDEX = _collect_release_history()


def _history_for(
    manifest_path: str, current_edition: str, current_sha: str
) -> tuple[list[dict] | None, str | None, str | None]:
    """Return (history_entries, first_archived, change_status) for a
    page. history_entries is a list of {edition, release_path, sha256,
    current?} dicts ordered newest-first; first_archived is the oldest
    edition date in the list; change_status is one of 'first',
    'unchanged', 'changed' or None when no archived history exists.

    The current edition's row carries current=True; older rows omit
    the marker. release_path always resolves to a folder on disk
    because the entries are sourced from disk scan, not heuristics."""
    rows = _HISTORY_INDEX.get(manifest_path)
    if not rows:
        return None, None, None
    history_entries: list[dict] = []
    for edition_date, sha in rows:
        # `edition_date` (not `edition`) avoids collision with the
        # validate_edition.py regex that asserts every top-level
        # "edition": "<YYYY-MM-DD>" matches the canonical edition.
        # the renderer reads entry.edition_date.
        entry = {
            "edition_date": edition_date,
            "release_path": f"/integrity/releases/{edition_date}/",
            "sha256": sha,
        }
        if edition_date == current_edition:
            entry["current"] = True
        history_entries.append(entry)
    first_archived = rows[-1][0]  # oldest is last after newest-first sort
    if len(rows) == 1:
        change_status = "first"
    else:
        change_status = "unchanged" if rows[0][1] == rows[1][1] else "changed"
    return history_entries, first_archived, change_status


# ─── bilingual route table ──────────────────────────────────────
# the verification map records every public page across both /en/
# and /fr/ trees. titles are read from the rendered page (the
# renderer has already set the per-language <title>), so the map is
# language-correct without a second copy of the editorial strings.
_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)


def _title_of(rel: str) -> str:
    p = pathlib.Path(rel)
    if p.is_file():
        m = _TITLE_RE.search(p.read_text(encoding="utf-8"))
        if m:
            return (
                m.group(1)
                .strip()
                .replace("&amp;", "&")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("&quot;", '"')
            )
    return rel


_PRINT_TYPE = {
    "home": "profile",
    "privacy": "trust-sheet",
    "security": "trust-sheet",
    "integrity": "trust-sheet",
    "integrity-releases": "utility-sheet",
    "integrity-verify-locally": "utility-sheet",
    "security-acknowledgments": None,
    "verify": "utility-sheet",
    "source": "utility-sheet",
    "source-view": "utility-sheet",
}


def _build_routes() -> list:
    """(path, title, canonical, source-mirror, manifest-path, release, print_type)
    for every page in both language trees, the per-tree + root error
    pages, the /local/ device-console page, and the / language gate."""
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
    import routes as rm

    base = rm.base_url()
    out = []
    for key in rm.route_keys():
        for lang in rm.languages():
            path = rm.route_path(key, lang)
            mp = rm.route_output(key, lang)
            out.append(
                (
                    path,
                    _title_of(mp),
                    base + path,
                    "/source/" + mp + ".txt",
                    mp,
                    _REL,
                    _PRINT_TYPE.get(key),
                )
            )
    for lang in rm.languages():
        for err in ("403", "404", "500", "maintenance"):
            mp = f"{rm.lang_url_segment(lang)}/{err}.html"
            out.append(
                (
                    f"/{mp}",
                    _title_of(mp),
                    base + f"/{mp}",
                    "/source/" + mp + ".txt",
                    mp,
                    None,
                    "utility-sheet",
                )
            )
    for err in ("403", "404", "500", "maintenance"):
        mp = f"{err}.html"
        out.append(
            (
                f"/{mp}",
                _title_of(mp),
                base + f"/{mp}",
                "/source/" + mp + ".txt",
                mp,
                None,
                "utility-sheet",
            )
        )
    out.append(
        (
            "/local/",
            _title_of("local/index.html"),
            base + "/local/",
            "/source/local/index.html.txt",
            "local/index.html",
            None,
            "utility-sheet",
        )
    )
    out.append(
        (
            "/tests/",
            _title_of("tests/index.html"),
            base + "/tests/",
            "/source/tests/index.html.txt",
            "tests/index.html",
            _REL,
            "utility-sheet",
        )
    )
    out.append(
        (
            "/",
            _title_of("index.html"),
            base + "/",
            "/source/index.html.txt",
            "index.html",
            _REL,
            "profile",
        )
    )
    return out


ROUTES = _build_routes()


def main() -> int:
    if not INTEGRITY.exists():
        print(f"ERROR: {INTEGRITY} not found — run generate_integrity.py first", file=sys.stderr)
        return 1

    manifest = json.loads(INTEGRITY.read_text())
    files = manifest["files"]
    # use UTC date · validate_verification_map.py compares against
    # today UTC, so generator and validator must agree across timezones
    # (fixed at the midnight-cest boundary where local was a day ahead
    # of utc and the build went red on a no-op pass).
    validated = datetime.datetime.now(datetime.UTC).date().isoformat()

    # pull the canonical edition + asset_version from the canonical sources
    # so the verification map never drifts from the rest of the site.
    canonical_edition = "unknown"
    if CANONICAL.exists():
        try:
            canonical_edition = json.loads(CANONICAL.read_text()).get("edition", canonical_edition)
        except Exception:
            pass
    asset_version = ""
    if SITE_META.exists():
        try:
            asset_version = json.loads(SITE_META.read_text()).get("asset_version", "")
        except Exception:
            pass

    records = {}
    for path, title, canonical, source_mirror, manifest_path, release, print_type in ROUTES:
        edition = canonical_edition
        sha = files.get(manifest_path)
        manifest_status = "found" if sha is not None else "missing"
        # file size + type come from the on-disk manifest entry file.
        size_bytes = None
        size_label = None
        local_file = pathlib.Path(manifest_path)
        if local_file.is_file():
            size_bytes = local_file.stat().st_size
            size_label = humanise_bytes(size_bytes)

        # the source mirror has its own hash entry (if it exists); expose
        # it so the page-source-mirror verification command can be truthful.
        source_key = source_mirror.lstrip("/") if source_mirror else None
        source_sha = files.get(source_key) if source_key else None

        # citation string built at build time (single source of truth).
        # format is intentionally compact: drops quotes around the title,
        # drops the locality, uses the bare-host display form. homepage
        # omits the page-title segment ("homepage" would be redundant);
        # subpages keep it.
        # Examples:
        #   /         → trent power. personal site. edition 2026-05-02. trentpower.fr
        #   /privacy/ → trent power. privacy & trust. personal site. edition 2026-05-02. trentpower.fr/privacy/
        if path == "/":
            short_url = "trentpower.fr"
            citation = f"Trent Power. Personal Site. Edition {edition}. {short_url}"
        else:
            short_url = "trentpower.fr" + path
            citation = f"Trent Power. {title}. Personal Site. Edition {edition}. {short_url}"

        rec = {
            "path": path,
            "title": title,
            "canonical": canonical,
            "route": path,  # alias for clarity in the record card
            "file_type": file_type_from_path(manifest_path),
            "source": source_mirror,
            # clean reader URL: ?path=<canonical live route>. the .txt
            # mirror extension is an implementation detail of the static
            # mirror and never appears in the address bar. the reader
            # itself resolves the path to a source mirror at runtime
            # via window.TP_SOURCE_VIEW_MANIFEST.
            "reader": (
                (
                    ("/fr/source/voir/" if path.startswith("/fr/") else "/en-au/source/view/")
                    + "?path="
                    + path.replace("/", "%2F")
                )
                if source_mirror
                else None
            ),
            "source_manifest": "/source/source-manifest.json",
            "source_sha256": source_sha,
            "sha256": sha if sha is not None else "(missing)",
            "size_bytes": size_bytes,
            "size_label": size_label,
            "manifest": "/integrity.json",
            "manifest_entry_path": "/" + manifest_path,
            "manifest_status": manifest_status,
            "signature": "/integrity.json.sig",
            "public_key": "/.well-known/pgp-key.asc",
            "edition": edition,
            "asset_version": asset_version,
            "validated": validated,
            "citation": citation,
        }
        if release:
            rec["release"] = release
        if print_type:
            rec["print_type"] = print_type

        # phase 95 · page availability history. when the page exists in
        # at least one archived release, attach `history` (newest-first
        # list of {edition, release_path, sha256, current?}), `first_archived`
        # (oldest edition the page was archived in), and `change_status`
        # ('first' | 'unchanged' | 'changed') so verify.js can render
        # a per-page provenance trail beneath the card.
        history_entries, first_archived, change_status = _history_for(
            manifest_path,
            canonical_edition,
            sha if sha else "",
        )
        if history_entries:
            rec["history"] = history_entries
            rec["first_archived"] = first_archived
            rec["change_status"] = change_status

        records[path] = rec
        print(f"  ok   {path:32}  → {manifest_path}  [{manifest_status}, {size_label}]")

    # emit a small immutable global. strict, no eval, no inline injection.
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(records, ensure_ascii=False, indent=2)
    js = (
        "/*! trentpower.fr · verification map · generated · "
        "signed via /integrity.json */\n"
        "window.TP_VERIFICATION_MAP = " + payload + ";\n"
    )

    # clean stable filename — matches every other asset on the site.
    # cache busting rides on the global `?v={asset_version}` query
    # string (the same one swept onto every other asset by
    # generate_site.py), so predeploy stage 7 (ASSET_VERSION coherence)
    # validates that all SWEPT_ASSETS — including this one — carry the
    # canonical asset_version. asset_version embeds the edition string
    # plus an 8-hex hash of ASSET_BUNDLE, so it rolls every edition;
    # mid-edition churn of verification-data.js (e.g. mirror updates
    # within a single build) doesn't roll the URL, but that's fine
    # because the published edition is the unit of cache invalidation.
    # the per-file sha8 is retained here only for the build log.
    sha8 = hashlib.sha256(js.encode("utf-8")).hexdigest()[:8]
    OUTPUT.write_text(js, encoding="utf-8")

    # Re-sweep every active html page so its <script> tag becomes:
    #   <script src="/verify/verification-data.js?v={asset_version}" defer></script>
    # the regex matches the clean URL as well as any legacy dated form
    # (`verification-data.<date>.<sha>.js`) left over in cached HTML
    # from earlier editions, so re-runs converge. SRI is intentionally
    # NOT re-added: generate_sri.py exempts /verify/verification-data.js
    # (the file embeds its own hashes — a self-referential cycle); the
    # exemption strips ?… before matching, so the clean path + query
    # form continues to be exempted.
    versioned_query = f"?v={asset_version}" if asset_version else ""
    swept_target = f"/verify/verification-data.js{versioned_query}"
    href_re = re.compile(
        r"/verify/verification-data"
        r"(?:\.\d{4}-\d{2}-\d{2}\.[a-f0-9]+)?"
        r"\.js"
        r'(?:\?v=[^"\']+)?'
    )
    import glob as _glob

    HTML_PAGES = [
        p
        for p in sorted(_glob.glob("**/*.html", recursive=True))
        if not p.startswith("integrity/releases/")
    ]
    swept = 0
    for relpath in HTML_PAGES:
        p = pathlib.Path(relpath)
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        new_text = href_re.sub(swept_target, text)
        if new_text != text:
            p.write_text(new_text, encoding="utf-8")
            swept += 1

    print(f"\n✓ wrote {OUTPUT}  ({len(records)} routes, {len(js)} bytes, sha8 {sha8})")
    print(f"✓ swept {swept} HTML page(s) → {swept_target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
