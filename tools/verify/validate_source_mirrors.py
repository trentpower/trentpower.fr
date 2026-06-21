#!/usr/bin/env python3
"""validate_source_mirrors.py — fail the build on any drifted source mirror.

The /source/ tree is a byte-exact text mirror of an explicit allowlist of
public files (see generate_source_view.MIRROR). This script enforces:

  1. every (src, mirror) pair has a mirror that exists on disk
  2. every mirror's bytes equal the source file's bytes exactly
  3. no extra *.txt mirror exists in /source/ that is not in MIRROR
  4. /source/source-manifest.json size + sha256 entries match disk

Exit 0 = mirror tree is faithful.
Exit 1 = at least one drift; failing paths are printed.

Shape (deep module, small interface). The filesystem is the one injected seam —
`Repo(root)` — so the whole gate runs over a fixture repo with no monkeypatching.
`load(repo)` reads the generator's MIRROR map (or returns an error); `evaluate`
is the pure compute path returning a Result; `main()` is the only adapter that
prints/exits and reproduces the original stdout contract.
"""

from __future__ import annotations

import fnmatch
import importlib.util
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# dated rebuild companion regexes shared by the source-mirror exempt
# rules. matches /integrity/releases/<edition>/<prefix>-YYYY-MM-DD.<ext>
# where <prefix> is one of the three companion families.
_MIRROR_REBUILD_REDIST_RE = re.compile(
    r"/integrity-redistributable-\d{4}-\d{2}-\d{2}\.json(\.sig)?$"
)
_MIRROR_REBUILD_EXCL_RE = re.compile(r"/EXCLUDED_FILES-\d{4}-\d{2}-\d{2}\.(json|txt)(\.sig)?$")
_MIRROR_REBUILD_RELEASE_RE = re.compile(r"/release-\d{4}-\d{2}-\d{2}\.json(\.sig)?$")

# the live html carries the footer source-hash and the matching body
# attribute (inject_source_sha_footer.py). the mirror is captured BEFORE
# the injection so its sha256 (the value the footer displays) is non-
# circular: hashing a file that does not contain its own hash. canonical-
# ising both sides of the comparison strips that bounded divergence so
# the validator confirms the mirror reflects everything else faithfully.
_FOOTER_SHA_BODY_RE = re.compile(
    rb'data-source-sha256-short="(?:[a-f0-9]{8}|-{8})"',
)
_FOOTER_SHA_CODE_RE = re.compile(
    rb"(<a\b[^>]*?\bdata-page-sha-short\b[^>]*>[^<]*<code>)(?:[a-f0-9]{8}|-{8})(</code>)",
)
# the verification-data reference carries an embedded sha8 that changes
# any time verification-data.js itself changes (e.g. when source_sha256
# is refreshed post-mirror). the mirror is captured at one moment in
# the convergence loop; the live HTML may reference a later sha8.
# normalise both sides to the unversioned alias so the byte comparison
# isolates real content drift from the expected metadata churn.
#
# accepts BOTH url shapes during transition:
#   legacy: /verify/verification-data.YYYY-MM-DD.HASH.js  (filename-hashed)
#   new:    /verify/verification-data.js?v=YYYY-MM-DD.HASH  (clean filename + query)
# the new shape is what we emit from 2026-05-23 onward; the legacy
# regex stays in for one cycle while any cached HTML rolls over.
_VERIFICATION_DATA_REF_RE = re.compile(
    rb"/verify/verification-data(?:"
    rb"\.\d{4}-\d{2}-\d{2}\.[a-f0-9]+\.js"
    rb"|\.js\?v=\d{4}-\d{2}-\d{2}\.[a-f0-9]+"
    rb")",
)
# the SRI integrity= attribute on the verification-data <script> tag
# tracks the file's content. mirror and live HTML may reference
# different verification-data builds (mirror frozen at one moment of
# the convergence loop, live HTML re-swept after). normalise the SRI
# attribute on that one script tag so the comparison ignores the
# expected divergence.
_VERIFICATION_DATA_SRI_RE = re.compile(
    rb'(<script\s+src="/verify/verification-data[^"]*"\s+)integrity="sha384-[^"]+"',
)


def _canonicalise_footer_sha(data: bytes) -> bytes:
    new = _FOOTER_SHA_BODY_RE.sub(b'data-source-sha256-short="--------"', data)
    new = _FOOTER_SHA_CODE_RE.sub(rb"\1--------\2", new)
    new = _VERIFICATION_DATA_REF_RE.sub(b"/verify/verification-data.js", new)
    new = _VERIFICATION_DATA_SRI_RE.sub(rb'\1integrity="sha384-CANON"', new)
    return new


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
import routes as _routes  # noqa: E402
from hashing import sha256_b64  # noqa: E402
from paths import PUBLIC_DIR as ROOT  # noqa: E402
from paths import REPO_ROOT  # noqa: E402
from paths import TOOLS_DIR as _TOOLS_DIR  # noqa: E402
from repo import Repo  # noqa: E402  (shared filesystem evidence seam)

# repo-relative location of the public tree, resolved through the Repo seam.
# the public-tree knowledge (the "public/" prefix) and the /source/ mirror
# subtree under it live here in the validator, not on Repo.
PUBLIC_REL = "public"

SOURCE_DIR = ROOT / "source"
# generate_source_view.py lives in tools/ alongside this validator
# (was htdocs/ pre-reorg).
GENERATOR = _TOOLS_DIR / "build" / "generate_source_view.py"

# mirrors that are not listed in mirror but are generated by main()
# itself; do not flag these as "extras".
SELF_GENERATED = {
    "index.html",
    "source-manifest.json",
    "source-manifest.json.txt",
    "README.txt",
    # source reader shell and data files (generated by generate_source_reader.py)
    "view/index.html",
    "view/source-view.js",
    "view/source-view-manifest.js",
}

# required mirrors — the build fails loudly if any of these go missing,
# even if mirror were edited to drop them. these are the trust-system
# pages whose source mirror is referenced by /verify/ and the cite
# overlay; their disappearance silently breaks page-level verification.
# paths are relative to SOURCE_DIR and use the directory-preserving
# convention: live url x → /source/X.txt.
# the trust-system route keys — both language editions of each must
# always carry a mirror. derived against the route map so the french
# slugs (confidentialite/, securite/, verifier/, integrite/archives/)
# are tracked without restating them here.
_TRUST_ROUTE_KEYS = (
    "privacy",
    "integrity",
    "integrity-releases",
    "security",
    "verify",
)


def _required_mirrors() -> set:
    req = {"index.html.txt"}  # the language gate
    for key in _TRUST_ROUTE_KEYS:
        for lang in _routes.languages():
            req.add(_routes.route_output(key, lang) + ".txt")
    return req


REQUIRED_MIRRORS = _required_mirrors()

# recursive /source/source/ paths are forbidden by the publication
# brief. only /source/index.html, /source/source-manifest.json (+ .txt),
# /source/README.txt, the directory-preserving *.txt mirrors, and the
# /source/images/ binary-mirror tree are tolerated.
FORBIDDEN_RECURSIVE_PREFIX = "source/"

# public files that are intentionally not mirrored. loaded from
# tools/source-mirror-exclusions.json. each entry is a public-tree
# path (e.g. "integrity.json"). used by the completeness gate so we
# don't have to mirror signature files / release archives / etc.
EXCLUSIONS_FILE = _TOOLS_DIR / "config" / "source-mirror-exclusions.json"


def _import_mirror():
    """Import generate_source_view as a module and return (MIRROR,
    SOURCE_MIRROR_MAP, css_banner, js_banner, htaccess_transform). The
    module is structured so import does not trigger generation."""
    spec = importlib.util.spec_from_file_location("generate_source_view", GENERATOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return (
        list(mod.MIRROR),
        dict(getattr(mod, "SOURCE_MIRROR_MAP", {})),
        bytes(getattr(mod, "_AUTHORED_BANNER_CSS", b"")),
        bytes(getattr(mod, "_AUTHORED_BANNER_JS", b"")),
        getattr(mod, "_htaccess_mirror_transform", lambda b: b),
    )


# ---------------------------------------------------------------------------
# Ctx / Result — the values that flow through the interface. load() produces
# Ctx (or errors); evaluate() produces Result; main() renders it. tests assert
# on Result, never on stdout.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Ctx:
    mirror: list
    mirror_map: dict
    banner_css: bytes
    banner_js: bytes
    htaccess_transform: object


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    warns: list[str] = field(default_factory=list)
    # carries the OK summary line so main() can reproduce the original stdout.
    summary: str = ""

    @property
    def ok(self) -> bool:
        return not self.fails


# ---------------------------------------------------------------------------
# load — import the generator's MIRROR map. returns (ctx, errors); never
# prints/exits.
# ---------------------------------------------------------------------------
def load(repo: Repo) -> tuple[Ctx | None, list[str]]:
    if not GENERATOR.exists():
        return None, [f"{GENERATOR} not found"]
    mirror, mirror_map, banner_css, banner_js, htaccess_transform = _import_mirror()
    return (
        Ctx(
            mirror=mirror,
            mirror_map=mirror_map,
            banner_css=banner_css,
            banner_js=banner_js,
            htaccess_transform=htaccess_transform,
        ),
        [],
    )


# ---------------------------------------------------------------------------
# evaluate — the compute interface. one call, one Result, over the injected
# Repo. this is the test surface. all byte reads / tree walks go through
# repo.root; text reads go through repo.read.
# ---------------------------------------------------------------------------
def evaluate(repo: Repo, ctx: Ctx) -> Result:
    mirror = ctx.mirror
    mirror_map = ctx.mirror_map
    banner_css = ctx.banner_css
    banner_js = ctx.banner_js
    htaccess_transform = ctx.htaccess_transform

    root = repo.root / PUBLIC_REL
    source_dir = repo.root / "public" / "source"

    r = Result()
    fails = r.fails

    # 0: required-mirror gate — fail explicitly if a trust-page mirror
    # is missing, before any byte-comparison work. catches the case
    # where mirror itself was edited to drop a required entry.
    expected_names_set = {dst for _, dst in mirror}
    for required in sorted(REQUIRED_MIRRORS):
        on_disk = (source_dir / required).is_file()
        in_mirror = required in expected_names_set
        if not on_disk:
            fails.append(
                f"REQUIRED MIRROR MISSING: source/{required} (trust-system page must always have a public mirror)"
            )
        elif not in_mirror:
            fails.append(
                f"REQUIRED MIRROR UNTRACKED: source/{required} exists on disk but is not in MIRROR (validator can't enforce byte-equality)"
            )

    # 1 + 2: every entry has a byte-equal mirror. six asset mirrors
    # are intentionally remapped to authored source via
    # SOURCE_MIRROR_MAP — for those, the expected bytes are the
    # banner-prefixed authored source rather than the live public
    # bytes.
    expected_names = {dst for _, dst in mirror}
    for src, dst in mirror:
        sp = root / src
        dp = source_dir / dst
        if not sp.is_file():
            fails.append(f"MISSING SOURCE: {src} (referenced by mirror entry → {dst})")
            continue
        if not dp.is_file():
            fails.append(f"MISSING MIRROR: source/{dst} (expected mirror of {src})")
            continue
        authored = mirror_map.get(dst)
        if authored is not None:
            ap = Path(authored)
            if not ap.is_file():
                fails.append(f"AUTHORED-SOURCE MISSING: {ap} (expected for mirror source/{dst})")
                continue
            banner = banner_css if dst.endswith(".css.txt") else banner_js
            expected_bytes = banner + ap.read_bytes()
            actual_bytes = dp.read_bytes()
            if expected_bytes != actual_bytes:
                fails.append(
                    f"DRIFT (authored): source/{dst} "
                    f"(expected sha={sha256_b64(expected_bytes)[:12]} "
                    f"mirror sha={sha256_b64(actual_bytes)[:12]})"
                )
            continue
        src_bytes = sp.read_bytes()
        dst_bytes = dp.read_bytes()
        # the apache config mirror is banner-framed and line-redacted by
        # the source generator. apply the same transform so byte-equality
        # is honest about what the mirror is supposed to be.
        expected_bytes = htaccess_transform(src_bytes) if src == ".htaccess" else src_bytes
        # html mirrors are captured pre-injection; the live page carries
        # the footer source-sha bytes that the mirror does not. canonical-
        # ising both sides to the placeholder shape isolates the bounded,
        # documented divergence so the validator catches any other drift.
        if dst.endswith(".html.txt"):
            expected_bytes = _canonicalise_footer_sha(expected_bytes)
            dst_bytes = _canonicalise_footer_sha(dst_bytes)
        if expected_bytes != dst_bytes:
            fails.append(
                f"DRIFT: {src} ↔ source/{dst} "
                f"(expected sha={sha256_b64(expected_bytes)[:12]} "
                f"mirror sha={sha256_b64(dst_bytes)[:12]})"
            )

    # image mirrors live under /source/images/... and are produced by
    # the same generate_source_view.py run. they are tracked in
    # source-manifest.json's "images" array, not the "files" array,
    # so the editorial catalogue stays terse. allowlist them here
    # against the array on disk.
    image_mirror_names: set[str] = set()
    image_mirror_records: list[dict] = []
    smf_path = source_dir / "source-manifest.json"
    if smf_path.exists():
        try:
            sm = json.loads(smf_path.read_text(encoding="utf-8"))
            for rec in sm.get("images", []):
                if rec.get("name"):
                    image_mirror_names.add(rec["name"])
                    image_mirror_records.append(rec)
        except json.JSONDecodeError:
            pass

    # 3: no extra *.txt mirror outside the allowlist (recursive walk
    # since mirrors now preserve the live tree's directory structure;
    # nested paths like /source/privacy/index.html.txt must be walked
    # by rglob rather than iterdir).
    if source_dir.is_dir():
        for fp in sorted(source_dir.rglob("*")):
            if not fp.is_file():
                continue
            rel = fp.relative_to(source_dir).as_posix()
            if rel in expected_names:
                continue
            if rel in SELF_GENERATED:
                continue
            if rel in image_mirror_names:
                continue
            fails.append(f"EXTRA: source/{rel} (not in MIRROR)")

    # 5: image mirrors — every record's live file must exist and the
    # mirror's hash header (binary case) or byte-equality (svg case)
    # must match disk.
    for rec in image_mirror_records:
        live_rel = rec["live_path"].lstrip("/")
        mirror_rel = rec["name"]
        live_p = root / live_rel
        mirror_p = source_dir / mirror_rel
        if not live_p.is_file():
            fails.append(
                f"IMAGE MIRROR: live file {live_rel} missing (mirror exists at source/{mirror_rel})"
            )
            continue
        if not mirror_p.is_file():
            fails.append(f"IMAGE MIRROR: mirror source/{mirror_rel} missing (live file present)")
            continue
        # compare live bytes' sha256 to the manifest record.
        live_sha = sha256_b64(live_p.read_bytes())
        if rec.get("sha256") != live_sha:
            fails.append(
                f"IMAGE MIRROR: source/{mirror_rel} manifest sha256 "
                f"{rec.get('sha256', '')[:16]}… vs live disk {live_sha[:16]}…"
            )

    # 4: source-manifest.json self-consistency for every entry
    smf = source_dir / "source-manifest.json"
    if smf.exists():
        try:
            sm = json.loads(smf.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            fails.append(f"source-manifest.json: invalid JSON ({e})")
            sm = None
        if isinstance(sm, dict):
            # per-entry self-consistency: every listed mirror must exist
            # on disk and its mirror_bytes + sha256 must match the bytes
            # published at /source/. (no wall-clock check here — mirror
            # freshness is guaranteed by the sha256/byte-match below, so a
            # stale mirror is caught regardless of which day the gate runs.)
            for entry in sm.get("files", []):
                name = entry.get("name", "")
                mp = source_dir / name
                if not mp.is_file():
                    fails.append(f"manifest: source/{name} listed but missing on disk")
                    continue
                data = mp.read_bytes()
                # entry.size / size_human refer to the canonical public
                # file (what the source-index table shows). the mirror's
                # own byte count is in mirror_bytes. on-disk comparison
                # is against mirror_bytes; the sha256 still hashes the
                # mirror file because that's what's published at /source/.
                mirror_bytes = entry.get("mirror_bytes", entry.get("size"))
                if mirror_bytes != len(data):
                    fails.append(
                        f"manifest: source/{name} mirror_bytes {mirror_bytes} != disk {len(data)}"
                    )
                disk_sha = sha256_b64(data)
                if entry.get("sha256") != disk_sha:
                    fails.append(
                        f"manifest: source/{name} sha256 {entry.get('sha256')[:12] if entry.get('sha256') else '∅'} "
                        f"!= disk {disk_sha[:12]}"
                    )
                # per-row `modified` is now content-history anchored
                # (resolved from /file-metadata.json) so it intentionally
                # differs from `generated_at` for files unchanged since
                # earlier builds. only fail if `modified` is missing
                # entirely or malformed.
                m = entry.get("modified")
                if m is not None and not (
                    isinstance(m, str) and len(m) >= 10 and m[4] == "-" and m[7] == "-"
                ):
                    fails.append(f"manifest: source/{name} modified={m!r} is not an ISO date")

    # 6: recursive-source-path guard
    # /source/source/ is forbidden. the source page is its own entry
    # point; a self-mirror under /source/source/index.html.txt would
    # re-introduce the recursive layer the brief specifically rules out.
    recursive_root = source_dir / "source"
    if recursive_root.exists():
        for fp in sorted(recursive_root.rglob("*")):
            if fp.is_file():
                rel = fp.relative_to(source_dir).as_posix()
                fails.append(
                    f"RECURSIVE SOURCE: source/{rel} (paths under "
                    f"source/source/ are forbidden by the publication brief)"
                )

    # 7: completeness gate — every public file is either mirrored
    #    (text or image), or explicitly listed in exclusions.json.
    #    catches the "new public file added but no mirror generated"
    #    regression class.
    exclusions: set[str] = set()
    exclusion_globs: list[str] = []
    if EXCLUSIONS_FILE.exists():
        try:
            data = json.loads(EXCLUSIONS_FILE.read_text(encoding="utf-8"))
            exclusions = set(data.get("exclude", []))
            exclusion_globs = list(data.get("exclude_glob", []))
        except json.JSONDecodeError as e:
            fails.append(f"source-mirror-exclusions.json: invalid JSON ({e})")
    mirrored_live_paths = {src for src, _ in mirror}
    image_mirror_live_paths = {rec["live_path"].lstrip("/") for rec in image_mirror_records}
    # walk the public tree and check completeness.
    for fp in sorted(root.rglob("*")):
        if not fp.is_file():
            continue
        rel = fp.relative_to(root).as_posix()
        # skip the /source/ subtree (its contents are mirrors).
        if rel.startswith("source/"):
            continue
        # skip frozen-archive contents (sealed historical bytes).
        if rel.startswith("integrity/releases/2026-02/"):
            continue
        # skip per-edition release artefacts (binary archives + sigs).
        if rel.startswith("integrity/releases/") and (
            rel.endswith(".zip")
            or rel.endswith(".tar.gz")
            or rel.endswith(".sha256")
            or rel.endswith(".sig")
            or rel.endswith("/SHA256SUMS")
            or rel.endswith("/integrity-redistributable.json")
            or rel.endswith("/integrity-redistributable.json.sig")
            # dated rebuild companion of the redistributable manifest.
            or _MIRROR_REBUILD_REDIST_RE.search(rel)
            # exclusion manifest pair lives alongside the archive at the
            # release directory; it is byte-equal to the in-archive
            # copy and signed independently. mirroring would duplicate
            # bytes without aiding inspection.
            or rel.endswith("/EXCLUDED_FILES.json")
            or rel.endswith("/EXCLUDED_FILES.json.sig")
            or rel.endswith("/EXCLUDED_FILES.txt")
            # dated rebuild companion of the exclusion manifest.
            or _MIRROR_REBUILD_EXCL_RE.search(rel)
            # release.json is the per-edition trust anchor; byte-equal
            # to the in-archive copy and signed independently.
            or rel.endswith("/release.json")
            or rel.endswith("/release.json.sig")
            # dated rebuild companion of the release.json trust anchor.
            or _MIRROR_REBUILD_RELEASE_RE.search(rel)
            # per-edition builds index. content can grow on each
            # across-day rebuild; mirroring would force constant churn.
            or rel.endswith("/builds.json")
            or rel.endswith("/builds.json.sig")
            # signed score-ledger attestation published into the release;
            # its .sig is covered by the .sig rule above. a source mirror
            # would duplicate the snapshot bytes without aiding inspection
            # (recipients verify the live .txt against the published key).
            or rel.endswith("/TESTRESULTS.txt")
        ):
            continue
        if rel in mirrored_live_paths:
            continue
        if rel in image_mirror_live_paths:
            continue
        if rel in exclusions:
            continue
        if any(fnmatch.fnmatch(rel, pat) for pat in exclusion_globs):
            continue
        fails.append(
            f"COMPLETENESS: {rel} (public file has no source mirror "
            f"and is not listed in tools/source-mirror-exclusions.json)"
        )

    r.summary = (
        f"OK: source mirrors — {len(mirror)} text + {len(image_mirror_records)} "
        f"image, {len(exclusions)} exclusion(s); manifest + completeness gate green"
    )
    return r


# ---------------------------------------------------------------------------
# main — the side-effecting adapter. loads, evaluates, renders, returns exit
# code. the only place stdout and exit codes live.
# ---------------------------------------------------------------------------
def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)

    ctx, errors = load(repo)
    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        return 1

    r = evaluate(repo, ctx)

    if r.fails:
        print(f"FAIL: {len(r.fails)} source-mirror issue(s):")
        for f in r.fails:
            print(f"  {f}")
        return 1

    print(r.summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
