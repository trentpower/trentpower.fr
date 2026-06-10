#!/usr/bin/env python3
"""generate_release_record.py — per-edition release-record page.

Writes public/integrity/releases/<edition>/index.html: a static,
language-neutral page that lists the signed archive files for the
current edition. Runs after build_release_archives.py so every
linked artefact already exists on disk.

The page is language-neutral by design — release archives are
language-neutral artefacts. English chrome, no runtime i18n, no
JavaScript. Output is deterministic (edition string + fixed file
list, no timestamps), so re-running the build is byte-stable and the
frozen-archive immutability gate stays satisfied once the edition
directory is sealed.
"""

import json
import sys

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
from paths import IDENTITY_CANONICAL, PUBLIC_DIR  # noqa: E402

# (filename template, label, description, ruled-divider)
_FILES = [
    ("SHA256SUMS", "Checksum list", "SHA-256 list for release archives", True),
    (
        "SHA256SUMS.sig",
        "Checksum list signature",
        'Detached <abbr title="Pretty Good Privacy">PGP</abbr> signature over SHA256SUMS',
        False,
    ),
    ("trentpower-fr-{ed}.zip", "ZIP", "Portable public source snapshot", True),
    ("trentpower-fr-{ed}.zip.sha256", "ZIP checksum", "SHA-256 checksum", False),
    (
        "trentpower-fr-{ed}.zip.sig",
        "ZIP signature",
        'Detached <abbr title="Pretty Good Privacy">PGP</abbr> signature',
        False,
    ),
    ("trentpower-fr-{ed}.tar.gz", "TAR.GZ", "Technical preservation archive", True),
    ("trentpower-fr-{ed}.tar.gz.sha256", "TAR.GZ checksum", "SHA-256 checksum", False),
    (
        "trentpower-fr-{ed}.tar.gz.sig",
        "TAR.GZ signature",
        'Detached <abbr title="Pretty Good Privacy">PGP</abbr> signature',
        False,
    ),
    (
        "TESTRESULTS.txt",
        "Test results",
        'Signed test and verification snapshot for this edition. Rendered at <a href="/tests/">/tests/</a>.',
        True,
    ),
    (
        "TESTRESULTS.txt.sig",
        "Test results signature",
        'Detached <abbr title="Pretty Good Privacy">PGP</abbr> signature over TESTRESULTS.txt',
        False,
    ),
]


def _render(ed: str) -> str:
    human = human_date(ed)
    rows = []
    for fname, label, desc, ruled in _FILES:
        fn = fname.format(ed=ed)
        cls = "integrity-rg integrity-rg--ruled" if ruled else "integrity-rg"
        rows.append(
            f'          <div class="{cls}">\n'
            f'            <dt class="integrity-rg-label">{label}</dt>\n'
            f'            <dd class="integrity-rg-value">\n'
            f'              <a class="integrity-rg-link" '
            f'href="/integrity/releases/{ed}/{fn}">{fn}</a>\n'
            f"            </dd>\n"
            f'            <dd class="integrity-rg-desc">{desc}</dd>\n'
            f"          </div>"
        )
    rows_html = "\n".join(rows)
    return f"""<!doctype html>
<!--
  trentpower.fr
  Release artefacts · {ed}
  Public site snapshot, signed and checksummed
-->
<html lang="en" dir="ltr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="color-scheme" content="light">
  <meta name="theme-color" content="#E9E5DC">

  <title>Release · {human} · Trent Power</title>
  <meta name="description" content="Signed downloadable release archives for trentpower.fr — {human} edition.">
  <meta name="robots" content="noindex">
  <link rel="canonical" href="https://trentpower.fr/integrity/releases/{ed}/">

  <link rel="icon" href="/favicon.ico" sizes="any">
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">

  <link rel="preload" as="font" type="font/woff2" href="/fonts/soehne-buch.woff2" crossorigin>
  <link rel="preload" as="font" type="font/woff2" href="/fonts/signifier-regular.woff2" crossorigin>
  <link rel="stylesheet" href="/styles.css">
  <link rel="stylesheet" href="/print.css" media="print">
</head>
<body data-page="release-archive-{ed}" data-layout="masthead" data-surface="record" data-masthead="brand-only" data-edition="{ed}">

<a href="#main" class="skip-link">Skip to content</a>

<header class="site-header" data-component="site-header">
  <div class="nav">
    <div class="nav-inner">
      <a class="nav-mark u-author" href="/" aria-label="Trent Power home"><span>Trent</span> <span>Power</span></a>
    </div>
  </div>
</header>

<main class="site" id="main" tabindex="-1">
  <div class="page">
    <h1 class="page-title">{human}</h1>
    <div class="page-body">
      <p class="page-lede">Signed release archives for the {human} edition. A signed checksum list verifies the archive set; checksums verify the downloaded files; detached signatures verify each archive directly. The signed manifest at /integrity.json remains the live-site authority.</p>

      <p class="integrity-page-level-note">Frozen snapshot. This edition is kept as published and is not re-rendered when the live site changes.</p>

      <section class="integrity-record-card" aria-labelledby="release-archive-title">
        <p class="integrity-record-kicker">Release files</p>
        <h2 class="integrity-record-title" id="release-archive-title">{human}</h2>
        <p class="integrity-record-status">ZIP · TAR.GZ · Checksums · Signatures · Test results</p>

        <dl class="integrity-record-dl">
{rows_html}
        </dl>
      </section>

      <p class="integrity-page-level-note">Archive binaries are not included in /integrity.json to avoid recursive hashing. They are verified separately through the signed checksum list, individual SHA-256 checksums and detached signatures. <a href="/en-au/integrity/">Integrity</a> remains the live-site authority.</p>

    </div>
  </div>
</main>

<footer class="site-footer" aria-label="Site footer">
  <div class="site-footer__inner">
    <div class="site-footer__top">
      <p class="site-footer__identity">
        <span class="year">&copy; <time datetime="2026">2026</time></span>
        <a class="wm" href="/" rel="home"><bdi>Trent Power</bdi></a>
      </p>
    </div>
  </div>
</footer>

</body>
</html>
"""


def main() -> int:
    ed = json.loads(IDENTITY_CANONICAL.read_text(encoding="utf-8"))["edition"]
    out_dir = PUBLIC_DIR / "integrity" / "releases" / ed
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(_render(ed), encoding="utf-8")
    print(f"OK: release-record page → integrity/releases/{ed}/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
