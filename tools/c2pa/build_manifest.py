#!/usr/bin/env python3
"""tools/c2pa/build_manifest.py — build the C2PA manifest payload for one asset.

Reads the two existing sources of truth — policy-data/c2pa-assets.yml (what the
asset is, its canonical URL, its declared AI posture) and
tools/config/identity_canonical.json (who the author/publisher is) — and emits
the JSON manifest a C2PA signer embeds. Identity facts are NOT duplicated here;
they are read from the canonical files so they cannot drift.

The assertions are deliberately modest and factual (see docs/C2PA.md): who
published it, its canonical URL, its AI-involvement value, and that it is also
listed in the PGP-signed integrity manifest. No "authentic" / "verified true" /
"human-made" claims.

Pure: no c2pa dependency, no signing. `build_manifest(asset, policy, identity)`
returns a dict; the signer (sign_asset.py) consumes it. CLI prints it as JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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
from paths import IDENTITY_CANONICAL, REPO_ROOT  # noqa: E402

POLICY_PATH = REPO_ROOT / "policy-data" / "c2pa-assets.yml"
INTEGRITY_URL = "https://trentpower.fr/integrity.json"
AI_MEANINGS = {
    "no-ai-in-release-path": (
        "AI may assist drafting or development, but no AI system participates in "
        "the build, signing, verification or deployment of this asset."
    ),
}

# IPTC digital source type for the c2pa.created action, derived honestly from the
# asset's declared AI involvement. c2pa-rs 0.89 validates the c2pa.actions
# assertion strictly — an asset signed WITHOUT an explicit, well-formed action
# assertion gets a malformed auto-default and fails validation, so this is
# required, not optional. Authored media maps to `digitalCreation`; only media
# produced or altered by a generative model may claim the trained-algorithmic
# source types (none of the in-scope assets do).
IPTC_DIGITALSOURCE = "http://cv.iptc.org/newscodes/digitalsourcetype/"
AI_TO_SOURCE_TYPE = {
    "image-generated": IPTC_DIGITALSOURCE + "trainedAlgorithmicMedia",
    "image-edited": IPTC_DIGITALSOURCE + "compositeWithTrainedAlgorithmicMedia",
}
DEFAULT_SOURCE_TYPE = IPTC_DIGITALSOURCE + "digitalCreation"


def load_policy(path: Path = POLICY_PATH) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_identity(path: Path = IDENTITY_CANONICAL) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def find_asset(policy: dict, asset_path: str) -> dict | None:
    for a in policy.get("assets", []):
        if a.get("path") == asset_path:
            return a
    return None


def _public_rel(asset_path: str) -> str:
    return asset_path[len("public/") :] if asset_path.startswith("public/") else asset_path


def build_manifest(asset: dict, policy: dict, identity: dict) -> dict:
    """Build the C2PA manifest dict for one declared asset."""
    person = identity.get("person", {})
    author_name = asset.get("author") or person.get("name", "")
    publisher_name = asset.get("publisher") or policy.get("publisher", {}).get("name", "")
    canonical_url = asset["canonical_url"]
    edition = identity.get("edition", "")
    ai = asset.get("ai_involvement", "unknown")

    creative_work = {
        "@context": "https://schema.org",
        "@type": "CreativeWork",
        "author": [{"@type": "Person", "name": author_name}],
        "publisher": {"@type": "Organization", "name": publisher_name},
        "url": canonical_url,
    }
    orcid = person.get("orcid")
    if orcid:
        creative_work["author"][0]["identifier"] = f"https://orcid.org/{orcid}"

    return {
        "claim_generator_info": [
            {"name": "trentpower.fr", "version": edition or "unversioned"}
        ],
        "title": Path(asset["path"]).name,
        "assertions": [
            {
                "label": "c2pa.actions.v2",
                "data": {
                    "actions": [
                        {
                            "action": "c2pa.created",
                            "digitalSourceType": AI_TO_SOURCE_TYPE.get(ai, DEFAULT_SOURCE_TYPE),
                        }
                    ]
                },
                "kind": "Json",
            },
            {"label": "stds.schema-org.CreativeWork", "data": creative_work, "kind": "Json"},
            {
                "label": "com.trentpower.ai-involvement",
                "data": {"value": ai, "meaning": AI_MEANINGS.get(ai, "see policy-data/c2pa-assets.yml")},
                "kind": "Json",
            },
            {
                "label": "com.trentpower.integrity",
                "data": {
                    "note": "This file is also listed, by hash, in the PGP-signed integrity manifest.",
                    "manifest": INTEGRITY_URL,
                    "path": _public_rel(asset["path"]),
                },
                "kind": "Json",
            },
        ],
    }


def manifest_for_path(asset_path: str) -> dict:
    policy = load_policy()
    asset = find_asset(policy, asset_path)
    if asset is None:
        raise SystemExit(f"error: {asset_path} is not declared in policy-data/c2pa-assets.yml")
    if "canonical_url" not in asset:
        raise SystemExit(f"error: {asset_path} has no canonical_url (status {asset.get('status')!r})")
    return build_manifest(asset, policy, load_identity())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the C2PA manifest JSON for a declared asset.")
    ap.add_argument("asset_path", help="repo-relative path, e.g. public/images/architecture/architecture.en.svg")
    args = ap.parse_args(argv)
    print(json.dumps(manifest_for_path(args.asset_path), indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
