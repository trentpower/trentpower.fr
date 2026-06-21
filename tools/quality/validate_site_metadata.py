#!/usr/bin/env python3
"""validate_site_metadata.py — canonical schema gate.

enforces the published shape of public/site-metadata.json. the
schema is documented in docs/PUBLIC-ARTEFACT-CONVENTIONS.md.

required top-level keys:
  type, schema_version, name, description, url, canonical_url,
  language, edition, author, publisher, information_classes,
  trust_order, integrity, privacy, citation, license,
  machine_readable, asset_version

forbidden top-level keys (regression gates):
  asset_bundle — the build inventory belongs to integrity.json
                 and to ASSET_BUNDLE in generate_site.py; it must
                 not duplicate into the editorial / identity record.

required nested shapes:
  edition.{id,label,date}
  integrity.{manifest,signature,public_key,checksums}
  privacy.{tracking,analytics,cookies,third_party_requests,attestations}
  citation.{text,format}
  license.{content,portrait}
  machine_readable.{person,webfinger,security,attestations}

integrity.checksums url must resolve to a real file on disk at
the path /SHA256SUMS (project root).

Shape (deep module, small interface). The filesystem is the one injected seam —
`Repo(root)` — so the whole gate runs over a fixture repo with no monkeypatching.
`load(repo)` reads + parses site-metadata.json; `evaluate(repo, data)` is pure
(it applies the required-keys / forbidden-keys / nested-shape / value rules and
returns a Result, never printing or raising); `main()` is the only adapter that
prints and exits. Behaviour is byte-identical to the former inline gate.
"""

from __future__ import annotations

import json
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
SM_REL = "public/site-metadata.json"
CHECKSUMS_REL = "public/SHA256SUMS"

REQUIRED_TOP = {
    "type",
    "schema_version",
    "name",
    "description",
    "url",
    "canonical_url",
    "language",
    "edition",
    "author",
    "publisher",
    "information_classes",
    "trust_order",
    "integrity",
    "privacy",
    "citation",
    "license",
    "machine_readable",
    "asset_version",
}

FORBIDDEN_TOP = {"asset_bundle"}

NESTED_REQUIRED = {
    "edition": {"id", "label", "date"},
    "integrity": {"manifest", "signature", "public_key", "checksums"},
    "privacy": {"tracking", "analytics", "cookies", "third_party_requests", "attestations"},
    "citation": {"text", "format"},
    "license": {"content", "portrait"},
    "machine_readable": {"person", "webfinger", "security", "attestations"},
    "information_classes": {"declared", "attested"},
}


# ---------------------------------------------------------------------------
# Result — the value that flows through the interface. evaluate() produces it;
# main() renders it. tests assert on Result, never on stdout.
# ---------------------------------------------------------------------------
@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    oks: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fails


# ---------------------------------------------------------------------------
# load — read + parse the input. returns (data, errors); never prints/exits.
# the missing-file / invalid-JSON FAIL lines are part of the stdout contract,
# so they are carried as errors and rendered by main() (to stdout).
# ---------------------------------------------------------------------------
def load(repo: Repo) -> tuple[dict | None, list[str]]:
    if not repo.is_file(SM_REL):
        return None, [f"{repo.root / SM_REL} missing"]
    try:
        data = json.loads(repo.read(SM_REL))
    except json.JSONDecodeError as e:
        return None, [f"site-metadata.json invalid JSON ({e})"]
    return data, []


# ---------------------------------------------------------------------------
# evaluate — the compute interface. one call, one Result, over the injected
# Repo + parsed data. this is the test surface.
# ---------------------------------------------------------------------------
def evaluate(repo: Repo, data: dict) -> Result:
    r = Result()

    keys = set(data.keys())
    missing = REQUIRED_TOP - keys
    if missing:
        r.fails.append(f"missing required top-level keys: {sorted(missing)}")
    forbidden_present = FORBIDDEN_TOP & keys
    if forbidden_present:
        r.fails.append(
            f"forbidden top-level key(s) present: {sorted(forbidden_present)} — "
            f"the build inventory belongs in integrity.json + ASSET_BUNDLE, "
            f"not in site-metadata.json"
        )

    for key, required in NESTED_REQUIRED.items():
        if key not in data:
            continue  # already caught by REQUIRED_TOP missing above
        value = data[key]
        if not isinstance(value, dict):
            r.fails.append(f"'{key}' must be an object, got {type(value).__name__}")
            continue
        missing_nested = required - set(value.keys())
        if missing_nested:
            r.fails.append(f"'{key}' missing nested keys: {sorted(missing_nested)}")

    # type + schema_version exact-value gates
    if data.get("type") != "PersonalSiteMetadata":
        r.fails.append(f"type must be 'PersonalSiteMetadata', got {data.get('type')!r}")
    if data.get("schema_version") != "1.0":
        r.fails.append(f"schema_version must be '1.0', got {data.get('schema_version')!r}")

    # language must be a list of locale strings
    lang = data.get("language")
    if not (isinstance(lang, list) and all(isinstance(x, str) for x in lang)):
        r.fails.append(f"language must be a list of strings, got {lang!r}")

    # checksums url must point at a real file on disk
    checksums_url = (data.get("integrity") or {}).get("checksums", "")
    if checksums_url.endswith("/SHA256SUMS"):
        if not repo.is_file(CHECKSUMS_REL):
            r.fails.append(
                "integrity.checksums points at /SHA256SUMS but "
                "public/SHA256SUMS does not exist on disk"
            )

    if r.ok:
        r.oks.append(
            f"site-metadata.json schema_version "
            f"{data.get('schema_version')}, {len(keys)} top-level keys, "
            f"no forbidden keys, all nested shapes present."
        )
    return r


# ---------------------------------------------------------------------------
# main — the side-effecting adapter. loads, evaluates, renders, returns exit
# code. the only place stdout and exit codes live.
# ---------------------------------------------------------------------------
def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)

    data, errors = load(repo)
    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
        return 1

    r = evaluate(repo, data)

    if r.fails:
        print(f"  FAIL: {len(r.fails)} site-metadata.json issue(s):")
        for f in r.fails:
            print(f"    {f}")
        return 1

    for line in r.oks:
        print(f"  OK: {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
