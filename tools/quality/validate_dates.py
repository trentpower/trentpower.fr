#!/usr/bin/env python3
"""validate_dates.py — fail the build on any date drift between the
content-history-anchored manifest and the visible date surfaces.

Single source of truth: public/file-metadata.json["files"][rel]["modified_iso"].
Every active surface that prints a date — sitemap.xml <lastmod>, JSON-LD
"dateModified", security.txt Expires, integrity.json "generated" — is
cross-checked against the manifest. Documented exceptions live in
tools/config/date_overrides.json with a `reason` per leaf.

The /verify/ tree owns the word "Validated"/"Validé" by policy; any
other appearance of either word is a regression of the renamed
print-evidence chip ("Edition <date>") and fails this gate.

Unresolved {{lastmod:*}} / {{datemod:*}} placeholders are a missed
sweep step and fail the gate so the operator re-runs the build.

Exit 0 = every date surface matches the manifest (or a reasoned override).
Exit 1 = at least one drift; failing paths are printed.

Shape (deep module, small interface). The external interface is `main() -> int`
plus the OK/WARN/ERROR text contract. Internally the two dependencies are
injected seams — `Repo(root)` for the filesystem and a `now` instant for the
clock — so the whole gate is exercised through `evaluate(repo, ctx, now) ->
Result` over a fixture repo at a frozen instant, with no monkeypatching. Compute
(`evaluate`) is separate from render (`main`): the former returns a Result and
never prints or exits; the latter is the only side-effecting adapter.
"""

from __future__ import annotations

import datetime
import json
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

# repo-relative locations of the inputs (resolved through the Repo seam).
IDENTITY_CANONICAL_REL = "tools/config/identity_canonical.json"
DATE_OVERRIDES_REL = "tools/config/date_overrides.json"
MANIFEST_REL = "public/file-metadata.json"
SITEMAP_REL = "public/sitemap.xml"
INTEGRITY_REL = "public/integrity.json"
SECURITY_TXT_REL = "public/.well-known/security.txt"

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


# named accessors over the shared Repo seam. the public-tree knowledge (the
# "public/" prefix, recursive walks) lives here in the validator, not on Repo.
def _read_public(repo: Repo, prel: str) -> str:
    return repo.read(f"public/{prel}")


def _public_glob(repo: Repo, pattern: str) -> list[str]:
    """recursive public-tree walk — returns public-relative posix paths.
    exclusion policy is NOT applied here (it is domain logic, kept in
    _active_html)."""
    prefix = "public/"
    return [rel[len(prefix):] for rel in repo.glob(f"{prefix}**/{pattern}")]


def _read_json(repo: Repo, rel: str):
    return json.loads(repo.read(rel))


def _active_html(repo: Repo) -> list[str]:
    """public-relative paths of every active .html — frozen archive snapshots
    and build-output editorial-review documents excluded (the exclusion policy)."""
    out: list[str] = []
    for rel in _public_glob(repo, "*.html"):
        if rel.startswith(FROZEN_PREFIX):
            continue
        if rel.startswith(EDITORIAL_REVIEW_PREFIXES):
            continue
        out.append(rel)
    return out


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


# ---------------------------------------------------------------------------
# Ctx / Result — the values that flow through the interface. load() produces
# Ctx (or errors); evaluate() produces Result; main() renders it. tests assert
# on Result, never on stdout.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Ctx:
    edition: str
    manifest: dict
    overrides: dict


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    warns: list[str] = field(default_factory=list)
    oks: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fails


# ---------------------------------------------------------------------------
# checks — accumulate findings into the Result (decision: mutation stays
# internal, behind the evaluate interface). each reads through the Repo seam.
# ---------------------------------------------------------------------------
def check_overrides_have_reasons(overrides: dict, r: Result) -> None:
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
                    r.fails.append(
                        f"date_overrides.json: {section}[{key}] missing non-empty 'reason'"
                    )
    r.oks.append(
        f"overrides: {counts['published']} published, {counts['modified']} modified, "
        f"{counts['lastmod']} lastmod, {counts['expires']} expires (all carry reason)"
    )


def check_sitemap(repo: Repo, manifest: dict, overrides: dict, edition: str, r: Result) -> None:
    """every <loc>/<lastmod> pair: lastmod must equal manifest.modified_iso
    or an explicit override declaration. files excluded from the manifest
    (integrity.json, site-metadata.json, integrity.json.sig) must declare
    a lastmod override so the date surface still has an audit trail.
    """
    if not repo.is_file(SITEMAP_REL):
        r.fails.append("sitemap.xml: missing")
        return
    text = repo.read(SITEMAP_REL)
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
            r.fails.append(
                f"sitemap: <loc>{url}</loc> has no manifest entry "
                f"({disk_rel}) and no lastmod override — add an entry "
                f"to date_overrides.json.lastmod with a reason"
            )
            continue
        if actual != expected:
            r.fails.append(
                f"sitemap: <lastmod>{actual}</lastmod> for {url} but {source} says {expected}"
            )
    r.oks.append(f"sitemap.xml: {seen} URLs checked")


def check_jsonld_datemod(repo: Repo, manifest: dict, r: Result) -> None:
    """every json-ld dateModified prefix (YYYY-MM-DD) must equal the
    manifest's modified_iso for the same file. catches the bug-class
    where a per-page generator hardcodes the edition or a past date
    rather than emitting the {{datemod:<path>}} placeholder."""
    files = manifest.get("files", {})
    checked_files = 0
    checked_values = 0
    for rel in _active_html(repo):
        text = _read_public(repo, rel)
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
                r.fails.append(f"{rel}: dateModified={val!r} does not start with YYYY-MM-DD")
                continue
            prefix = iso_m.group(1)
            if expected is None:
                r.fails.append(
                    f"{rel}: dateModified={val} present but no manifest entry "
                    f"for this path — add the file to the manifest or fix the generator"
                )
                continue
            if prefix != expected:
                line = text.count("\n", 0, m.start()) + 1
                r.fails.append(
                    f"{rel}:{line} dateModified={val} (date prefix {prefix}) "
                    f"but manifest says {expected}"
                )
    r.oks.append(
        f"json-ld dateModified: {checked_values} value(s) across {checked_files} file(s) checked"
    )


def check_integrity_generated(repo: Repo, now: datetime.datetime, r: Result) -> None:
    """integrity.json.generated must not be in the future relative to
    today utc. catches a build clock skew that would otherwise mint a
    manifest dated tomorrow."""
    if not repo.is_file(INTEGRITY_REL):
        r.fails.append("integrity.json: missing")
        return
    try:
        gen = _read_json(repo, INTEGRITY_REL).get("generated", "")
    except json.JSONDecodeError as e:
        r.fails.append(f"integrity.json: invalid JSON ({e})")
        return
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", gen):
        r.fails.append(f"integrity.json: generated={gen!r} is not YYYY-MM-DD")
        return
    today = now.strftime("%Y-%m-%d")
    if gen > today:
        r.fails.append(f"integrity.json: generated={gen} is in the future (today UTC {today})")
        return
    r.oks.append(f"integrity.json: generated={gen} (today UTC {today})")


def check_no_placeholders(repo: Repo, r: Result) -> None:
    """no file under public/ may carry an unresolved {{lastmod:*}} or
    {{datemod:*}} token. the sweep pass in generate_file_metadata.py
    rewrites these against the manifest; survivors mean the sweep was
    skipped or a generator emitted a token after the sweep ran."""
    leaks: list[str] = []
    for ext in PLACEHOLDER_EXTS:
        for rel in _public_glob(repo, f"*{ext}"):
            if rel.startswith(FROZEN_PREFIX):
                continue
            try:
                text = _read_public(repo, rel)
            except UnicodeDecodeError:
                continue
            m = PLACEHOLDER_RE.search(text)
            if m:
                line = text.count("\n", 0, m.start()) + 1
                leaks.append(f"{rel}:{line} unresolved placeholder near {m.group(0)}")
    if leaks:
        for leak in leaks:
            r.fails.append(f"placeholder: {leak}")
        return
    r.oks.append("no unresolved placeholders")


def check_validated_word(repo: Repo, r: Result) -> None:
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
    for rel in _active_html(repo):
        text = _read_public(repo, rel)
        for m in VALIDATED_RE.finditer(text):
            window_start = max(0, m.start() - 200)
            window = text[window_start : m.start()]
            if '<script type="application/ld+json">' in window and "</script>" not in window:
                continue
            line = text.count("\n", 0, m.start()) + 1
            r.fails.append(
                f"{rel}:{line} '{m.group(0)}' — non-canonical trust term; "
                f"the canonical freshness label is 'Verified' / 'Vérifié'"
            )
            hits += 1
    if hits == 0:
        r.oks.append('no non-canonical "Validated"/"Validé" anywhere')


def check_security_txt_expires(repo: Repo, overrides: dict, now: datetime.datetime, r: Result) -> None:
    """security.txt must carry an Expires line in the future. if an
    override declares the expected expiry, mismatch surfaces as a
    warning (the override is documentation, not enforcement)."""
    if not repo.is_file(SECURITY_TXT_REL):
        r.fails.append(".well-known/security.txt: missing")
        return
    text = repo.read(SECURITY_TXT_REL)
    m = EXPIRES_RE.search(text)
    if not m:
        r.fails.append(".well-known/security.txt: no Expires: line found")
        return
    raw = m.group(1)
    # rfc 3339 forms — accept z or +HH:MM offsets, with optional fractional
    # seconds. python's fromisoformat needs the z stripped pre-3.11.
    try:
        norm = raw.replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(norm)
    except ValueError:
        r.fails.append(f".well-known/security.txt: Expires={raw!r} not parseable as RFC 3339")
        return
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.UTC)
    if dt <= now:
        r.fails.append(
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
            r.warns.append(
                f".well-known/security.txt: Expires date {actual_date} "
                f"differs from override {expected_date} (override is documentation)"
            )
    r.oks.append(f"security.txt Expires={raw} ({dt.date().isoformat()})")


def check_stale_files(manifest: dict, edition: str, r: Result) -> None:
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
            r.warns.append(
                f"stale: {rel} last changed {iso}, edition {edition} ({(ed - d).days} days)"
            )


# ---------------------------------------------------------------------------
# load — read + validate the inputs. returns (ctx, errors); never prints/exits.
# ---------------------------------------------------------------------------
def load(repo: Repo) -> tuple[Ctx | None, list[str]]:
    if not repo.is_file(IDENTITY_CANONICAL_REL):
        return None, [f"{IDENTITY_CANONICAL_REL} not found"]
    edition = _read_json(repo, IDENTITY_CANONICAL_REL).get("edition", "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", edition):
        return None, [f"canonical edition '{edition}' is not YYYY-MM-DD"]
    if not repo.is_file(MANIFEST_REL):
        return None, [f"{MANIFEST_REL} not found — run generate_file_metadata.py"]
    manifest = _read_json(repo, MANIFEST_REL)
    overrides: dict = {}
    if repo.is_file(DATE_OVERRIDES_REL):
        try:
            overrides = _read_json(repo, DATE_OVERRIDES_REL)
        except json.JSONDecodeError as e:
            return None, [f"date_overrides.json invalid ({e})"]
    return Ctx(edition=edition, manifest=manifest, overrides=overrides), []


# ---------------------------------------------------------------------------
# evaluate — the compute interface. one call, one Result, over the injected
# Repo + now. this is the test surface.
# ---------------------------------------------------------------------------
def evaluate(repo: Repo, ctx: Ctx, now: datetime.datetime) -> Result:
    r = Result()
    check_overrides_have_reasons(ctx.overrides, r)
    check_sitemap(repo, ctx.manifest, ctx.overrides, ctx.edition, r)
    check_jsonld_datemod(repo, ctx.manifest, r)
    check_integrity_generated(repo, now, r)
    check_no_placeholders(repo, r)
    check_validated_word(repo, r)
    check_security_txt_expires(repo, ctx.overrides, now, r)
    check_stale_files(ctx.manifest, ctx.edition, r)
    r.oks.append(f"file-metadata.json: {len(ctx.manifest.get('files', {}))} entries consulted")
    return r


# ---------------------------------------------------------------------------
# main — the side-effecting adapter. loads, evaluates, renders, returns exit
# code. the only place stdout and exit codes live.
# ---------------------------------------------------------------------------
def main(repo_root: Path = REPO_ROOT, now: datetime.datetime | None = None) -> int:
    repo = Repo(repo_root)
    now = now or datetime.datetime.now(datetime.UTC)

    ctx, errors = load(repo)
    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        return 1

    r = evaluate(repo, ctx, now)

    print("DATE CHECK")
    for line in r.oks:
        print(f"OK {line}")
    for line in r.warns:
        print(f"WARN {line}")
    for line in r.fails:
        print(f"ERROR {line}")

    if r.fails:
        print(f"RESULT: {len(r.fails)} error(s), {len(r.warns)} warning(s)")
        return 1
    print("RESULT: green" if not r.warns else f"RESULT: green, {len(r.warns)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
