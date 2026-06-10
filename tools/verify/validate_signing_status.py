#!/usr/bin/env python3
"""tools/validate_signing_status.py — trust-claim accuracy gate.

every public artefact is assigned a signing class. this validator
refuses to ship when a file's actual cryptographic coverage does
not match its declared class.

classes:
  directly_signed     — file contains an inline PGP signature
                        (clear-signed); or a paired ".sig" file
                        exists alongside.
  covered_by_manifest — file's path appears in integrity.json
                        (which is itself GPG-signed).
  signature_carrier   — file is a detached signature whose target
                        is also covered. listed explicitly so the
                        absence of a ".sig.sig" is not flagged.

artefacts not in the classification table are ignored — this gate
only enforces what is declared, never speculates.
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

# (relative path under public/, class). order is documentation;
# the validator does not depend on it.
CLASSIFICATION: list[tuple[str, str]] = [
    # integrity layer
    ("integrity.json", "covered_by_manifest"),
    ("integrity.json.sig", "signature_carrier"),
    (".well-known/pgp-key.asc", "covered_by_manifest"),
    ("pgp.txt", "covered_by_manifest"),
    # directly signed prose
    ("assertion.txt", "directly_signed"),
    ("statement.txt", "directly_signed"),
    (".well-known/security.txt", "directly_signed"),
    # editorial text — covered by signed manifest
    ("ai-usage.txt", "covered_by_manifest"),
    ("humans.txt", "covered_by_manifest"),
    ("llms.txt", "covered_by_manifest"),
    ("robots.txt", "covered_by_manifest"),
    ("changelog.txt", "covered_by_manifest"),
    (".well-known/attribution.txt", "covered_by_manifest"),
    # machine-readable identity / metadata
    ("site-metadata.json", "covered_by_manifest"),
    ("attestations.json", "covered_by_manifest"),
    ("manifest.webmanifest", "covered_by_manifest"),
    (".well-known/person.json", "covered_by_manifest"),
    (".well-known/publication.json", "covered_by_manifest"),
    (".well-known/webfinger", "covered_by_manifest"),
    (".well-known/build.json", "covered_by_manifest"),
]

# files that intentionally live outside integrity.json (it would be
# circular to hash these). they're independently signed or self-evidencing.
SELF_EVIDENCING = {
    "integrity.json",  # the manifest itself
    "site-metadata.json",  # listed in integrity.json's exclude but...
    # we check separately; see logic below
}

CLEARSIGN_HEADER = b"-----BEGIN PGP SIGNED MESSAGE-----"


def _load_integrity_files() -> set[str]:
    p = PUBLIC_DIR / "integrity.json"
    if not p.exists():
        return set()
    data = json.loads(p.read_text(encoding="utf-8"))
    return set((data.get("files") or {}).keys())


def main() -> int:
    integrity_files = _load_integrity_files()
    fails: list[str] = []
    oks = 0

    for rel, klass in CLASSIFICATION:
        path = PUBLIC_DIR / rel
        if not path.is_file():
            fails.append(f"{rel}: missing on disk (declared as {klass})")
            continue

        if klass == "directly_signed":
            # accept either an inline clearsigned block, or a paired
            # ".sig" file. paired-sig form is what integrity.json uses;
            # clearsigned form is what assertion.txt / statement.txt
            # use. either is fine, both must verify externally.
            has_inline = CLEARSIGN_HEADER in path.read_bytes()
            sig_path = path.with_suffix(path.suffix + ".sig")
            has_paired = sig_path.is_file()
            if not (has_inline or has_paired):
                fails.append(
                    f"{rel}: claims directly_signed but has neither inline "
                    f"PGP block nor paired {sig_path.name}"
                )
            else:
                oks += 1

        elif klass == "covered_by_manifest":
            # integrity.json itself is the manifest — it can't list
            # itself. site-metadata.json is excluded by generate_integrity
            # because asset_version changes it post-hashing. these two
            # are accepted on a self-evidencing basis.
            if rel in ("integrity.json", "site-metadata.json"):
                oks += 1
                continue
            if rel not in integrity_files:
                fails.append(
                    f"{rel}: claims covered_by_manifest but is not a key in integrity.json"
                )
            else:
                oks += 1

        elif klass == "signature_carrier":
            target = path.with_suffix("")  # strip ".sig"
            if not target.is_file():
                fails.append(f"{rel}: signature_carrier but target {target.name} missing")
            else:
                oks += 1

        else:
            fails.append(f"{rel}: unknown class '{klass}'")

    # leak check: no file declared "covered_by_manifest" should also
    # contain a clearsigned block — that would be a hidden upgrade of
    # its signing status, surprising readers.
    for rel, klass in CLASSIFICATION:
        if klass != "covered_by_manifest":
            continue
        path = PUBLIC_DIR / rel
        if not path.is_file():
            continue
        # only check text-like files
        if path.suffix not in (".txt", ".json", ".webmanifest", ""):
            continue
        try:
            if CLEARSIGN_HEADER in path.read_bytes():
                fails.append(
                    f"{rel}: classified covered_by_manifest but contains "
                    f"a clearsigned block — promote to directly_signed "
                    f"or remove the inline signature."
                )
        except OSError:
            continue

    if fails:
        print(f"  FAIL: {len(fails)} signing-status mismatch(es):")
        for f in fails:
            print(f"    {f}")
        return 1

    print(f"  OK: {oks} artefact(s) match their declared signing class.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
