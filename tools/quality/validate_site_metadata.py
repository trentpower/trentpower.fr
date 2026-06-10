#!/usr/bin/env python3
"""tools/validate_site_metadata.py — canonical schema gate.

enforces the published shape of public/site-metadata.json. the
schema is documented in docs/public-artefact-conventions.md.

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
"""

import json
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
from paths import PUBLIC_DIR  # noqa: E402

SM_PATH = PUBLIC_DIR / "site-metadata.json"

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


def main() -> int:
    if not SM_PATH.is_file():
        print(f"  FAIL: {SM_PATH} missing")
        return 1
    try:
        data = json.loads(SM_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"  FAIL: site-metadata.json invalid JSON ({e})")
        return 1

    fails: list[str] = []

    keys = set(data.keys())
    missing = REQUIRED_TOP - keys
    if missing:
        fails.append(f"missing required top-level keys: {sorted(missing)}")
    forbidden_present = FORBIDDEN_TOP & keys
    if forbidden_present:
        fails.append(
            f"forbidden top-level key(s) present: {sorted(forbidden_present)} — "
            f"the build inventory belongs in integrity.json + ASSET_BUNDLE, "
            f"not in site-metadata.json"
        )

    for key, required in NESTED_REQUIRED.items():
        if key not in data:
            continue  # already caught by REQUIRED_TOP missing above
        value = data[key]
        if not isinstance(value, dict):
            fails.append(f"'{key}' must be an object, got {type(value).__name__}")
            continue
        missing_nested = required - set(value.keys())
        if missing_nested:
            fails.append(f"'{key}' missing nested keys: {sorted(missing_nested)}")

    # type + schema_version exact-value gates
    if data.get("type") != "PersonalSiteMetadata":
        fails.append(f"type must be 'PersonalSiteMetadata', got {data.get('type')!r}")
    if data.get("schema_version") != "1.0":
        fails.append(f"schema_version must be '1.0', got {data.get('schema_version')!r}")

    # language must be a list of locale strings
    lang = data.get("language")
    if not (isinstance(lang, list) and all(isinstance(x, str) for x in lang)):
        fails.append(f"language must be a list of strings, got {lang!r}")

    # checksums url must point at a real file on disk
    checksums_url = (data.get("integrity") or {}).get("checksums", "")
    if checksums_url.endswith("/SHA256SUMS"):
        if not (PUBLIC_DIR / "SHA256SUMS").is_file():
            fails.append(
                "integrity.checksums points at /SHA256SUMS but "
                "public/SHA256SUMS does not exist on disk"
            )

    if fails:
        print(f"  FAIL: {len(fails)} site-metadata.json issue(s):")
        for f in fails:
            print(f"    {f}")
        return 1

    print(
        f"  OK: site-metadata.json schema_version "
        f"{data.get('schema_version')}, {len(keys)} top-level keys, "
        f"no forbidden keys, all nested shapes present."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
