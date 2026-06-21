#!/usr/bin/env python3
"""validate_asset_version.py — asset_version agrees across site-metadata.json,
sw.js, the active HTML ?v= references, AND the bundle hash recomputed from disk.

The recompute catches the case where a cached asset's bytes changed but
generate_site.py was not re-run (so the sw cache name no longer reflects what's
on disk).

Shape (deep module, small interface). The filesystem is the one injected seam —
`Repo(root)`. The bundle-hash derivation (`recompute_asset_version`, which
AST-parses generate_site.py without executing it) is split from the coherence
checks: `evaluate(repo, recomputed)` takes the recomputed version as input, so
the coherence logic (drift, sw.js, ?v= sweep) is exercised over a small fixture
without standing up the full asset bundle; `recompute_asset_version` has its own
focused test. `main()` is the only adapter that prints/exits. Byte-identical to
the former inline_checks.check_asset_version_coherence.

Exit 0 = asset_version coherent everywhere. Exit 1 = any disagreement.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
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
import public_inventory as _pi  # noqa: E402
from paths import REPO_ROOT  # noqa: E402
from repo import Repo  # noqa: E402  (shared filesystem evidence seam)

SITE_METADATA_REL = "public/site-metadata.json"
SW_REL = "public/sw.js"

# assets that must carry ?v={asset_version} in every active html reference.
SWEPT_ASSETS = [
    "/styles.css",
    "/print.css",
    "/js/theme.js",
    "/sw-register.js",
    "/js/reveal.js",
    "/js/verify-modal.js",
    "/verify/verify.js",
    "/verify/verification-data.js",
]

# /sw-reset/ deliberately omitted from the sweep: the recovery page references
# stylesheets without ?v= so it can never be served from a stale varnish layer.
_ACTIVE_HTML_LITERAL = ["index.html", "403.html", "404.html", "500.html", "maintenance.html"]


def active_html_for_av() -> list[str]:
    return _ACTIVE_HTML_LITERAL + _pi.page_outputs() + _pi.error_page_outputs()


def _extract_asset_bundle_via_ast(path: Path) -> list[str]:
    """Parse generate_site.py with `ast` and read the ASSET_BUNDLE list literal
    — without executing any top-level code. Importing generate_site.py would
    re-run its full generation pass and rewrite HTML AFTER the final
    integrity.json was already signed, drifting the manifest."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "ASSET_BUNDLE":
                value = node.value
                if (
                    isinstance(value, ast.Call)
                    and isinstance(value.func, ast.Name)
                    and value.func.id == "sorted"
                    and value.args
                    and isinstance(value.args[0], (ast.List, ast.Tuple))
                ):
                    items = value.args[0].elts
                elif isinstance(value, (ast.List, ast.Tuple)):
                    items = value.elts
                else:
                    return []
                out: list[str] = []
                for it in items:
                    if isinstance(it, ast.Constant) and isinstance(it.value, str):
                        out.append(it.value)
                return sorted(out)
    return []


def recompute_asset_version(repo: Repo) -> str | None:
    """Re-derive {edition}.{first8} from generate_site.ASSET_BUNDLE and
    identity_canonical.edition, exactly as generate_site._compute_asset_version
    does. Returns None if the generator or any bundle file is missing.

    ASSET_BUNDLE is read via AST parse (no execution): importing generate_site.py
    would run its top-level generation pass, rewriting bundles and HTML AFTER the
    final integrity.json was signed, causing spurious manifest drift."""
    gen = repo.root / "tools" / "build" / "generate_site.py"
    canon = repo.root / "tools" / "config" / "identity_canonical.json"
    if not (gen.exists() and canon.exists()):
        return None
    bundle = _extract_asset_bundle_via_ast(gen)
    if not bundle:
        return None
    edition = json.loads(canon.read_text(encoding="utf-8")).get("edition", "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", edition):
        return None
    # mirror generate_site.py's normalisation: collapse BOTH the legacy
    # `/fonts-full.<v>.css` (filename-dated) form AND the new
    # `/fonts-full.css?v=<v>` (query-string) form back to the unversioned form
    # before hashing, so the bundle hash is stable across the post-compute
    # substitution pass. must stay in lock-step with
    # generate_site._VER_LITERAL_RE_LEGACY / _QUERY.
    ver_re_legacy = re.compile(rb"(/fonts-full)\.\d{4}-\d{2}-\d{2}\.[a-f0-9]{8}(\.css)")
    ver_re_query = re.compile(rb"(/fonts-full\.css)\?v=\d{4}-\d{2}-\d{2}\.[a-f0-9]{8}")
    # also normalise the I18N_VTAG literal in app.js — it embeds the
    # asset_version itself, causing the hash to oscillate without this.
    i18n_vtag_re = re.compile(rb"var I18N_VTAG\s*=\s*'\d{4}-\d{2}-\d{2}\.[a-f0-9]{8}';?")
    h = hashlib.sha256()
    for rel in bundle:
        p = repo.root / "public" / rel
        if not p.is_file():
            return None
        data = ver_re_legacy.sub(rb"\1\2", p.read_bytes())
        data = ver_re_query.sub(rb"\1", data)
        data = i18n_vtag_re.sub(b"var I18N_VTAG = '';", data)
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(hashlib.sha256(data).digest())
    return f"{edition}.{h.hexdigest()[:8]}"


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    av: str = ""
    sm_missing: bool = False
    no_av: bool = False

    @property
    def ok(self) -> bool:
        return not (self.fails or self.sm_missing or self.no_av)


def evaluate(repo: Repo, recomputed: str | None) -> Result:
    if not repo.is_file(SITE_METADATA_REL):
        return Result(sm_missing=True)
    av = json.loads(repo.read(SITE_METADATA_REL)).get("asset_version", "")
    if not av:
        return Result(no_av=True)

    r = Result(av=av)

    # bundle-hash recomputation (injected).
    if recomputed is None:
        r.fails.append(
            "site-metadata.json: cannot recompute asset_version (generate_site.py "
            "or one of ASSET_BUNDLE missing)"
        )
    elif recomputed != av:
        r.fails.append(
            f"site-metadata.json: asset_version {av} does not match disk-derived "
            f"{recomputed} — rerun generate_site.py so cache busts"
        )

    # sw.js cache name.
    if repo.is_file(SW_REL) and av not in repo.read(SW_REL):
        r.fails.append(f"sw.js: cache name does not contain asset_version {av}")

    # active HTML: every reference to a swept asset must carry ?v={av}.
    for rel in active_html_for_av():
        if not repo.is_file(f"public/{rel}"):
            r.fails.append(f"{rel}: missing active HTML")
            continue
        text = repo.read(f"public/{rel}")
        for asset in SWEPT_ASSETS:
            pat = re.compile(r'(?:href|src)="' + re.escape(asset) + r'(\?v=([^"]*))?"')
            for m in pat.finditer(text):
                qv = m.group(2)
                if qv is None:
                    r.fails.append(f"{rel}: reference to {asset} missing ?v=")
                elif qv != av:
                    r.fails.append(f"{rel}: reference to {asset} has ?v={qv} (expected {av})")
    return r


def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    r = evaluate(repo, recompute_asset_version(repo))
    if r.sm_missing:
        print("  FAIL: site-metadata.json missing")
        return 1
    if r.no_av:
        print("  FAIL: site-metadata.json has no asset_version")
        return 1
    if r.fails:
        print(f"  FAIL: {len(r.fails)} asset-version coherence issue(s) (canonical {r.av}):")
        for f in r.fails[:50]:
            print(f"    {f}")
        if len(r.fails) > 50:
            print(f"    … and {len(r.fails) - 50} more")
        return 1
    print(f"  OK: asset_version {r.av} consistent (HTML + sw.js + on-disk bundle)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
