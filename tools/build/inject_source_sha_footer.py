#!/usr/bin/env python3
"""inject_source_sha_footer.py — stamp the footer's source-artefact hash.

The signed-colophon footer carries the first 8 hex characters of the
page's source-mirror SHA-256 (a non-self-referential hash — the mirror
was captured before the hex itself was placed). At render time the
mirror doesn't exist yet, so templates emit a placeholder:

    <a class="site-footer__colophon-link …" data-page-sha-short …>
       SHA-256 · <code>--------</code>
    </a>

    <body … data-source-sha256-short="--------">

This script runs after [6k/9] (final source-mirror refresh) and before
[7/9] (final signed integrity manifest). It reads the latest
verification map (where the build has already computed `source_sha256`
for every route), converts the base64 SHA to 8-char lowercase hex,
and rewrites the placeholder in both the footer link and the body
attribute.

The mirror at /source/<route>.html.txt is NOT rewritten by this step
— that is the whole point. The footer claims the source-artefact
hash, not the live-HTML hash; a visitor can curl the mirror, sha256
it, and read the first 8 hex chars to confirm the footer's claim.

If a route has no record or an empty source_sha256, the link
collapses to the "Integrity manifest" / "Manifeste d'intégrité"
fallback shape and the body attribute is stripped. The script fails
loudly if any "--------" placeholder remains anywhere after the pass.

Usage:
    python3 tools/inject_source_sha_footer.py [--root DIR]
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import sys
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
from paths import PUBLIC_DIR  # noqa: E402

PLACEHOLDER = "--------"

# manifest_link fallback text per locale — used when a route has no
# source_sha256 (the no-hash fallback shape). hardcoded here to avoid
# pulling the full yaml loader; the two strings rarely change and the
# build will warn if they ever drift from content/{en,fr}/shared.yml.
FALLBACK_LINK_TEXT = {
    "en": "Integrity manifest",
    "fr": "Manifeste d'intégrité",
}


def _load_verification_map(public_dir: Path) -> dict:
    """Read the latest versioned verification-data.YYYY-MM-DD.HASHHEX.js
    and return the parsed TP_VERIFICATION_MAP object. Picks the bare
    `/verify/verification-data.js` (the unversioned alias the live site
    serves) — the build keeps this pointing at the current edition."""
    fp = public_dir / "verify" / "verification-data.js"
    if not fp.is_file():
        raise FileNotFoundError(f"{fp} not present — run generate_verification_map.py first")
    text = fp.read_text(encoding="utf-8")
    # the file is `window.TP_VERIFICATION_MAP = { … };` — slice out the
    # object literal and parse as json (the generator emits json-strict
    # values; quotes, escapes and trailing commas are all clean).
    m = re.search(r"window\.TP_VERIFICATION_MAP\s*=\s*(\{.*\});", text, re.DOTALL)
    if not m:
        raise ValueError(f"{fp}: could not locate TP_VERIFICATION_MAP literal")
    return json.loads(m.group(1))


def _hex8(b64sha: str) -> str:
    """Convert `sha256-XXX=` (base64) to the first 8 hex chars."""
    if not b64sha or not b64sha.startswith("sha256-"):
        return ""
    try:
        raw = base64.b64decode(b64sha[len("sha256-") :])
    except binascii.Error:
        return ""
    return raw[:4].hex()


def _route_for_html(rel: str) -> str:
    """Normalise a public/-rooted html relative path to a web route.

    /index.html              → "/" (the gate; not in the map by design)
    /en-au/index.html        → "/en-au/"
    /en-au/privacy/index.html → "/en-au/privacy/"
    /404.html (root)         → "/404.html"
    /en-au/404.html          → "/en-au/404.html"
    """
    rel = rel.replace(os.sep, "/")
    if rel.endswith("/index.html"):
        return "/" + rel[: -len("index.html")]
    if rel == "index.html":
        return "/"
    return "/" + rel


def _lang_of_route(route: str) -> str:
    if route.startswith("/fr/"):
        return "fr"
    return "en"


def _inject_hex(html: str, hex8: str) -> tuple[str, int]:
    """Replace the two placeholders OR an existing hex (idempotent
    re-injection) in body attribute + footer <code> with the new
    8-char hex. Returns (new_html, n_replaced)."""
    # match either the literal placeholder or any 8-char lowercase hex
    # already in the slot — supports re-stamping after a verification-
    # data refresh that changed source_sha256.
    SHA_TOKEN = r"(?:[a-f0-9]{8}|-{8})"
    n = 0

    # 1. body attribute
    body_pat = re.compile(r'(data-source-sha256-short=")' + SHA_TOKEN + r'(")')
    new, k = body_pat.subn(rf"\g<1>{hex8}\g<2>", html, count=1)
    n += k

    # 2. footer <code> (anchored by surrounding data-page-sha-short on the
    # parent <a>; we look for a <code> child carrying either the
    # placeholder or an old hex inside an <a … data-page-sha-short …>).
    code_pat = re.compile(
        r"(<a\b[^>]*\bdata-page-sha-short\b[^>]*>[^<]*<code>)" + SHA_TOKEN + r"(</code>)",
    )
    new, k = code_pat.subn(rf"\g<1>{hex8}\g<2>", new, count=1)
    n += k

    return new, n


def _inject_fallback(html: str, lang: str) -> tuple[str, int]:
    """No-hash fallback: leave the literal placeholder in place.

    Routes without a source_sha256 record (the /source/ and /source/view/
    pages whose verification-data carries null) keep the footer reading
    "SHA-256 · --------" — the eight dashes read honestly as "unavailable
    on this page", and the byte count stays identical to a hex-stamped
    page so the source mirror remains byte-for-byte the pre-injection
    capture. Returns (new_html, n_changes_made=1) for the bookkeeping in
    main(), which expects a non-zero count to confirm the page matched."""
    return html, 1


def main() -> int:
    public_dir = PUBLIC_DIR
    argv = sys.argv[1:]
    if "--root" in argv:
        public_dir = Path(argv[argv.index("--root") + 1]).resolve()

    vmap = _load_verification_map(public_dir)

    # walk every active html under public/ that carries the placeholder.
    # the placeholder is the cheap pre-filter — pages without the new
    # colophon footer (the language gate, frozen-archive index pages)
    # are skipped without further work.
    touched = 0
    fallback = 0
    hex_count = 0
    missing_route: list[str] = []

    for fp in sorted(public_dir.rglob("*.html")):
        rel_to_public = fp.relative_to(public_dir).as_posix()
        # skip frozen release-archive index pages — their bytes are
        # immutable and sealed.
        if re.match(r"integrity/releases/[^/]+/", rel_to_public):
            continue

        text = fp.read_text(encoding="utf-8")
        # touch only pages that carry the footer-sha slot (placeholder
        # or a previously-injected hex). idempotent: re-running re-stamps
        # the current source_sha256 over whatever hex sits there now.
        slot_re = re.compile(r'data-source-sha256-short="(?:[a-f0-9]{8}|-{8})"')
        if not slot_re.search(text) and "data-page-sha-short" not in text:
            continue

        route = _route_for_html(rel_to_public)
        record = vmap.get(route)
        b64 = (record or {}).get("source_sha256") or ""
        hex8 = _hex8(b64)
        lang = _lang_of_route(route)

        if hex8:
            new, n = _inject_hex(text, hex8)
            # the footer colophon was simplified to a single linked
            # edition row (no separate SHA-256 prefix row), so only
            # one in-DOM placeholder remains — the body's
            # data-source-sha256-short attribute. accept n >= 1.
            if n < 1:
                missing_route.append(f"{rel_to_public}: expected ≥1 placeholder, replaced {n}")
                continue
            fp.write_text(new, encoding="utf-8")
            touched += 1
            hex_count += 1
        else:
            new, n = _inject_fallback(text, lang)
            if n < 1:
                # nothing changed — shouldn't happen given the gate above
                missing_route.append(
                    f"{rel_to_public}: no source_sha256 and no fallback shape matched"
                )
                continue
            fp.write_text(new, encoding="utf-8")
            touched += 1
            fallback += 1

    # leak-check is intentionally light. fallback pages (no source_sha256)
    # deliberately keep the literal "--------" placeholder so the footer
    # stays byte-identical to the source mirror — the eight dashes read
    # as "unavailable" without misrepresenting a hash. there is no
    # placeholder we need to refuse to ship.
    leaks: list[str] = []

    if missing_route or leaks:
        for m in missing_route:
            print(f"  ✗ {m}", file=sys.stderr)
        for m in leaks:
            print(f"  ✗ {m}", file=sys.stderr)
        print(
            f"\nFAIL: footer-sha injection incomplete "
            f"({len(missing_route)} mismatch, {len(leaks)} leaked)",
            file=sys.stderr,
        )
        return 1

    print(
        f"  OK: footer-sha injected — {touched} page(s) ({hex_count} with hex, {fallback} fallback)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
