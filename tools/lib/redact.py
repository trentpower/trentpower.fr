"""
redact.py · single source of truth for masking secret values in output.

the secret scanners exist to TELL the operator something leaked — but
echoing the matched value verbatim re-leaks it into terminals and ci
logs (a codeql clear-text-logging finding). mask_secret() keeps the
finding actionable without reprinting any part of the secret: the
masked length identifies the shape, and a sha-256 fingerprint
correlates the same value across runs and files. no prefix of the
value is ever included — even a few leading characters keep the
finding taint-flagged and ease targeted guessing.
"""

from __future__ import annotations

import hashlib


def mask_secret(value: str) -> str:
    """mask value for safe printing, e.g. '[40 chars, sha256:1a2b3c4d]'."""
    fingerprint = hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:8]
    return f"[{len(value)} chars, sha256:{fingerprint}]"
