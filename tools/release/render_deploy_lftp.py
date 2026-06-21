#!/usr/bin/env python3
"""render_deploy_lftp.py — render the gitignored SFTP recipe from the template.

Reads the host + account from the environment ONLY (the same secret names the CI
deploy workflow uses) and substitutes them into deploy.sftp.lftp.template,
writing the concrete deploy.sftp.lftp (which .gitignore keeps out of the repo).
The values are never printed, and the password is never handled here — lftp
prompts for it at connect time.

    export SFTP_USERNAME=…  SFTP_HOST=…
    python3 tools/release/render_deploy_lftp.py

Exit 0 = rendered. Exit 2 = a required env var is unset (nothing written).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
TEMPLATE = _DIR / "deploy.sftp.lftp.template"
OUTPUT = _DIR / "deploy.sftp.lftp"

# only these are substituted; password is always lftp-prompted, never rendered.
REQUIRED = ("SFTP_USERNAME", "SFTP_HOST")


def render(env: dict[str, str]) -> str:
    """Pure substitution of ${VAR} for the required keys. Raises KeyError naming
    the first missing var (never echoing any value)."""
    text = TEMPLATE.read_text(encoding="utf-8")
    for key in REQUIRED:
        if not env.get(key):
            raise KeyError(key)
        text = text.replace("${" + key + "}", env[key])
    return text


def main() -> int:
    try:
        rendered = render(os.environ)
    except KeyError as missing:
        print(
            f"error: required env var {missing.args[0]} is unset — "
            "export SFTP_USERNAME and SFTP_HOST from your secret store first.",
            file=sys.stderr,
        )
        return 2
    OUTPUT.write_text(rendered, encoding="utf-8")
    # never echo the rendered values; just confirm the write.
    print(
        f"  OK: rendered {OUTPUT.name} ({OUTPUT.stat().st_size} bytes) — gitignored, do not commit"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
