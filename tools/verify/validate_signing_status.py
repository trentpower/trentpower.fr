#!/usr/bin/env python3
"""validate_signing_status.py — trust-claim accuracy gate.

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

Shape (deep module, small interface). The filesystem is the one injected seam —
`Repo(root)` — so the whole gate runs over a fixture repo with no
monkeypatching. `load(repo)` reads the one config input (integrity.json's file
set) into a Ctx; `evaluate(repo, ctx)` is the pure compute path returning a
Result and never prints or exits; `main()` is the only adapter that prints and
exits. Behaviour is byte-identical to the former direct-PUBLIC_DIR
implementation.

Exit 0 = every artefact matches its declared signing class. Exit 1 = a mismatch.
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


# named accessors over the shared Repo seam. the public-tree knowledge (the
# "public/" prefix) lives here in the validator, not on Repo.
def _public_rel(rel: str) -> str:
    return f"public/{rel}"


def _read_public_bytes(repo: Repo, rel: str) -> bytes:
    """raw bytes of public/<rel> — the clearsign-header check is byte-level,
    not text, so it must not go through utf-8 decoding."""
    return (repo.root / _public_rel(rel)).read_bytes()


def _public_is_file(repo: Repo, rel: str) -> bool:
    return repo.is_file(_public_rel(rel))


def _strip_suffix(rel: str) -> str:
    """drop the final ".sig" suffix from a signature-carrier path
    (mirrors Path.with_suffix(""))."""
    return rel[: -len(Path(rel).suffix)] if Path(rel).suffix else rel


def _add_sig_suffix(rel: str) -> str:
    """paired-sig name for a file (mirrors with_suffix(suffix + ".sig"))."""
    return rel + ".sig"


# ---------------------------------------------------------------------------
# Ctx / Result — the values that flow through the interface. load() produces
# Ctx (or errors); evaluate() produces Result; main() renders it. tests assert
# on Result, never on stdout.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Ctx:
    integrity_files: set[str]


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    oks: int = 0

    @property
    def ok(self) -> bool:
        return not self.fails


# ---------------------------------------------------------------------------
# load — read + parse the one input (integrity.json's file set). returns
# (ctx, errors); never prints/exits. a missing manifest yields an empty set,
# exactly as the former _load_integrity_files() did.
# ---------------------------------------------------------------------------
def load(repo: Repo) -> tuple[Ctx | None, list[str]]:
    if not _public_is_file(repo, "integrity.json"):
        return Ctx(integrity_files=set()), []
    data = json.loads(repo.read(_public_rel("integrity.json")))
    return Ctx(integrity_files=set((data.get("files") or {}).keys())), []


# ---------------------------------------------------------------------------
# evaluate — the compute interface. one call, one Result, over the injected
# Repo + Ctx. this is the test surface.
# ---------------------------------------------------------------------------
def evaluate(repo: Repo, ctx: Ctx) -> Result:
    r = Result()
    integrity_files = ctx.integrity_files

    for rel, klass in CLASSIFICATION:
        if not _public_is_file(repo, rel):
            r.fails.append(f"{rel}: missing on disk (declared as {klass})")
            continue

        if klass == "directly_signed":
            # accept either an inline clearsigned block, or a paired
            # ".sig" file. paired-sig form is what integrity.json uses;
            # clearsigned form is what assertion.txt / statement.txt
            # use. either is fine, both must verify externally.
            has_inline = CLEARSIGN_HEADER in _read_public_bytes(repo, rel)
            sig_rel = _add_sig_suffix(rel)
            has_paired = _public_is_file(repo, sig_rel)
            if not (has_inline or has_paired):
                r.fails.append(
                    f"{rel}: claims directly_signed but has neither inline "
                    f"PGP block nor paired {Path(sig_rel).name}"
                )
            else:
                r.oks += 1

        elif klass == "covered_by_manifest":
            # integrity.json itself is the manifest — it can't list
            # itself. site-metadata.json is excluded by generate_integrity
            # because asset_version changes it post-hashing. these two
            # are accepted on a self-evidencing basis.
            if rel in ("integrity.json", "site-metadata.json"):
                r.oks += 1
                continue
            if rel not in integrity_files:
                r.fails.append(
                    f"{rel}: claims covered_by_manifest but is not a key in integrity.json"
                )
            else:
                r.oks += 1

        elif klass == "signature_carrier":
            target_rel = _strip_suffix(rel)  # strip ".sig"
            if not _public_is_file(repo, target_rel):
                r.fails.append(
                    f"{rel}: signature_carrier but target {Path(target_rel).name} missing"
                )
            else:
                r.oks += 1

        else:
            r.fails.append(f"{rel}: unknown class '{klass}'")

    # leak check: no file declared "covered_by_manifest" should also
    # contain a clearsigned block — that would be a hidden upgrade of
    # its signing status, surprising readers.
    for rel, klass in CLASSIFICATION:
        if klass != "covered_by_manifest":
            continue
        if not _public_is_file(repo, rel):
            continue
        # only check text-like files
        if Path(rel).suffix not in (".txt", ".json", ".webmanifest", ""):
            continue
        try:
            if CLEARSIGN_HEADER in _read_public_bytes(repo, rel):
                r.fails.append(
                    f"{rel}: classified covered_by_manifest but contains "
                    f"a clearsigned block — promote to directly_signed "
                    f"or remove the inline signature."
                )
        except OSError:
            continue

    return r


# ---------------------------------------------------------------------------
# main — the side-effecting adapter. loads, evaluates, renders, returns exit
# code. the only place stdout and exit codes live.
# ---------------------------------------------------------------------------
def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)

    ctx, errors = load(repo)
    if errors or ctx is None:
        for e in errors:
            print(f"  FAIL: {e}")
        return 1

    r = evaluate(repo, ctx)

    if r.fails:
        print(f"  FAIL: {len(r.fails)} signing-status mismatch(es):")
        for f in r.fails:
            print(f"    {f}")
        return 1

    print(f"  OK: {r.oks} artefact(s) match their declared signing class.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
