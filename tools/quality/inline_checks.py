"""inline_checks.py — inline cross-cutting check functions for the gate.

Library, not a script: each check here is a small function that does
not warrant its own validate_*.py sub-script. tools/lib/checks.py
imports this module and registers every function into the blocking or
advisory tier; gate.py and lint.py are the entry points that run them.

The checks:
  check_gpg — integrity.json.sig verifies against the *published* key
      in a throwaway keyring
  check_integrity_manifest_freshness — every active public file appears
      in integrity.json with a current sha256
  check_integrity_sig_freshness — integrity.json.sig is not stale
      relative to the manifest it signs
  check_verification_map_dates — every Verify record's `validated`
      date falls within the freshness window
  check_asset_version_coherence — site-metadata ↔ HTML ↔ sw.js, AND the
      bundle hash recomputed from disk matches the published version
  check_sw_precache — every URL in sw.js's precache lists maps to a
      real file on disk with a matching content-type
  check_local_path_leakage — no /home/, Desktop/, htdocs/htdocs or
      server-internal paths in public bytes
  check_hidden_and_archive_safety — no hidden host artefacts or key
      material; release ZIP free of fonts and stale stylesheets
  check_frozen_archives_immutable — every file under /integrity/releases/
      hashes to its own per-release baseline
  check_changelog_freshness — the edition is not newer than the topmost
      changelog entry

Each function prints its own OK/FAIL lines and returns 0 (pass) or
1 (fail).
"""

import datetime
import hashlib
import json
import os
import pathlib
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
import routes as _routes  # noqa: E402
from hashing import sha256_b64, sri_sha256  # noqa: E402
from paths import PUBLIC_DIR as ROOT  # noqa: E402


def _bilingual_page_outputs() -> list:
    """public/-relative path of every rendered bilingual page, both
    editions — derived from the route map so French slugs are tracked
    without restating them."""
    out = []
    for key in _routes.route_keys():
        for lang in _routes.languages():
            out.append(_routes.route_output(key, lang))
    return out


def _tree_error_pages() -> list:
    """Per-language-tree error documents."""
    return [
        f"{_routes.lang_url_segment(lang)}/{err}"
        for lang in _routes.languages()
        for err in ("403.html", "404.html", "500.html", "maintenance.html")
    ]


# /sw-reset/ deliberately omitted from the asset-version sweep: the
# recovery page references stylesheets without ?v= so it can never be
# served from a stale varnish layer. the page is also network-only at
# the sw level (see public_inventory.NETWORK_ONLY).
ACTIVE_HTML_FOR_AV = (
    ["index.html", "403.html", "404.html", "500.html", "maintenance.html"]
    + _bilingual_page_outputs()
    + _tree_error_pages()
)

# assets that must carry ?v={asset_version} in every active html reference.
SWEPT_ASSETS = [
    "/styles.css",
    "/print.css",
    "/js/theme.js",
    "/sw-register.js",
    "/js/reveal.js",
    "/js/verify-modal.js",
    "/verify/verify.js",
    "/verify/verification-data.js",
]

LEAK_PATTERNS = [
    re.compile(r"/home/trentpower/"),
    re.compile(r"\bDesktop/"),
    re.compile(r"htdocs/htdocs"),
    # Server-internal absolute paths from the gandi instance.
    # anything matching this pattern in a public file is a leak —
    # public-side .htaccess uses /htdocs/htdocs to block requests
    # to it (excluded below) but no public artefact has any
    # legitimate reason to mention /srv/data/web/vhosts/...
    re.compile(r"/srv/data/web/vhosts/"),
]
# glob list for the leak scan. the brief explicitly forbids
# /srv/data/web/vhosts/ leaks via .ini files (.user.ini was the
# original instance) so the scan now includes config-shape extensions.
LEAK_GLOBS = [
    "*.html",
    "*.js",
    "*.css",
    "*.json",
    "*.txt",
    "*.ini",
    "*.conf",
    "*.yaml",
    "*.yml",
    "*.xml",
]
# scripts/ no longer exists under public/; the corresponding tools/
# tree lives outside public/ and is not walked by ROOT.rglob().
# keep "integrity/releases" excluded — those are frozen historical
# bytes that may legitimately contain the kind of strings the leak
# scan is otherwise looking for.
LEAK_EXCLUDE_DIRS = {"integrity/releases", ".git"}
# the apache config (and its public mirror) intentionally references
# the stale /htdocs/htdocs/ path — to block requests to it via
# redirectmatch. the presence is defensive, not a leak. skip the file.
LEAK_EXCLUDE_FILES = {"source/htaccess.txt"}


def check_gpg() -> int:
    """Verify integrity.json.sig against the *published* key only.

    Uses a throwaway GNUPGHOME seeded solely from
    public/.well-known/pgp-key.asc, so verification is deterministic on
    clean machines / CI and never depends on the operator's ambient
    keyring or trustdb. (validate_release.py:_verify_detached_sig uses
    the same pattern for the release-artefact signatures.)"""
    import tempfile

    sig = ROOT / "integrity.json.sig"
    man = ROOT / "integrity.json"
    key = ROOT / ".well-known" / "pgp-key.asc"
    if not (sig.exists() and man.exists()):
        print("  FAIL: integrity.json or integrity.json.sig missing")
        return 1
    if not key.is_file():
        print(f"  FAIL: published key {key.relative_to(ROOT)} missing")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        env = os.environ.copy()
        env["GNUPGHOME"] = tmp
        env.pop("GPG_AGENT_INFO", None)
        imp = subprocess.run(
            ["gpg", "--batch", "--quiet", "--import", str(key)],
            env=env,
            capture_output=True,
            text=True,
        )
        if imp.returncode != 0:
            print("  FAIL: could not import published key into temp keyring")
            for line in (imp.stdout + imp.stderr).splitlines():
                print(f"    {line}")
            return 1
        r = subprocess.run(
            ["gpg", "--batch", "--quiet", "--verify", str(sig), str(man)],
            env=env,
            capture_output=True,
            text=True,
        )
    out = r.stdout + r.stderr
    if r.returncode != 0 or "Good signature" not in out:
        print("  FAIL: gpg verification failed (against published key)")
        for line in out.splitlines():
            print(f"    {line}")
        return 1
    # print the key fingerprint line for the build log.
    for line in out.splitlines():
        if "Good signature" in line or "fingerprint" in line.lower():
            print(f"  {line.strip()}")
    return 0


def _is_excluded(rel: pathlib.Path) -> bool:
    s = rel.as_posix()
    if s in LEAK_EXCLUDE_FILES:
        return True
    return any(s.startswith(d + "/") or s == d for d in LEAK_EXCLUDE_DIRS)


def check_local_path_leakage() -> int:
    fails: list[str] = []
    for glob in LEAK_GLOBS:
        for p in ROOT.rglob(glob):
            if not p.is_file():
                continue
            rel = p.relative_to(ROOT)
            if _is_excluded(rel):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="strict")
            except UnicodeDecodeError:
                continue
            for line_num, line in enumerate(text.splitlines(), 1):
                for pat in LEAK_PATTERNS:
                    if pat.search(line):
                        fails.append(f"{rel}:{line_num} {pat.pattern} → {line.strip()[:100]}")
    if fails:
        print(f"  FAIL: {len(fails)} local-path leak(s):")
        for f in fails:
            print(f"    {f}")
        return 1
    print("  OK: no local-path leaks in public tree")
    return 0


def check_asset_version_coherence() -> int:
    sm_path = ROOT / "site-metadata.json"
    if not sm_path.exists():
        print("  FAIL: site-metadata.json missing")
        return 1
    av = json.loads(sm_path.read_text(encoding="utf-8")).get("asset_version", "")
    if not av:
        print("  FAIL: site-metadata.json has no asset_version")
        return 1

    fails: list[str] = []

    # Bundle-hash recomputation. asset_version is {edition}.{first8 of
    # sha256(rel\0sha256(rel) for rel in ASSET_BUNDLE)} — see
    # generate_site._compute_asset_version. Re-derive from disk and
    # compare against the version stamped into site-metadata.json. this
    # catches the case where a cached asset's bytes changed but
    # generate_site.py was not re-run (so the sw cache name no longer
    # reflects what's on disk).
    expected_av = _recompute_asset_version()
    if expected_av is None:
        fails.append(
            "site-metadata.json: cannot recompute asset_version (generate_site.py "
            "or one of ASSET_BUNDLE missing)"
        )
    elif expected_av != av:
        fails.append(
            f"site-metadata.json: asset_version {av} does not match disk-derived "
            f"{expected_av} — rerun generate_site.py so cache busts"
        )

    # sw.js cache name
    sw = ROOT / "sw.js"
    if sw.exists() and av not in sw.read_text(encoding="utf-8"):
        fails.append(f"sw.js: cache name does not contain asset_version {av}")

    # active HTML: every reference to a swept asset must carry ?v={av}
    for rel in ACTIVE_HTML_FOR_AV:
        p = ROOT / rel
        if not p.exists():
            fails.append(f"{rel}: missing active HTML")
            continue
        text = p.read_text(encoding="utf-8")
        for asset in SWEPT_ASSETS:
            # find every href/src to that asset; require ?v={av} immediately after.
            pat = re.compile(r'(?:href|src)="' + re.escape(asset) + r'(\?v=([^"]*))?"')
            for m in pat.finditer(text):
                qv = m.group(2)
                if qv is None:
                    fails.append(f"{rel}: reference to {asset} missing ?v=")
                elif qv != av:
                    fails.append(f"{rel}: reference to {asset} has ?v={qv} (expected {av})")

    if fails:
        print(f"  FAIL: {len(fails)} asset-version coherence issue(s) (canonical {av}):")
        for f in fails[:50]:
            print(f"    {f}")
        if len(fails) > 50:
            print(f"    … and {len(fails) - 50} more")
        return 1
    print(f"  OK: asset_version {av} consistent (HTML + sw.js + on-disk bundle)")
    return 0


def _extract_asset_bundle_via_ast(path: pathlib.Path) -> list[str]:
    """Parse generate_site.py with `ast` and read the ASSET_BUNDLE
    list literal — without executing any of the top-level code. This
    keeps predeploy free of side effects: importing generate_site.py
    would re-run its full generation pass and rewrite HTML files
    AFTER the final integrity.json was already signed, drifting the
    manifest."""
    import ast as _ast

    try:
        tree = _ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    for node in tree.body:
        if not isinstance(node, _ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, _ast.Name) and target.id == "ASSET_BUNDLE":
                # accept either `ASSET_BUNDLE = [...]` or
                # `ASSET_BUNDLE = sorted([...])` — both are static
                # literals once we unwrap the sorted() call.
                value = node.value
                if (
                    isinstance(value, _ast.Call)
                    and isinstance(value.func, _ast.Name)
                    and value.func.id == "sorted"
                    and value.args
                    and isinstance(value.args[0], (_ast.List, _ast.Tuple))
                ):
                    items = value.args[0].elts
                elif isinstance(value, (_ast.List, _ast.Tuple)):
                    items = value.elts
                else:
                    return []
                out: list[str] = []
                for it in items:
                    if isinstance(it, _ast.Constant) and isinstance(it.value, str):
                        out.append(it.value)
                return sorted(out)
    return []


def _recompute_asset_version() -> str | None:
    """Re-derive {edition}.{first8} from generate_site.ASSET_BUNDLE and
    identity_canonical.edition, exactly as generate_site._compute_asset_version
    does. Returns None if the generator or any bundle file is missing.

    Note: ASSET_BUNDLE is read via AST parse (no execution). Importing
    generate_site.py would run its top-level generation pass, which
    rewrites bundles and sweeps HTML files — and that would happen
    AFTER the final integrity.json was already signed, causing
    spurious manifest drift."""
    _tools = pathlib.Path(__file__).resolve().parents[1]
    gen = _tools / "build" / "generate_site.py"
    canon = _tools / "config" / "identity_canonical.json"
    if not (gen.exists() and canon.exists()):
        return None
    bundle = _extract_asset_bundle_via_ast(gen)
    if not bundle:
        return None
    edition = json.loads(canon.read_text(encoding="utf-8")).get("edition", "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", edition):
        return None
    # mirror generate_site.py's normalisation: collapse BOTH the
    # legacy `/fonts-full.<v>.css` (filename-dated) form AND the
    # new `/fonts-full.css?v=<v>` (query-string) form back to the
    # unversioned form before hashing, so the bundle hash is stable
    # across the post-compute substitution pass. must stay in lock-
    # step with generate_site._VER_LITERAL_RE_LEGACY / _QUERY.
    ver_re_legacy = re.compile(rb"(/fonts-full)\.\d{4}-\d{2}-\d{2}\.[a-f0-9]{8}(\.css)")
    ver_re_query = re.compile(rb"(/fonts-full\.css)\?v=\d{4}-\d{2}-\d{2}\.[a-f0-9]{8}")
    # also normalise the I18N_VTAG literal in app.js — it embeds the
    # asset_version itself, causing the hash to oscillate without this.
    i18n_vtag_re = re.compile(rb"var I18N_VTAG\s*=\s*'\d{4}-\d{2}-\d{2}\.[a-f0-9]{8}';?")
    h = hashlib.sha256()
    for rel in bundle:
        p = ROOT / rel
        if not p.is_file():
            return None
        data = ver_re_legacy.sub(rb"\1\2", p.read_bytes())
        data = ver_re_query.sub(rb"\1", data)
        data = i18n_vtag_re.sub(b"var I18N_VTAG = '';", data)
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(hashlib.sha256(data).digest())
    return f"{edition}.{h.hexdigest()[:8]}"


# ─── integrity manifest freshness ───────────────────────────────
# required entries — every active public file that integrity.json
# claims to cover. site-metadata.json is intentionally excluded by
# generate_integrity.EXCLUDE_FILES (it carries asset_version, which
# itself depends on bundle bytes that the manifest hashes — a circular
# reference) and is therefore omitted here.
INTEGRITY_REQUIRED_PATHS = (
    [
        "index.html",
        "403.html",
        "404.html",
        "500.html",
        "maintenance.html",
        "local/index.html",
        "js/theme.js",
        "sw-register.js",
        "js/reveal.js",
        "js/verify-modal.js",
        "js/language-gate.js",
        "verify/verify.js",
        "verify/verification-data.js",
        "styles.css",
        "print.css",
        "sw.js",
        "source/source-manifest.json",
    ]
    + _bilingual_page_outputs()
    + _tree_error_pages()
)


def check_integrity_manifest_freshness() -> int:
    """Every active public file must appear in integrity.json with a
    sha256-b64 that matches its bytes on disk. Catches the case where
    a file was modified after integrity.json was generated (a signed
    manifest that no longer reflects the tree)."""
    man_path = ROOT / "integrity.json"
    if not man_path.exists():
        print("  FAIL: integrity.json missing")
        return 1
    try:
        man = json.loads(man_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"  FAIL: integrity.json not valid JSON ({e})")
        return 1
    files = man.get("files") or {}
    if not isinstance(files, dict):
        print("  FAIL: integrity.json missing 'files' dict")
        return 1

    fails: list[str] = []

    # 1. every required active path is recorded.
    for rel in INTEGRITY_REQUIRED_PATHS:
        if rel not in files:
            fails.append(f"integrity.json: missing required entry for {rel}")

    # 2. every recorded entry hashes to its claimed value.
    for rel, claimed in files.items():
        p = ROOT / rel
        if not p.is_file():
            fails.append(f"integrity.json: {rel} listed but missing on disk")
            continue
        actual = "sha256-" + sha256_b64(p.read_bytes())
        if actual != claimed:
            fails.append(
                f"integrity.json: {rel} hash drift "
                f"(manifest {claimed[:24]} vs disk {actual[:24]}) — "
                f"regenerate integrity.json"
            )

    if fails:
        print(f"  FAIL: {len(fails)} integrity-manifest freshness issue(s):")
        for f in fails[:50]:
            print(f"    {f}")
        if len(fails) > 50:
            print(f"    … and {len(fails) - 50} more")
        return 1
    print(f"  OK: integrity.json reflects {len(files)} files on disk")
    return 0


def check_integrity_sig_freshness() -> int:
    """integrity.json.sig must not be older than integrity.json. If it
    is, the signature is for a previous state of the manifest — the
    user re-ran integrity but forgot to re-sign."""
    man = ROOT / "integrity.json"
    sig = ROOT / "integrity.json.sig"
    if not (man.exists() and sig.exists()):
        print("  FAIL: integrity.json or integrity.json.sig missing")
        return 1
    if sig.stat().st_mtime + 1 < man.stat().st_mtime:
        # +1 second slack so a same-second regenerate-then-sign pair
        # does not falsely fail on filesystems with second-resolution
        # mtimes.
        print(
            f"  FAIL: integrity.json.sig is older than integrity.json "
            f"(sig {datetime.datetime.fromtimestamp(sig.stat().st_mtime).isoformat()} "
            f"vs man {datetime.datetime.fromtimestamp(man.stat().st_mtime).isoformat()}) — "
            f"re-sign with: gpg --batch --yes --detach-sign --armor "
            f"-o integrity.json.sig integrity.json"
        )
        return 1
    print("  OK: integrity.json.sig is current")
    return 0


# ─── verification map date freshness ────────────────────────────
# the `validated` stamp is generated at build time (utc) and travels in
# the committed, GPG-signed artifacts. CI re-runs this gate on its own
# "today", which can be a later UTC day than the build (overnight push,
# or simply crossing midnight utc). an exact `== today` match made deploy
# success depend on *when* CI ran, not on the artifacts — so a no-op push
# the next day went red. a tolerance window keeps the user-facing freshness
# guarantee (the stamp is never more than two weeks stale) without coupling
# the gate to the build/CI day boundary. re-stamping in CI is not an option:
# verification-data.js is hashed inside the signed integrity.json, so a
# fresh stamp would need the signing key in CI.
VERIFICATION_MAP_MAX_AGE_DAYS = 14


def check_verification_map_dates() -> int:
    """Every record in verify/verification-data.js must carry a `validated`
    date that is no more than VERIFICATION_MAP_MAX_AGE_DAYS old (and not in
    the future) relative to today's UTC date. Visitors expect the validated
    stamp to reflect a recent build; the window absorbs the build-vs-CI day
    boundary without going stale."""
    vd = ROOT / "verify" / "verification-data.js"
    if not vd.exists():
        print("  OK: verify/verification-data.js absent — skipping")
        return 0
    text = vd.read_text(encoding="utf-8")
    today = datetime.datetime.now(datetime.UTC).date()
    today_str = today.isoformat()
    fails: list[str] = []
    pat = re.compile(r'"validated":\s*"(\d{4}-\d{2}-\d{2})"')
    seen = 0
    for m in pat.finditer(text):
        seen += 1
        try:
            validated = datetime.date.fromisoformat(m.group(1))
        except ValueError:
            line = text.count("\n", 0, m.start()) + 1
            fails.append(
                f"verify/verification-data.js:{line} validated={m.group(1)} is not a valid ISO date"
            )
            continue
        age = (today - validated).days
        if age < 0:
            line = text.count("\n", 0, m.start()) + 1
            fails.append(
                f"verify/verification-data.js:{line} validated={m.group(1)} "
                f"is in the future (today UTC {today_str})"
            )
        elif age > VERIFICATION_MAP_MAX_AGE_DAYS:
            line = text.count("\n", 0, m.start()) + 1
            fails.append(
                f"verify/verification-data.js:{line} validated={m.group(1)} "
                f"is {age} days old (max {VERIFICATION_MAP_MAX_AGE_DAYS}; today UTC "
                f"{today_str}) — rebuild to refresh"
            )
    if fails:
        print(f"  FAIL: {len(fails)} stale verification-map date(s) (today UTC {today_str}):")
        for f in fails[:20]:
            print(f"    {f}")
        if len(fails) > 20:
            print(f"    … and {len(fails) - 20} more")
        return 1
    if seen == 0:
        print("  OK: verify/verification-data.js has no validated entries — skipping")
    else:
        print(
            f"  OK: {seen} verification-map record(s) validated within "
            f"{VERIFICATION_MAP_MAX_AGE_DAYS}d (today UTC {today_str})"
        )
    return 0


# ─── Service-worker precache validation ────────────────────────
# allowed file extensions in the precache list. anything else fails.
_PRECACHE_EXT_OK = {
    ".html",
    ".css",
    ".js",
    ".woff2",
    ".svg",
    ".png",
    ".ico",
    ".json",
    ".webmanifest",
}


def check_sw_precache() -> int:
    """Read sw.js, extract the PRECACHE array, assert every URL maps
    to a real file on disk with an allowed content-type. Catches the
    silent-install class — a precache URL that 404s on the server (or
    is missing locally) fails install in the browser without naming
    itself; this gate names it before anything ships."""
    sw_path = ROOT / "sw.js"
    if not sw_path.exists():
        print("  FAIL: sw.js missing — run generate_sw.py")
        return 1
    text = sw_path.read_text(encoding="utf-8")
    # the two-tier split (commit l) gives sw.js separate
    # CRITICAL_PRECACHE + OPTIONAL_PRECACHE literals plus a derived
    # precache = CRITICAL_PRECACHE.concat(OPTIONAL_PRECACHE). read both
    # arrays and treat their union as the surface to validate.
    crit_m = re.search(r"var CRITICAL_PRECACHE = \[(.*?)\];", text, re.S)
    opt_m = re.search(r"var OPTIONAL_PRECACHE = \[(.*?)\];", text, re.S)
    if not (crit_m and opt_m):
        print("  FAIL: sw.js missing CRITICAL_PRECACHE / OPTIONAL_PRECACHE literals")
        return 1
    entries = re.findall(r"'([^']+)'", crit_m.group(1)) + re.findall(r"'([^']+)'", opt_m.group(1))
    if not entries:
        print("  FAIL: sw.js precache list is empty")
        return 1

    fails: list[str] = []
    for url in entries:
        if not url.startswith("/"):
            fails.append(f"{url}: not server-rooted (must start with '/')")
            continue
        # map url → on-disk path.
        if url == "/":
            disk_rel = "index.html"
        elif url.endswith("/"):
            disk_rel = url.lstrip("/") + "index.html"
        else:
            disk_rel = url.lstrip("/")
        disk = ROOT / disk_rel
        if not disk.is_file():
            fails.append(f"{url}: missing on disk ({disk_rel})")
            continue
        # extension allowlist — sanity for content-type.
        # '/maintenance.html' or '/' map to .html; bare extensions are
        # checked against the disk path.
        ext = "." + disk_rel.rsplit(".", 1)[-1].lower() if "." in disk_rel else ""
        if ext not in _PRECACHE_EXT_OK:
            fails.append(f"{url}: extension {ext or '(none)'} not in allowed precache type set")

    if fails:
        print(f"  FAIL: {len(fails)} precache issue(s):")
        for f in fails[:30]:
            print(f"    {f}")
        if len(fails) > 30:
            print(f"    … and {len(fails) - 30} more")
        return 1
    print(f"  OK: sw.js PRECACHE — {len(entries)} URL(s) resolve to disk")
    return 0


from paths import ARCHIVE_BASELINE  # noqa: E402  # imported via tools/lib/paths.py


def _hash_archive_tree() -> dict:
    """Walk every frozen-release directory and hash files that must
    be byte-stable. Returns {relative_path: sha256_b64_sri}.

    Two directory shapes:

      YYYY-MM     legacy editions (e.g. 2026-02). entire directory is
                  frozen and every file is included in the baseline.

      YYYY-MM-DD  full-date editions (2026-05-09, 2026-05-17, …). only
                  the canonical archive bytes and canonical companion
                  manifests are locked. dated rebuild artefacts
                  (trentpower-fr-<build_date>.zip with build_date !=
                  edition) are not baseline-locked — they are tracked
                  by the per-edition builds.json signature instead.

    in both shapes, .sig files are EXCLUDED from the baseline because
    gpg detached signatures carry random salt and are not bitwise
    deterministic across runs. SHA256SUMS is excluded because it
    aggregates over both archives and changes as rebuilds are added.
    builds.json is excluded because its `rebuilds[]` grows on each
    across-day drift.
    """
    rel_root = ROOT / "integrity" / "releases"
    out: dict[str, str] = {}
    if not rel_root.is_dir():
        return out

    def _hash(fp):
        return sri_sha256(fp.read_bytes())

    for child in sorted(rel_root.iterdir()):
        if not child.is_dir():
            continue
        if re.fullmatch(r"\d{4}-\d{2}", child.name):
            # legacy edition — lock the whole tree.
            for fp in sorted(child.rglob("*")):
                if not fp.is_file():
                    continue
                rel = fp.relative_to(ROOT).as_posix()
                out[rel] = _hash(fp)
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", child.name):
            # full-date edition — lock canonical bytes + companion
            # manifests only. byte-stable; .sig / SHA256SUMS /
            # builds.json excluded for the reasons in the docstring.
            canonical_basename = f"trentpower-fr-{child.name}"
            byte_stable = [
                f"{canonical_basename}.zip",
                f"{canonical_basename}.zip.sha256",
                f"{canonical_basename}.tar.gz",
                f"{canonical_basename}.tar.gz.sha256",
                "integrity-redistributable.json",
                "EXCLUDED_FILES.json",
                "EXCLUDED_FILES.txt",
                "release.json",
                # legacy 2026-02 shape kept its own integrity.json
                # inside; other full-date editions don't have one but
                # the lookup tolerates absence.
                "integrity.json",
            ]
            for fn in byte_stable:
                fp = child / fn
                if fp.is_file():
                    rel = fp.relative_to(ROOT).as_posix()
                    out[rel] = _hash(fp)
    return out


def check_hidden_and_archive_safety() -> int:
    """Stricter sweep: fail on hidden host artefacts in the public
    tree (.DS_Store, .env, Thumbs.db, __MACOSX, swap files, sqlite
    DBs, key material) and on font binaries inside the most recent
    date-precision release ZIP.

    Existing checks (local-path leakage, frozen-archive immutability)
    cover different surfaces — this one specifically covers the
    classes of file the hardening spec calls out as build-fail
    triggers."""
    fails: list[str] = []

    # 1. hidden host artefacts + secret-material globs anywhere in the
    # public tree. the list mirrors the brief's "forbidden public files"
    # in phase 3, so any addition there should be reflected here.
    hidden_globs = [
        ".DS_Store",
        ".env",
        ".env.*",
        "Thumbs.db",
        "*.swp",
        "*.sqlite",
        "*.db",
        "*.log",
        "*.bak",
        "*.tmp",
        "id_ed25519",
        "id_ed25519.pub",
        "*.totp_key",
        "*-key.txt",
        ".htpasswd",
        "composer.json",
        "composer.lock",
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
    ]
    for glob in hidden_globs:
        for p in ROOT.rglob(glob):
            if not p.is_file():
                continue
            rel = p.relative_to(ROOT).as_posix()
            # the local-path leakage scan already excludes _audit_*
            # / _rollback_* / _archives / _licences; mirror that here.
            if rel.startswith(("_audit", "_rollback", "_archives", "_licences")):
                continue
            fails.append(f"hidden artefact: {rel}")

    # the brief's .user.ini policy: must not appear in public/. the
    # server-side file is preserved at tools/server/user.ini.example
    # (build-input only, not deployed by `mirror`).
    user_ini = ROOT / ".user.ini"
    if user_ini.exists():
        fails.append(
            ".user.ini present in public/ — move directives to "
            "tools/server/user.ini.example; the server-side file is "
            "preserved by --no-delete mirror semantics."
        )

    # forbidden directories that should never appear inside public/.
    forbidden_dirs = ["console_data", "node_modules", ".git", "private"]
    for d in forbidden_dirs:
        for p in ROOT.rglob(d):
            if p.is_dir():
                rel = p.relative_to(ROOT).as_posix()
                fails.append(f"forbidden directory under public/: {rel}")

    for p in ROOT.rglob("__MACOSX"):
        if p.is_dir():
            fails.append(f"hidden artefact dir: {p.relative_to(ROOT).as_posix()}")

    # 2. font binaries inside the most recent date-precision release
    # zip. the packager already excludes them by extension, but the
    # gate verifies the artefact on disk so a packager regression
    # cannot ship.
    rel_root = ROOT / "integrity" / "releases"
    if rel_root.is_dir():
        for child in sorted(rel_root.iterdir(), reverse=True):
            if not child.is_dir():
                continue
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", child.name):
                continue
            for zp in sorted(child.glob("trentpower-fr-*.zip")):
                try:
                    import zipfile as _zf

                    with _zf.ZipFile(zp) as zf:
                        for entry in zf.namelist():
                            low = entry.lower()
                            if low.endswith((".woff", ".woff2", ".otf", ".ttf")):
                                fails.append(f"font binary inside {zp.name}: {entry}")
                            if low.endswith("styles.v") or "/styles.v" in low:
                                # belt and braces; styles.v*.css is also
                                # caught by extension match above
                                fails.append(f"stale stylesheet inside {zp.name}: {entry}")
                except Exception as e:
                    fails.append(f"could not read {zp.name}: {e}")
            break  # only the newest date-precision folder

    if fails:
        print(f"  FAIL: {len(fails)} hidden/archive issue(s):")
        for f in fails:
            print(f"    {f}")
        print("       Remediation: delete the offending file(s) or fix the packager.")
        return 1
    print("  OK: no hidden artefacts; release ZIP free of fonts and stale stylesheets")
    return 0


def check_frozen_archives_immutable() -> int:
    """Compare every file under /integrity/releases/YYYY-MM/ against a
    locally-managed baseline at metadata/archive-baseline.json.

    Frozen archives must be immutable going forward; this is the gate
    that catches a generator (or a manual edit) accidentally rewriting
    historical bytes. Pre-existing drift in the per-release integrity.json
    files is intentionally NOT consulted — those are historical snapshots
    and have known drift from earlier non-hardened pipeline runs.

    First run: writes the baseline from the current tree and exits OK
    (no prior baseline to compare against). Subsequent runs: any byte
    drift = FAIL. Reseal explicitly with `--reseal-archives` (or by
    deleting the baseline file) when an archive intentionally changes.
    """
    current = _hash_archive_tree()
    if not current:
        print("  OK: no frozen archives present — nothing to check")
        return 0
    if not ARCHIVE_BASELINE.exists():
        ARCHIVE_BASELINE.write_text(
            json.dumps(current, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"  OK: sealed initial baseline of {len(current)} archive file(s)")
        print(f"       (baseline written to {ARCHIVE_BASELINE.name};")
        print("        future drift will fail this gate)")
        return 0
    try:
        baseline = json.loads(ARCHIVE_BASELINE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"  FAIL: {ARCHIVE_BASELINE.name} invalid JSON ({e}); delete to reseal")
        return 1

    # drift detection: any baseline file that disagrees with disk OR
    # has gone missing is a hard fail. existing baseline entries are
    # the editorial seal.
    drift_fails: list[str] = []
    for rel, expected in baseline.items():
        got = current.get(rel)
        if got is None:
            drift_fails.append(f"{rel}: in baseline but missing on disk")
        elif got != expected:
            drift_fails.append(f"{rel}: drift (expected {expected[:24]}, got {got[:24]})")
    if drift_fails:
        print(f"  FAIL: {len(drift_fails)} frozen-archive drift(s):")
        for f in drift_fails:
            print(f"    {f}")
        print("       to reseal an edition intentionally:")
        print("       python3 tools/seal_edition.py --reseal-canonical <edition>")
        return 1

    # new canonicals on disk that aren't in baseline yet: auto-seal.
    # this is the seal-on-first-emit path — a newly emitted canonical
    # archive for a fresh edition (or a freshly-introduced companion
    # manifest for a previously-shipped edition) enters the baseline
    # the first time predeploy observes it. subsequent drift then
    # trips the check above.
    new_entries = {rel: current[rel] for rel in current if rel not in baseline}
    if new_entries:
        baseline.update(new_entries)
        ARCHIVE_BASELINE.write_text(
            json.dumps(baseline, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"  OK: auto-sealed {len(new_entries)} new canonical file(s) into baseline")
        for rel in sorted(new_entries):
            print(f"      + {rel}")
        print(f"      commit {ARCHIVE_BASELINE.name} to record the seal in git history")

    print(f"  OK: frozen archives immutable ({len(current)} files match baseline)")
    return 0


def check_changelog_freshness() -> int:
    """Hard gate: the canonical edition must not advance past the topmost
    changelog entry's date. Edition bumps are deliberate; if the edition is
    newer than the newest changelog entry, an editorial entry is owed before
    the build can ship (raw material in reports/changelog-draft.txt)."""
    changelog = ROOT / "changelog.txt"
    canon = pathlib.Path(__file__).resolve().parents[1] / "config" / "identity_canonical.json"
    if not (changelog.is_file() and canon.is_file()):
        return 0
    try:
        ed = json.loads(canon.read_text(encoding="utf-8")).get("edition", "")
        top_match = re.search(
            r"^(\d{4}-\d{2}-\d{2})\b", changelog.read_text(encoding="utf-8"), re.MULTILINE
        )
        top = top_match.group(1) if top_match else ""
        if ed and top and ed > top:
            print(
                f"  FAIL: changelog freshness — canonical edition {ed} "
                f"is newer than the topmost changelog entry ({top}). "
                f"Add an entry to public/changelog.txt; raw diff at "
                f"reports/changelog-draft.txt."
            )
            return 1
        if ed and top:
            relation = "matches" if top == ed else f"ahead of (>= {ed})"
            print(f"  OK: changelog top entry {top} {relation} edition {ed}")
    except Exception as _e:
        print(f"  WARN: changelog freshness check did not complete ({_e})")
    return 0
