#!/usr/bin/env python3
"""generate_documentation.py — public /documentation/ surface.

Publishes the documentation set as a discoverable, verifiable surface:

  public/documentation/index.html   landing page (this generator)
  public/documentation/README.pdf   the signed publication (copied from root)
  public/documentation/README.txt   plain-text README (copied from root README.md)

The PDF is hand-rendered locally by docs/pdf/build.sh (paged.js + Chromium) and
committed; this generator only copies the committed bytes into the public tree
and bakes the PDF's SHA-256 into the landing page so a reader can cross-check it
against the signed integrity.json. No Chromium dependency in the main build.

`.md` is denied site-wide by .htaccess, so the Markdown ships as README.txt (the
same convention the source mirror uses). The landing page is language-neutral
(like /tests/ and /source/) and built from the same native page shell, so it is
hashed, SRI-swept and mirrored like any other public surface.

Runs after generate_site.py (needs site-metadata.json for asset_version) and
before the integrity / SRI / source-mirror stages.
"""

import json
import shutil
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
from dates import human_date  # noqa: E402
from hashing import sri_sha256  # noqa: E402
from paths import IDENTITY_CANONICAL, PUBLIC_DIR  # noqa: E402
from paths import REPO_ROOT as ROOT

FINGERPRINT = "A729 591B 450D 3F59 3694 98BD 8299 1F25 04AE 0263"


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _sha256_sri(path: Path) -> str:
    return sri_sha256(path.read_bytes())


def _render(ed: str, asset_version: str, human: str, pdf_sri: str, pdf_bytes: int) -> str:
    v = f"?v={asset_version}"
    pdf_kb = f"{pdf_bytes / 1024:.0f} kB"
    return f"""<!doctype html>
<!--
  trentpower.fr · /documentation/
  Public documentation surface · edition {ed}
  Links the signed README.pdf and plain-text README, with the PDF's SHA-256 for
  cross-checking against integrity.json. No analytics, no cookies, no external assets.
-->
<html lang="en-AU" dir="ltr">
<head>
  <!-- foundations -->
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="format-detection" content="telephone=no">
  <meta name="color-scheme" content="light dark">
  <meta name="theme-color" content="#E9E5DC">

  <!-- appearance bootstrap (theme; hash authorised in global CSP) -->
  <script>(()=>{{const e=document.documentElement;e.classList.add('js');try{{const m=localStorage.getItem('tp-theme');if(m==='dark'||m==='light')e.dataset.theme=m}}catch(_){{}}}})();</script>

  <!-- document identity -->
  <title>Documentation · Trent Power</title>
  <meta name="description" content="The complete technical documentation for trentpower.fr — architecture, privacy, security and verification — as a signed PDF and plain-text README.">
  <meta name="document-edition" content="{ed}">
  <meta name="robots" content="index, follow">
  <meta name="referrer" content="no-referrer">
  <link rel="canonical" href="https://trentpower.fr/documentation/">

  <!-- authorship + provenance -->
  <meta name="author" content="Trent Power">
  <link rel="author" href="/.well-known/person.json">
  <link rel="license" href="https://creativecommons.org/licenses/by-sa/4.0/">
  <link rel="describedby" href="/integrity.json">

  <!-- application surface -->
  <link rel="icon" href="/favicon.ico" sizes="any">
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png">
  <link rel="manifest" href="/manifest.webmanifest" type="application/manifest+json">

  <!-- rendering + assets -->
  <link rel="preload" as="font" type="font/woff2" href="/fonts/soehne-buch.woff2" crossorigin>
  <link rel="preload" as="font" type="font/woff2" href="/fonts/signifier-regular.woff2" crossorigin>
  <link rel="stylesheet" href="/styles.css{v}">
  <link rel="stylesheet" href="/print.css{v}" media="print">
</head>
<body data-page="documentation" data-layout="masthead" data-surface="record" data-masthead="brand-only" data-edition="{ed}">

<a href="#main" class="skip-link">Skip to content</a>

<!-- masthead -->
<header class="site-header" data-component="site-header">
  <div class="nav">
    <div class="nav-inner">
      <a class="nav-mark u-author" href="/" aria-label="Trent Power home"><span>Trent</span> <span>Power</span></a>
    </div>
  </div>
</header>

<main class="site documentation-page" id="main" tabindex="-1">
  <div class="page">

    <!-- primary · statement -->
    <p class="page-kicker">Public Documentation</p>
    <h1 class="page-title hero-stack">Documentation</h1>
    <div class="page-body">
      <p class="page-lede">The complete technical description of this site — its architecture, content model, build pipeline, security and privacy posture, and verification process — published as a signed PDF and a plain-text README.</p>
      <p>This page is part of the verification chain. The PDF below is hashed in the signed <a href="/integrity.json">integrity manifest</a>, so anyone can confirm the document they downloaded is exactly the one that was published — no need to trust the host or the network.</p>

      <!-- the publication -->
      <section class="security-section" aria-labelledby="doc-pub-h">
        <h2 class="security-section-heading" id="doc-pub-h">The publication</h2>
        <p>One reading of the whole system, written so a non-technical reader and the engineer who maintains it can both follow it. The PDF is the canonical, page-designed edition; the README is the same documentation in plain text.</p>
        <div class="integrity-record-card">
          <p class="integrity-record-kicker">Documentation set</p>
          <h3 class="integrity-record-title">README</h3>
          <dl class="integrity-record-dl">
            <div class="integrity-rg integrity-rg--ruled">
              <dt class="integrity-rg-label">Edition</dt>
              <dd class="integrity-rg-value"><time datetime="{ed}">{ed}</time></dd>
            </div>
            <div class="integrity-rg">
              <dt class="integrity-rg-label">Published</dt>
              <dd class="integrity-rg-value">{_esc(human)}</dd>
            </div>
            <div class="integrity-rg">
              <dt class="integrity-rg-label">PDF</dt>
              <dd class="integrity-rg-value"><a class="integrity-rg-link" href="/documentation/README.pdf">README.pdf</a></dd>
              <dd class="integrity-rg-desc">A4 portrait · {pdf_kb}</dd>
            </div>
            <div class="integrity-rg">
              <dt class="integrity-rg-label">Plain text</dt>
              <dd class="integrity-rg-value"><a class="integrity-rg-link" href="/documentation/README.txt">README.txt</a></dd>
              <dd class="integrity-rg-desc">Markdown source, as text</dd>
            </div>
          </dl>
        </div>
      </section>

      <!-- integrity -->
      <section class="security-section" aria-labelledby="doc-int-h">
        <h2 class="security-section-heading" id="doc-int-h">Integrity</h2>
        <p>The PDF is covered by the same signed manifest as every other published byte. Its fingerprint is recorded in <a href="/integrity.json">integrity.json</a>, which is signed with the published PGP key.</p>
        <div class="integrity-record-card">
          <p class="integrity-record-kicker">Signed artefact</p>
          <h3 class="integrity-record-title">README.pdf</h3>
          <p class="integrity-record-status">SHA-256 recorded in integrity.json · Edition {ed}</p>
          <dl class="integrity-record-dl">
            <div class="integrity-rg integrity-rg--ruled">
              <dt class="integrity-rg-label">SHA-256</dt>
              <dd class="integrity-rg-value">{pdf_sri}</dd>
            </div>
            <div class="integrity-rg">
              <dt class="integrity-rg-label">Manifest</dt>
              <dd class="integrity-rg-value"><a class="integrity-rg-link" href="/integrity.json">integrity.json</a></dd>
              <dd class="integrity-rg-desc">Signed: <a class="integrity-rg-link" href="/integrity.json.sig">integrity.json.sig</a></dd>
            </div>
            <div class="integrity-rg">
              <dt class="integrity-rg-label">Key</dt>
              <dd class="integrity-rg-value"><a class="integrity-rg-link" href="/.well-known/pgp-key.asc">pgp-key.asc</a></dd>
            </div>
            <div class="integrity-rg">
              <dt class="integrity-rg-label">Fingerprint</dt>
              <dd class="integrity-rg-value">{_esc(FINGERPRINT)}</dd>
            </div>
          </dl>
        </div>
        <details class="tests-verify">
          <summary>View verification command</summary>
          <p>Download the PDF, hash it, and confirm the digest appears in the signed manifest.</p>
          <pre class="tests-cmd">curl -O https://trentpower.fr/documentation/README.pdf <span class="tests-cmd__op">&amp;&amp;</span>
openssl dgst -sha256 -binary README.pdf | openssl base64 <span class="tests-cmd__op">&amp;&amp;</span>
curl -s https://trentpower.fr/integrity.json | grep documentation/README.pdf</pre>
        </details>
        <p class="tests-downloads">Read the full <a href="/en-au/verify/">verification record</a>, or browse the <a href="/source/">source mirror</a> and <a href="/integrity/releases/{ed}/">release archive</a>.</p>
      </section>

    </div>
  </div>
</main>

<!-- body · footer -->
<footer class="site-footer" aria-label="Site footer">
  <div class="site-footer__inner">

    <!-- top stratum · identity · nav · language -->
    <div class="site-footer__top">

      <p class="site-footer__identity">
        <span class="year">&copy; <span class="since">1997 &ndash;</span> <time datetime="2026">2026</time></span>
        <a class="wm" href="/en-au/" rel="home" aria-describedby="desc-home-footer"><bdi>Trent Power</bdi></a>
        <span class="visually-hidden" id="desc-home-footer">Return to the homepage</span>
      </p>

      <nav class="site-footer__nav" aria-label="Footer">
        <span>Paris, France</span>
        <span class="sep" aria-hidden="true">&middot;</span>
        <a class="site-footer__action" href="/en-au/privacy/" rel="privacy-policy" aria-describedby="desc-privacy">Privacy</a>
        <span class="visually-hidden" id="desc-privacy">Read how this site avoids analytics, cookies, profiling, tracking, and third-party assets</span>
        <span class="sep" aria-hidden="true">&middot;</span>
        <button type="button" class="site-footer__action"
                data-cite-open aria-haspopup="dialog"
                aria-describedby="desc-cite">Verify</button>
        <span class="visually-hidden" id="desc-cite">Open citation and verification details for this page</span>
      </nav>

      <ul class="site-footer__language" aria-label="Language">
        <li><a href="/en-au/"  aria-describedby="desc-lang-en" lang="en" aria-current="page">English</a> <span class="visually-hidden" id="desc-lang-en">Read this site in English</span></li>
        <li aria-hidden="true"><span class="sep">&middot;</span></li>
        <li><a href="/fr/" aria-describedby="desc-lang-fr" lang="fr">Français</a> <span class="visually-hidden" id="desc-lang-fr">Lire ce site en français</span></li>
      </ul>

    </div>

    <hr class="site-footer__break tp-rule" aria-hidden="true">

    <!-- bottom stratum · colophon · theme -->
    <div class="site-footer__bottom">

      <ul class="site-footer__colophon" id="footerImprint" aria-label="Publication verification">
        <li class="site-footer__colophon-row">
          <a class="site-footer__colophon-link" href="/en-au/verify/" aria-describedby="desc-integrity"><span class="site-footer__colophon-key">Edition</span> <time datetime="{ed}">{ed}</time></a>
          <span class="site-footer__colophon-sep" aria-hidden="true">·</span>
          <span class="site-footer__colophon-note" data-edition-age>Published today</span>
          <span class="visually-hidden" id="desc-integrity">Open the verification record for this edition — citation, source mirror, fingerprint, signed release</span>
        </li>
      </ul>

      <ul class="site-footer__theme" aria-label="Appearance">
        <li><button type="button" data-theme="light"  aria-pressed="false" aria-describedby="desc-theme-light">Light</button> <span class="visually-hidden" id="desc-theme-light">Switch to the light appearance</span></li>
        <li aria-hidden="true"><span class="sep">&middot;</span></li>
        <li><button type="button" data-theme="system" aria-pressed="true"  aria-describedby="desc-theme-auto">Auto</button> <span class="visually-hidden" id="desc-theme-auto">Match the system appearance setting</span></li>
        <li aria-hidden="true"><span class="sep">&middot;</span></li>
        <li><button type="button" data-theme="dark"   aria-pressed="false" aria-describedby="desc-theme-dark">Dark</button> <span class="visually-hidden" id="desc-theme-dark">Switch to the dark appearance</span></li>
      </ul>

    </div>

  </div>
</footer>

<!-- scripts · progressive enhancement, no telemetry -->
<script src="/js/theme.js{v}" defer></script>
<script src="/sw-register.js{v}" defer></script>
<script src="/js/reveal.js{v}" defer></script>
<script src="/js/overlay.js{v}" defer></script>
<script src="/verify/verification-data.js{v}" defer></script>
<script src="/js/copy.js{v}" defer></script>
<script src="/js/edition.js{v}" defer></script>
<script src="/js/micro-interactions.js" defer></script>
<script src="/js/verify-modal.js{v}" defer></script>
<script src="/js/fonts.js{v}" defer></script>
</body>
</html>
"""


def main() -> int:
    ed = json.loads(IDENTITY_CANONICAL.read_text(encoding="utf-8"))["edition"]
    root_pdf = ROOT / "README.pdf"
    root_md = ROOT / "README.md"
    if not root_pdf.is_file():
        raise SystemExit(
            "generate_documentation: README.pdf not found at repo root — "
            "run `bash docs/pdf/build.sh` first to render + validate it."
        )
    if not root_md.is_file():
        raise SystemExit("generate_documentation: README.md not found at repo root.")

    meta = json.loads((PUBLIC_DIR / "site-metadata.json").read_text(encoding="utf-8"))
    asset_version = meta.get("asset_version", ed)

    out_dir = PUBLIC_DIR / "documentation"
    out_dir.mkdir(parents=True, exist_ok=True)

    # copy the committed artefacts into the public surface.
    shutil.copyfile(root_pdf, out_dir / "README.pdf")
    shutil.copyfile(root_md, out_dir / "README.txt")

    pdf_sri = _sha256_sri(out_dir / "README.pdf")
    pdf_bytes = (out_dir / "README.pdf").stat().st_size
    human = human_date(ed)

    (out_dir / "index.html").write_text(
        _render(ed, asset_version, human, pdf_sri, pdf_bytes), encoding="utf-8"
    )
    print(
        f"OK: documentation surface → documentation/ "
        f"(index.html + README.pdf + README.txt, edition {ed})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
