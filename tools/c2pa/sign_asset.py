#!/usr/bin/env python3
"""tools/c2pa/sign_asset.py — sign one asset with a Pi-local C2PA credential.

Signing is local-only (the build host is aarch64, where no c2patool binary ships;
see docs/C2PA-SPIKE.md). Private signing material lives OUTSIDE the repo under
$TRENTPOWER_C2PA_DIR (default ~/.config/trentpower/c2pa) and is never read into
logs or committed. The certificate is self-signed: it binds a consistent claimed
identity, not a trust-listed one (docs/C2PA.md, docs/SECRETS-AND-KEY-MANAGEMENT.md).

Manifest content comes from build_manifest.py (policy + canonical identity). This
script is the c2pa adapter only: load key material, sign, write output. It fails
clearly if the signing material is missing — it never invents a key.

    python3 tools/c2pa/sign_asset.py <asset_path> [--out PATH]

By default the signed file is written beside the source as <name>.signed<ext> so a
signing run never clobbers the committed asset; promoting it into public/ is a
separate, deliberate step.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_manifest as bm  # noqa: E402

DEFAULT_DIR = os.path.expanduser("~/.config/trentpower/c2pa")
SIGNING_ALG = b"es256"


def signing_dir() -> Path:
    return Path(os.environ.get("TRENTPOWER_C2PA_DIR", DEFAULT_DIR))


def _load_material(d: Path) -> tuple[bytes, bytes]:
    chain, key = d / "chain.pem", d / "signer.key"
    missing = [str(p) for p in (chain, key) if not p.is_file()]
    if missing:
        raise SystemExit(
            "error: C2PA signing material not found: "
            + ", ".join(missing)
            + f"\n  Set $TRENTPOWER_C2PA_DIR or generate it (see tools/c2pa/README.md). Looked in {d}."
        )
    return chain.read_bytes(), key.read_bytes()


def _signer(chain: bytes, key: bytes):
    try:
        from c2pa import C2paSignerInfo, Signer  # noqa: PLC0415
    except ImportError:
        raise SystemExit(
            "error: c2pa-python not importable. Run this with the signing venv, e.g.\n"
            "  ~/.local/share/trentpower/c2pa-venv/bin/python tools/c2pa/sign_asset.py ..."
        )
    info = C2paSignerInfo(SIGNING_ALG, chain, key, b"placeholder")
    info.ta_url = None  # no timestamp authority; keeps one less non-deterministic input
    return Signer.from_info(info)


def sign(declared_path: str, source_path: str, out_path: str) -> str:
    import json  # noqa: PLC0415

    from c2pa import Builder  # noqa: PLC0415

    # the manifest (title, canonical URL, assertions) is built from the DECLARED
    # asset; the bytes signed come from SOURCE (a generated original may be signed
    # into a /provenance/ distribution copy). They are the same file unless the
    # policy entry sets `source`.
    manifest = bm.manifest_for_path(declared_path)
    chain, key = _load_material(signing_dir())
    signer = _signer(chain, key)
    Builder(json.dumps(manifest)).sign_file(source_path, out_path, signer)
    return out_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Sign one declared asset with the Pi-local C2PA credential."
    )
    ap.add_argument("asset_path", help="repo-relative DECLARED path of the asset (policy key)")
    ap.add_argument("--out", help="output path (default: the declared path itself)")
    args = ap.parse_args(argv)

    policy = bm.load_policy()
    entry = bm.find_asset(policy, args.asset_path)
    if entry is None:
        raise SystemExit(f"error: {args.asset_path} is not declared in policy-data/c2pa-assets.yml")
    source = entry.get("source", args.asset_path)
    src = Path(source)
    if not src.is_file():
        raise SystemExit(f"error: source bytes not found: {src}")
    out = args.out or args.asset_path
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    sign(args.asset_path, source, out)
    print(f"  OK: signed {source} -> {out}  (canonical {entry.get('canonical_url')})")
    print(f"  (verify with: tools/c2pa/inspect_asset.py {out})")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
