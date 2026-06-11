"""
redact.py · single source of truth for masking secret values in output.

the secret scanners exist to TELL the operator something leaked — but
echoing the matched value verbatim re-leaks it into terminals and ci
logs (a codeql clear-text-logging finding). mask_secret() keeps the
finding actionable without reprinting the secret: a short prefix to
recognise it by, the masked length, and a sha-256 fingerprint to
correlate the same value across runs and files.
"""

from __future__ import annotations

import hashlib


def mask_secret(value: str, keep: int = 4) -> str:
    """mask value for safe printing, e.g. 'ghp_…[40 chars, sha256:1a2b3c4d]'."""
    fingerprint = hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:8]
    prefix = value[:keep] if len(value) > keep else ""
    return f"{prefix}…[{len(value)} chars, sha256:{fingerprint}]"
