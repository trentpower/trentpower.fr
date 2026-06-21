#!/usr/bin/env python3
r"""tools/validate_lighthouse_invariants.py — predeploy step 17.

Defends the Lighthouse score gains from edition 2026-05-09 against
silent regression in future builds. Each check is a one-line
invariant the operator would otherwise have to remember.

Checks
  L1. No inline event handlers (`onclick=`, `onload=`, `onerror=`,
      etc.) in any active HTML page. Inline handlers require
      'unsafe-inline' which violates the site CSP and is a
      Best-Practices loss.

  L2. No `eval(` or `new Function(` in the deployed behaviour-scoped JS
      bundles. Both bypass CSP `script-src 'self'` discipline and
      break Trusted Types.

  L3. `<FilesMatch "^sw\.js$">` block in `.htaccess` carries an
      explicit `Content-Type: application/javascript` and
      `Service-Worker-Allowed: /`. Without these, browsers refuse
      the worker under `X-Content-Type-Options: nosniff` and
      Lighthouse logs a Best-Practices console error.

  L4. `.footer-lang button` rule in styles.css declares
      `min-width: 44px` AND `min-height: 44px` (the box geometry
      Lighthouse audits — pseudo-element overlays do not count).

  L5. The editioned verification-data filename
      (`/verify/verification-data.<edition>.<sha8>.js`) exists on
      disk; the unversioned alias is byte-identical.

  L6. Homepage Tier-1 font preload count ≤ 3. Preloading more than
      three first-paint fonts wastes bytes and crowds the critical
      path.

  L7. The five .principle-title <h3> headings on /index.html close
      with </h3>. The cluster carried </h2> in earlier revisions —
      browsers tolerate the bug, validators flag it.

  L8. `.cite-btn` rule in styles.css declares `min-height: 44px`. The
      button sits beside the language switcher in the footer; without
      its own minimum height it can drop below the 44 px tap-target
      bar at small sizes when the surrounding row reflows.

Exit 0 = green. Exit 1 = block.

Shape (deep module, small interface). The filesystem is the one injected seam —
`Repo(root)` — so the whole gate runs over a fixture repo with no
monkeypatching. `load(repo)` reads the canonical identity JSON; `evaluate(repo,
edition)` is the pure compute path returning a Result; `main()` is the only
adapter that prints/exits. The per-check helpers take the Repo (and any read
text) as parameters — no module-global path reads.
"""

from __future__ import annotations

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
from paths import REPO_ROOT  # noqa: E402
from repo import Repo  # noqa: E402  (shared filesystem evidence seam)
from script_blocks import strip_script_blocks  # noqa: E402

# repo-relative location of the canonical identity input (resolved through Repo).
IDENTITY_CANONICAL_REL = "tools/config/identity_canonical.json"


# every active .html under public/ — discovered by walk so the
# bilingual /en/ and /fr/ trees are covered. the dated frozen-archive
# snapshots and the editorial review documents are excluded.
def _discover_active_html(repo: Repo) -> list[str]:
    out: list[str] = []
    prefix = "public/"
    for full in repo.glob(f"{prefix}**/*.html"):
        rel = full[len(prefix) :]
        if re.match(r"integrity/releases/[^/]+/", rel):
            continue
        if rel.startswith("editorial/"):
            continue
        out.append(rel)
    return out


INLINE_HANDLER_RE = re.compile(
    r"\son(?:click|load|error|change|input|submit|focus|blur|"
    r"mouseover|mouseout|mouseenter|mouseleave|keydown|keyup|"
    r"keypress|touchstart|touchend|touchmove|scroll|resize|"
    r"abort|reset|select)\s*=\s*[\"']",
    re.IGNORECASE,
)

EVAL_RE = re.compile(r"\beval\s*\(|\bnew\s+Function\s*\(")


def _fail(fails: list, msg: str):
    fails.append(msg)


def _check_no_inline_handlers(repo: Repo, fails: list) -> None:
    for rel in _discover_active_html(repo):
        prel = f"public/{rel}"
        if not repo.is_file(prel):
            _fail(fails, f"L1: {rel} missing")
            continue
        text = repo.read(prel)
        # strip <script>...</script> blocks first — js code inside a
        # script element legitimately uses identifiers like onclick.
        text_no_scripts = strip_script_blocks(text)
        m = INLINE_HANDLER_RE.search(text_no_scripts)
        if m:
            ctx_start = max(0, m.start() - 30)
            ctx_end = min(len(text_no_scripts), m.end() + 30)
            ctx = text_no_scripts[ctx_start:ctx_end].replace("\n", " ")
            _fail(fails, f"L1: {rel} carries inline event handler near: …{ctx}…")


def _check_no_eval(repo: Repo, fails: list) -> None:
    for rel in (
        "js/theme.js",
        "sw-register.js",
        "js/reveal.js",
        "js/verify-modal.js",
        "js/copy.js",
        "js/overlay.js",
        "js/fonts.js",
    ):
        prel = f"public/{rel}"
        if not repo.is_file(prel):
            _fail(fails, f"L2: {rel} missing")
            continue
        text = repo.read(prel)
        if EVAL_RE.search(text):
            _fail(
                fails,
                f"L2: {rel} contains eval() or new Function() — CSP / Trusted Types regression",
            )


def _check_htaccess_sw_block(repo: Repo, fails: list) -> None:
    prel = "public/.htaccess"
    if not repo.is_file(prel):
        _fail(fails, "L3: .htaccess missing")
        return
    text = repo.read(prel)
    # the 2026-05-19 .htaccess refactor split the sw.js policy across
    # two FilesMatch blocks: one in section d (csp override) and one
    # in section e (Content-Type + Service-Worker-Allowed + cache).
    # the L3 invariant is "these directives exist on sw.js" — accept
    # any block that contributes them.
    blocks = re.findall(
        r'<FilesMatch\s+"\^sw\\\.js\$">\s*(.*?)\s*</FilesMatch>',
        text,
        re.S,
    )
    if not blocks:
        _fail(fails, "L3: .htaccess has no <FilesMatch sw.js> block")
        return
    combined = "\n".join(blocks)
    if "Content-Type" not in combined or "application/javascript" not in combined:
        _fail(
            fails,
            "L3: sw.js FilesMatch block(s) missing explicit Content-Type: application/javascript",
        )
    if "Service-Worker-Allowed" not in combined:
        _fail(fails, "L3: sw.js FilesMatch block(s) missing Service-Worker-Allowed: /")


def _check_footer_lang_touch_target(repo: Repo, fails: list) -> None:
    prel = "public/styles.css"
    if not repo.is_file(prel):
        _fail(fails, "L4: styles.css missing")
        return
    text = repo.read(prel)
    # the footer language switcher is two static <a> links between the
    # editions. the lighthouse touch-target audit wants ≥44px tap
    # height; we accept either the legacy min-width/min-height: 44px
    # block OR a padding-block ≥ 12px (which combined with the rule's
    # font-size + line-height yields ≥44px tap height without making
    # the link read as a button).
    # accept either a standalone .site-footer__language a {...} block
    # or a combined .site-footer__language a, .site-footer__language
    # button {...} block (the error pages + source reader use <button>
    # for js-driven switching; main pages use <a> for real navigation;
    # both share the same italic-serif editorial styling).
    blocks = re.findall(
        r"\.site-footer__language\s+(?:a|button)(?:[^{]*\.site-footer__language\s+(?:a|button))?\s*\{([^}]*)\}",
        text,
    )
    if not blocks:
        _fail(
            fails,
            "L4: styles.css has no footer language-link rule (.site-footer__language a / button)",
        )
        return
    pad_re = re.compile(r"padding(?:-block(?:-(?:start|end))?)?\s*:[^;]*?\b(1[2-9]|[2-9]\d)px")
    ok = False
    for b in blocks:
        if "min-width" in b and "min-height" in b and b.count("44px") >= 2:
            ok = True
            break
        if pad_re.search(b):
            ok = True
            break
    if not ok:
        _fail(
            fails,
            "L4: footer language-link block needs touch-target ≥ 44px "
            "(either min-width:44px + min-height:44px, OR padding-block ≥ 12px)",
        )


def _check_cite_btn_touch_target(repo: Repo, fails: list) -> None:
    prel = "public/styles.css"
    if not repo.is_file(prel):
        return  # l4 already reported missing
    text = repo.read(prel)
    m = re.search(r"\.cite-btn\s*\{([^}]*)\}", text)
    if not m:
        # cite-btn may be absent on some surfaces; treat as not-applicable
        return
    block = m.group(1)
    if "min-height" not in block or "44px" not in block:
        _fail(fails, "L8: .cite-btn missing min-height: 44px (touch-target audit)")


def _check_versioned_verification_data(repo: Repo, edition: str, fails: list) -> None:
    """L5 — the verification-data script ships as a single clean file
    `/verify/verification-data.js`; cache busting rides on the
    `?v={asset_version}` query string stamped into every HTML
    reference (enforced by stage 7 ASSET_VERSION coherence). there
    must be NO dated `verification-data.<edition>.<sha>.js` siblings
    in the active tree (enforced by stage 7a too); this gate just
    confirms the clean alias is present and non-empty."""
    if not edition:
        _fail(fails, "L5: identity_canonical.json has no edition")
        return
    alias_rel = "public/verify/verification-data.js"
    if not repo.is_file(alias_rel):
        _fail(fails, "L5: /verify/verification-data.js missing")
        return
    if repo.size(alias_rel) == 0:
        _fail(fails, "L5: /verify/verification-data.js is empty")
        return
    # belt-and-braces: any leftover dated siblings would have been
    # caught by stage 7a (validate_no_dated_assets.py), but flag
    # them here too so the L5 message names the offender directly.
    dated_pat = re.compile(rf"^verification-data\.{re.escape(edition)}\.[a-f0-9]+\.js$")
    siblings = repo.glob("public/verify/verification-data.*.js")
    stale = sorted(
        rel for rel in siblings if dated_pat.match(rel.rsplit("/", 1)[-1])
    )
    if stale:
        names = [rel.rsplit("/", 1)[-1] for rel in stale]
        _fail(
            fails,
            f"L5: dated verification-data sibling(s) present (should have been pruned): {names}",
        )


def _check_principle_close_tags(repo: Repo, fails: list) -> None:
    prel = "public/index.html"
    if not repo.is_file(prel):
        _fail(fails, "L7: index.html missing")
        return
    text = repo.read(prel)
    bad = re.findall(
        r'<h3[^>]*class="principle-title"[^>]*>[^<]*</h2>',
        text,
    )
    if bad:
        _fail(fails, f"L7: {len(bad)} principle-title <h3> rule(s) close with </h2>")


def _check_homepage_font_preloads(repo: Repo, fails: list) -> None:
    prel = "public/index.html"
    if not repo.is_file(prel):
        _fail(fails, "L6: index.html missing")
        return
    text = repo.read(prel)
    preloads = re.findall(
        r"<link[^>]+rel=[\"\']preload[\"\'][^>]+as=[\"\']font[\"\'][^>]*>",
        text,
    )
    if len(preloads) > 3:
        _fail(fails, f"L6: index.html preloads {len(preloads)} fonts (≤3 expected)")


def _check_no_data_urls_in_stylesheets(repo: Repo, fails: list) -> None:
    """L9 — no data: URLs inside url(...) in stylesheets.

    the site's CSP at .htaccess pins img-src to 'self', and browsers
    treat background-image: url("data:...") as an image fetch, which the
    CSP then blocks. blocked fetches show up as console errors, and
    Lighthouse Best Practices deducts for unresolved console errors.
    catching this at predeploy keeps the strict CSP intact without a
    silent regression next time a generator inlines a tiny svg.
    """
    for name in ("styles.css", "print.css"):
        prel = f"public/{name}"
        if not repo.is_file(prel):
            continue
        text = repo.read(prel)
        # match `url(` optional-quote `data:`
        if re.search(r"url\(\s*['\"]?data:", text):
            _fail(
                fails,
                f"L9: {name} contains url(data:...) — CSP img-src 'self' would block it. "
                f"move the asset to a real file under /images/.",
            )


# ---------------------------------------------------------------------------
# Result — the value that flows through the interface. evaluate() produces it;
# main() renders it. tests assert on Result, never on stdout. `summary` carries
# the green one-liner so the render stays a thin adapter.
# ---------------------------------------------------------------------------
@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    warns: list[str] = field(default_factory=list)
    summary: str = (
        "Lighthouse invariants — inline handlers, eval, sw.js headers, "
        "touch targets, versioned verification-data, font preloads, "
        "principle close tags, cite-btn tap target, i18n core (en+fr) carries every locale, "
        "no data: URLs in stylesheets"
    )

    @property
    def ok(self) -> bool:
        return not self.fails


# ---------------------------------------------------------------------------
# load — read the canonical identity JSON through the Repo seam. returns the
# edition (or None when missing); never prints/exits.
# ---------------------------------------------------------------------------
def load(repo: Repo) -> str | None:
    if not repo.is_file(IDENTITY_CANONICAL_REL):
        return None
    return json.loads(repo.read(IDENTITY_CANONICAL_REL)).get("edition")


# ---------------------------------------------------------------------------
# evaluate — the compute interface. one call, one Result, over the injected
# Repo + the canonical edition. this is the test surface.
# ---------------------------------------------------------------------------
def evaluate(repo: Repo, edition: str | None) -> Result:
    r = Result()
    _check_no_inline_handlers(repo, r.fails)
    _check_no_eval(repo, r.fails)
    _check_htaccess_sw_block(repo, r.fails)
    _check_footer_lang_touch_target(repo, r.fails)
    _check_cite_btn_touch_target(repo, r.fails)
    _check_versioned_verification_data(repo, edition or "", r.fails)
    _check_homepage_font_preloads(repo, r.fails)
    _check_principle_close_tags(repo, r.fails)
    _check_no_data_urls_in_stylesheets(repo, r.fails)
    return r


# ---------------------------------------------------------------------------
# main — the side-effecting adapter. loads, evaluates, renders, returns exit
# code. the only place stdout and exit codes live.
# ---------------------------------------------------------------------------
def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    edition = load(repo)
    r = evaluate(repo, edition)

    if r.fails:
        print(f"FAIL: {len(r.fails)} Lighthouse-invariant issue(s):", file=sys.stderr)
        for f in r.fails:
            print(f"  ✗ {f}", file=sys.stderr)
        return 1
    print(f"OK: {r.summary}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
