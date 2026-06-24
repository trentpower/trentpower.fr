"""
hashing.py · single source of truth for digest wire-formats.

the pipeline renders the same digest in a few shapes, and the shape is
a contract: integrity manifests, file catalogues, subresource-integrity
attributes and csp script hashes all use the "sha256-"/"sha384-" prefixed
base64 form (the SRI encoding — the manifest deliberately borrows it),
the source-mirror records use bare base64, and a handful of internal
comparisons use lowercase hex. writers and validators that re-derive a
digest import the matching helper here instead of re-spelling the
hashlib/base64 incantation, so a shape can never drift between the
writer and its checker.

two exceptions stay where they live, by design: bespoke composite
hashes (e.g. the asset-bundle hash chain in inline_checks.py) are not
single-digest wire-formats; and a coherence gate that exists to catch
SRI drift (validate_sri_coherence) re-derives independently on purpose —
sharing this helper would let a bug here hide on both sides of its check.
only single-digest formatting is canonical here.
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

_CHUNK = 1024 * 1024


def sha256_hex(data: bytes) -> str:
    """lowercase hex digest — the integrity.json / file-metadata shape."""
    return hashlib.sha256(data).hexdigest()


def sha256_file_hex(path: Path) -> str:
    """lowercase hex digest of a file, streamed in 1 MiB chunks."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def sha256_b64(data: bytes) -> str:
    """bare base64 digest — the source-mirror record shape."""
    return base64.b64encode(hashlib.sha256(data).digest()).decode("ascii")


def sri_sha256(data: bytes) -> str:
    """sri shape — "sha256-" prefixed base64 digest (SRI / csp script-hash)."""
    return "sha256-" + sha256_b64(data)


def sri_sha384(data: bytes) -> str:
    """sri shape — "sha384-" prefixed base64 digest (subresource-integrity)."""
    return "sha384-" + base64.b64encode(hashlib.sha384(data).digest()).decode("ascii")


__all__ = ["sha256_hex", "sha256_file_hex", "sha256_b64", "sri_sha256", "sri_sha384"]
