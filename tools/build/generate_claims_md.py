#!/usr/bin/env python3
"""tools/build/generate_claims_md.py — render docs/CLAIMS.md from claims-map.yml.

The public-promise ledger lives as data in policy-data/claims-map.yml. This
generator renders the human-readable view, docs/CLAIMS.md, from that single
source. A blocking drift gate (claims_map_drift in tools/lib/checks.py) runs
this with --check so the doc can never drift from the data.

Mirrors the generate_routes_json.py --check pattern: a generator that either
writes the file or, with --check, exits non-zero if the committed file differs
from a fresh render.

Usage:
    python3 tools/build/generate_claims_md.py            # write docs/CLAIMS.md
    python3 tools/build/generate_claims_md.py --check    # exit 1 on drift
"""

from __future__ import annotations

import argparse
import sys

try:
    import yaml
except ImportError:
    print("error: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

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

CLAIMS_MAP = REPO_ROOT / "policy-data" / "claims-map.yml"
OUT_PATH = REPO_ROOT / "docs" / "CLAIMS.md"

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _esc(text: str) -> str:
    """escape pipe so a wording string cannot break the markdown table."""
    return text.replace("|", "\\|")


def _rows(claims: dict) -> list[str]:
    # stable, reviewable order: severity then token name.
    ordered = sorted(
        claims.items(), key=lambda kv: (_SEVERITY_ORDER.get(kv[1]["severity"], 9), kv[0])
    )
    rows = []
    for token, c in ordered:
        rows.append(
            "| `{token}` | {wording} | {sev} | {stated} | {verified} | {enforced} | "
            "{status} | {blocking} | {owner} | {reviewed} |".format(
                token=token,
                wording=_esc(c["public_wording"]),
                sev=c["severity"],
                stated="<br>".join(f"`{p}`" for p in c["stated_in"]),
                verified="<br>".join(f"`{v}`" for v in c["verified_by"]) or "—",
                enforced=", ".join(c["enforced_at"]),
                status=c["status"],
                blocking="yes" if c["release_blocking"] else "no",
                owner=c["owner"],
                reviewed=c["last_reviewed"],
            )
        )
    return rows


def build() -> str:
    data = yaml.safe_load(CLAIMS_MAP.read_text(encoding="utf-8"))
    claims = data["claims"]
    surface = data["claim_surface"]
    notes = data.get("manual_notes", [])

    lines: list[str] = []
    lines.append("<!-- GENERATED FILE — do not edit by hand. -->")
    lines.append(
        "<!-- Source: policy-data/claims-map.yml · "
        "Generator: tools/build/generate_claims_md.py · "
        "Drift gate: claims_map_drift (blocking). -->")
    lines.append("")
    lines.append("# Public claims ledger")
    lines.append("")
    lines.append(
        "Every public supply-chain promise this project makes, and the executable "
        "control that backs it. This page is generated from "
        "`policy-data/claims-map.yml` and held in lock-step with it by the blocking "
        "`claims_map_drift` gate — the human view cannot drift from the policy data."
    )
    lines.append("")
    lines.append(
        "**Policy as data, enforcement as code.** The map declares *what* is claimed "
        "and *which* control backs it; `tools/verify/validate_claims_parity.py` decides "
        "*whether* each control passes by collecting real evidence — running gpg, parsing "
        "`release.yml`, checking files on disk."
    )
    lines.append("")
    lines.append("## Why no OPA / Conftest / rego / Node")
    lines.append("")
    lines.append(
        "A policy engine evaluates data someone has already collected. Here the hard "
        "work *is* the collection — there is little neat JSON to reason over and a great "
        "deal of evidence to gather. Rego could not run gpg or parse a workflow file, so "
        "it would add a layer without removing any work. The bindings are data (this "
        "ledger); the evaluation stays executable Python. See "
        "`docs/SECURITY-PIPELINE.md`."
    )
    lines.append("")
    lines.append("## Claims")
    lines.append("")
    lines.append(
        "| Claim | Public wording | Severity | Stated in | Verified by | Enforced at | "
        "Status | Release-blocking | Owner | Last reviewed |"
    )
    lines.append(
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"
    )
    lines.extend(_rows(claims))
    lines.append("")
    lines.append("## Claim surface")
    lines.append("")
    lines.append(
        "Where the gate looks for claims. The map *describes* claims; it does not decide "
        "where the repo may state them — the scanner walks this wider surface, so a claim "
        "added to an unlisted public page is still seen and still must be backed."
    )
    lines.append("")
    lines.append("**Included:**")
    lines.append("")
    for pat in surface.get("include", []):
        lines.append(f"- `{pat}`")
    if surface.get("exclude"):
        lines.append("")
        lines.append("**Excluded:**")
        lines.append("")
        for pat in surface["exclude"]:
            lines.append(f"- `{pat}`")
    lines.append("")
    lines.append("## Manual boundaries")
    lines.append("")
    lines.append(
        "The limits no automated control can close, recorded beside the automated ones "
        "so the trust story is honest about its edges."
    )
    lines.append("")
    for n in notes:
        note = " ".join(n["note"].split())
        lines.append(f"- **{n['topic']}.** {note}")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="render docs/CLAIMS.md from claims-map.yml")
    ap.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the committed docs/CLAIMS.md differs from a fresh render",
    )
    args = ap.parse_args(argv)

    text = build()

    if args.check:
        rel = OUT_PATH.relative_to(REPO_ROOT)
        if not OUT_PATH.exists():
            print(f"FAIL: {rel} is missing — run tools/build/generate_claims_md.py")
            return 1
        if OUT_PATH.read_text(encoding="utf-8") != text:
            print(
                f"FAIL: {rel} drifted from policy-data/claims-map.yml — "
                "regenerate with tools/build/generate_claims_md.py"
            )
            return 1
        print(f"OK: {rel} matches policy-data/claims-map.yml")
        return 0

    OUT_PATH.write_text(text, encoding="utf-8")
    print(f"wrote {OUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
