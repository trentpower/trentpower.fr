"""
hashing.py · single source of truth for sha-256 digest formatting.

the pipeline renders the same digest in three shapes, and the shape is
a contract: integrity manifests and file catalogues use lowercase hex,
subresource-integrity attributes and csp script hashes use the
"sha256-" prefixed base64 form, and the source-mirror records use bare
base64. validators that re-derive a digest import the matching helper
here instead of re-spelling the hashlib/base64 incantation, so a shape
can never drift between the writer and its checker.

bespoke composite hashes (e.g. the asset-bundle hash chain in
inline_checks.py) stay where they live — only the single-digest
formatting is canonical here.
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


__all__ = ["sha256_hex", "sha256_file_hex", "sha256_b64", "sri_sha256"]
