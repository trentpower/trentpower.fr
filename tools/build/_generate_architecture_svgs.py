#!/usr/bin/env python3
"""
Generate localised architecture SVGs for trentpower.fr.

Outputs:
  /images/architecture/architecture.svg         (English default — for no-JS users)
  /images/architecture/architecture.{lang}.svg  (en/fr)
  /images/architecture/architecture-mobile.svg
  /images/architecture/architecture-mobile.{lang}.svg

Brief — 30 April 2026 final close-out:
  - Eyebrow line "trentpower.fr · architecture" removed
  - Red horizontal Trust line removed (the small oxblood dot beside
    integrity.json is the only proof accent retained)
  - "Apache · Gandi" → "Apache · Gandi, Paris"
  - Layer titles in Title Case in source (rendered uppercase + tracked
    via CSS text-transform — they read as small caps regardless)
  - Technical literals preserved (HTTPS, TLS, HSTS, COOP, COEP, CORP,
    CSP, SHA-256, PGP, woff2, etc.)
"""

import os

LANGS = ["en", "fr"]

# ─── Per-language label dictionary ──────────────────────────────────
L = {
    "en": {
        "title": "trentpower.fr architecture",
        "desc": (
            "Static, self-managed, privacy-first architecture. "
            "Six layers: browser request, static host with strict "
            "headers, site files, offline service-worker cache, "
            "signed integrity and identity files, and frozen "
            "public release archives."
        ),
        "L_browser": "Browser",
        "L_host": "Static Host",
        "L_site": "Site Files",
        "L_offline": "Offline",
        "L_trust": "Trust",
        "L_archive": "Archive",
        "L_flow": "Flow",
        "user_https": "User · HTTPS",
        "user_https_m": "User · HTTPS",
        "no_cookies": "No Cookies · No Analytics",
        "tls": "TLS · HSTS",
        "hsts_sni": "HSTS, SNI",
        "tls_hsts": "TLS · HSTS",
        "host_label": "Apache · Gandi, Paris",
        "headers": "Strict Headers · CSP · HSTS",
        "coop": "COOP · COEP · CORP",
        "corp": "Permissions Policy Locked",
        "perms": "SRI on CSS · JS",
        "perms_sub": "Subresource Integrity",
        "html": "HTML",
        "html_sub": "10 Served Pages",
        "css": "CSS",
        "css_sub": "Signifier · Söhne",
        "js": "Vanilla JS",
        "js_sub": "No Framework",
        "fonts": "Self-Managed Fonts",
        "fonts_sub": "8 woff2, Latin Subset",
        "site_files": "HTML · CSS · Vanilla JS",
        "site_sub_1": "Signifier · Söhne · Söhne Mono",
        "site_sub_2": "Self-Managed Fonts · 8 woff2",
        "site_sub_3": "No Framework, No Bundler",
        "sw": "Service Worker",
        "sw_sub": "Local Cache · Network First",
        "cache": "Cache",
        "cache_sub": "Core Pages · Fonts · CSS · JS",
        "fallback": "Offline",
        "fallback_sub": "After First Load",
        "sw_local": "Service Worker · Local Cache",
        "sw_local_sub": "Network First",
        "sw_local_2": "Offline After First Load",
        "integrity": "integrity.json",
        "integrity_sub": "SHA-256 Manifest",
        "sig": "integrity.json.sig",
        "sig_sub": "Detached PGP Signature",
        "sig_sub_m": "Detached PGP Signature",
        "pgp": ".well-known/pgp-key.asc",
        "pgp_sub": "PGP Public Key",
        "wellknown": ".well-known/",
        "wellknown_sub": "person.json · security.txt",
        "feb": "February 2026",
        "apr": "May 2026",
        "frozen": "Frozen, Signed",
        "frozen_sub": "Archive-Local Assets",
        "archive_label": "Frozen Public Releases",
        "flow_long": "Browser → TLS → Apache → Site Files → Service Worker → Offline",
        "flow_meta": "Trust Files Signed and Verifiable · Archives Frozen and Immutable",
        "flow_short": "Browser → Host → Site → Cache → Trust → Archive",
    },
    "fr": {
        "title": "Architecture de trentpower.fr",
        "desc": (
            "Architecture statique, auto-gérée et respectueuse "
            "de la vie privée. Six couches : requête navigateur, "
            "hébergement avec en-têtes stricts, fichiers statiques, "
            "cache hors ligne via service worker, fichiers "
            "d'intégrité et d'identité signés, et archives "
            "publiques figées."
        ),
        "L_browser": "Navigateur",
        "L_host": "Hébergement",
        "L_site": "Fichiers",
        "L_offline": "Hors ligne",
        "L_trust": "Confiance",
        "L_archive": "Archive",
        "L_flow": "Parcours",
        "user_https": "Utilisateur · HTTPS",
        "user_https_m": "Utilisateur · HTTPS",
        "no_cookies": "Sans Cookies · Sans Analyse",
        "tls": "TLS · HSTS",
        "hsts_sni": "HSTS, SNI",
        "tls_hsts": "TLS · HSTS",
        "host_label": "Apache · Gandi, Paris",
        "headers": "En-têtes Stricts · CSP · HSTS",
        "coop": "COOP · COEP · CORP",
        "corp": "Permissions Policy Verrouillée",
        "perms": "SRI sur CSS · JS",
        "perms_sub": "Subresource Integrity",
        "html": "HTML",
        "html_sub": "10 Pages Servies",
        "css": "CSS",
        "css_sub": "Signifier · Söhne",
        "js": "JS Pur",
        "js_sub": "Aucun Framework",
        "fonts": "Polices Auto-Gérées",
        "fonts_sub": "8 woff2, Sous-Ensemble Latin",
        "site_files": "HTML · CSS · JS Pur",
        "site_sub_1": "Signifier · Söhne · Söhne Mono",
        "site_sub_2": "Polices Auto-Gérées · 8 woff2",
        "site_sub_3": "Aucun Framework, Aucun Bundler",
        "sw": "Service Worker",
        "sw_sub": "Cache Local · Réseau d'Abord",
        "cache": "Cache",
        "cache_sub": "Pages Clés · Polices · CSS · JS",
        "fallback": "Hors Ligne",
        "fallback_sub": "Après le Premier Chargement",
        "sw_local": "Service Worker · Cache Local",
        "sw_local_sub": "Réseau d'Abord",
        "sw_local_2": "Hors Ligne Après le 1er Chargement",
        "integrity": "integrity.json",
        "integrity_sub": "Manifeste SHA-256",
        "sig": "integrity.json.sig",
        "sig_sub": "Signature PGP Détachée",
        "sig_sub_m": "Signature PGP Détachée",
        "pgp": ".well-known/pgp-key.asc",
        "pgp_sub": "Clé Publique PGP",
        "wellknown": ".well-known/",
        "wellknown_sub": "person.json · security.txt",
        "feb": "Février 2026",
        "apr": "Mai 2026",
        "frozen": "Figées, Signées",
        "frozen_sub": "Ressources Locales à l'Archive",
        "archive_label": "Versions Publiques Figées",
        "flow_long": "Navigateur → TLS → Apache → Fichiers Statiques → Service Worker → Hors Ligne",
        "flow_meta": "Fichiers de Confiance Signés et Vérifiables · Archives Figées et Immuables",
        "flow_short": "Navigateur → Hôte → Site → Cache → Confiance → Archive",
    },
}

# ─── desktop svg template (1200×680) ────────────────────────────────
DESKTOP = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 680" role="img" aria-labelledby="arch-title arch-desc">
  <title id="arch-title">{title}</title>
  <desc id="arch-desc">{desc}</desc>
  <style>
    .panel    {{ fill: #FFFEFA; stroke: #D8D4CC; stroke-width: 1; }}
    .surface  {{ fill: #EDEAE4; stroke: #D8D4CC; stroke-width: 1; }}
    .rule     {{ stroke: #E6E1D8; stroke-width: 1; fill: none; }}
    .struct   {{ stroke: #D8D4CC; stroke-width: 1; fill: none; }}
    .accent-mark {{ fill: #6E1A14; }}
    .label    {{ font-family: 'Söhne', system-ui, -apple-system, sans-serif; font-size: 13px; font-weight: 500; fill: #1F1E1C; }}
    .sublabel {{ font-family: 'Söhne Mono', ui-monospace, Menlo, monospace; font-size: 10.5px; fill: #5C5955; letter-spacing: 0.04em; }}
    .layer-title {{ font-family: 'Söhne Mono', ui-monospace, Menlo, monospace; font-size: 10px; fill: #706B66; letter-spacing: 0.14em; text-transform: uppercase; }}
    .num      {{ font-family: 'Söhne Mono', ui-monospace, Menlo, monospace; font-size: 10px; fill: #6E1A14; font-weight: 500; letter-spacing: 0.14em; }}
  </style>

  <!-- 01 BROWSER -->
  <text x="32"  y="92"  class="num">01</text>
  <text x="60"  y="92"  class="layer-title">{L_browser}</text>
  <rect x="280" y="72"  width="240" height="44" class="panel"/>
  <text x="296" y="93"  class="label">{user_https}</text>
  <text x="296" y="108" class="sublabel">{no_cookies}</text>
  <rect x="540" y="72"  width="180" height="44" class="surface"/>
  <text x="556" y="93"  class="label">{tls}</text>
  <text x="556" y="108" class="sublabel">{hsts_sni}</text>

  <!-- 02 STATIC HOST -->
  <text x="32"  y="172" class="num">02</text>
  <text x="60"  y="172" class="layer-title">{L_host}</text>
  <rect x="280" y="152" width="240" height="44" class="panel"/>
  <text x="296" y="173" class="label">{host_label}</text>
  <text x="296" y="188" class="sublabel">{headers}</text>
  <rect x="540" y="152" width="180" height="44" class="surface"/>
  <text x="556" y="173" class="label">{coop}</text>
  <text x="556" y="188" class="sublabel">{corp}</text>
  <rect x="740" y="152" width="200" height="44" class="surface"/>
  <text x="756" y="173" class="label">{perms}</text>
  <text x="756" y="188" class="sublabel">{perms_sub}</text>
  <line x1="32"  y1="208" x2="1168" y2="208" class="rule"/>

  <!-- 03 SITE FILES -->
  <text x="32"  y="252" class="num">03</text>
  <text x="60"  y="252" class="layer-title">{L_site}</text>
  <rect x="280" y="232" width="160" height="44" class="panel"/>
  <text x="296" y="253" class="label">{html}</text>
  <text x="296" y="268" class="sublabel">{html_sub}</text>
  <rect x="460" y="232" width="160" height="44" class="panel"/>
  <text x="476" y="253" class="label">{css}</text>
  <text x="476" y="268" class="sublabel">{css_sub}</text>
  <rect x="640" y="232" width="160" height="44" class="panel"/>
  <text x="656" y="253" class="label">{js}</text>
  <text x="656" y="268" class="sublabel">{js_sub}</text>
  <rect x="820" y="232" width="200" height="44" class="panel"/>
  <text x="836" y="253" class="label">{fonts}</text>
  <text x="836" y="268" class="sublabel">{fonts_sub}</text>
  <line x1="32"  y1="288" x2="1168" y2="288" class="rule"/>

  <!-- 04 OFFLINE -->
  <text x="32"  y="332" class="num">04</text>
  <text x="60"  y="332" class="layer-title">{L_offline}</text>
  <rect x="280" y="312" width="280" height="44" class="panel"/>
  <text x="296" y="333" class="label">{sw}</text>
  <text x="296" y="348" class="sublabel">{sw_sub}</text>
  <rect x="580" y="312" width="240" height="44" class="surface"/>
  <text x="596" y="333" class="label">{cache}</text>
  <text x="596" y="348" class="sublabel">{cache_sub}</text>
  <rect x="840" y="312" width="220" height="44" class="surface"/>
  <text x="856" y="333" class="label">{fallback}</text>
  <text x="856" y="348" class="sublabel">{fallback_sub}</text>
  <line x1="32"  y1="368" x2="1168" y2="368" class="rule"/>

  <!-- 05 TRUST — single oxblood dot beside integrity.json is the only accent -->
  <text x="32"  y="412" class="num">05</text>
  <text x="60"  y="412" class="layer-title">{L_trust}</text>
  <rect x="280" y="424" width="200" height="44" class="panel"/>
  <text x="300" y="445" class="label">{integrity}</text>
  <text x="300" y="460" class="sublabel">{integrity_sub}</text>
  <circle cx="288" cy="441" r="3" class="accent-mark"/>
  <rect x="500" y="424" width="200" height="44" class="panel"/>
  <text x="516" y="445" class="label">{sig}</text>
  <text x="516" y="460" class="sublabel">{sig_sub}</text>
  <rect x="720" y="424" width="200" height="44" class="panel"/>
  <text x="736" y="445" class="label">{pgp}</text>
  <text x="736" y="460" class="sublabel">{pgp_sub}</text>
  <rect x="940" y="424" width="180" height="44" class="panel"/>
  <text x="956" y="445" class="label">{wellknown}</text>
  <text x="956" y="460" class="sublabel">{wellknown_sub}</text>
  <line x1="32"  y1="480" x2="1168" y2="480" class="rule"/>

  <!-- 06 ARCHIVE -->
  <text x="32"  y="524" class="num">06</text>
  <text x="60"  y="524" class="layer-title">{L_archive}</text>
  <rect x="280" y="504" width="280" height="44" class="surface"/>
  <text x="296" y="525" class="label">{feb}</text>
  <text x="296" y="540" class="sublabel">/integrity/releases/2026-02/</text>
  <rect x="580" y="504" width="280" height="44" class="surface"/>
  <text x="596" y="525" class="label">{apr}</text>
  <text x="596" y="540" class="sublabel">/integrity/releases/2026-05-08/</text>
  <rect x="880" y="504" width="240" height="44" class="surface"/>
  <text x="896" y="525" class="label">{frozen}</text>
  <text x="896" y="540" class="sublabel">{frozen_sub}</text>

  <line x1="32"  y1="588" x2="1168" y2="588" class="rule"/>
  <text x="32"  y="616" class="layer-title">{L_flow}</text>
  <text x="32"  y="640" class="sublabel">{flow_long}</text>
  <text x="32"  y="660" class="sublabel">{flow_meta}</text>
</svg>
"""

# ─── mobile svg template (390×900) ──────────────────────────────────
MOBILE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 390 900" role="img" aria-labelledby="arch-m-title arch-m-desc">
  <title id="arch-m-title">{title}</title>
  <desc id="arch-m-desc">{desc}</desc>
  <style>
    .panel    {{ fill: #FFFEFA; stroke: #D8D4CC; stroke-width: 1; }}
    .surface  {{ fill: #EDEAE4; stroke: #D8D4CC; stroke-width: 1; }}
    .rule     {{ stroke: #E6E1D8; stroke-width: 1; fill: none; }}
    .accent-mark {{ fill: #6E1A14; }}
    .connector {{ stroke: #D8D4CC; stroke-width: 1; fill: none; stroke-dasharray: 2 3; }}
    .label    {{ font-family: 'Söhne', system-ui, -apple-system, sans-serif; font-size: 12px; font-weight: 500; fill: #1F1E1C; }}
    .sublabel {{ font-family: 'Söhne Mono', ui-monospace, Menlo, monospace; font-size: 10px; fill: #5C5955; letter-spacing: 0.04em; }}
    .num      {{ font-family: 'Söhne Mono', ui-monospace, Menlo, monospace; font-size: 10px; fill: #6E1A14; font-weight: 500; letter-spacing: 0.14em; }}
    .layer-title {{ font-family: 'Söhne Mono', ui-monospace, Menlo, monospace; font-size: 10px; fill: #706B66; letter-spacing: 0.14em; text-transform: uppercase; }}
  </style>

  <!-- 01 BROWSER -->
  <text x="20"  y="76"  class="num">01</text>
  <text x="48"  y="76"  class="layer-title">{L_browser}</text>
  <rect x="20" y="86"  width="350" height="62" class="panel"/>
  <text x="36" y="108" class="label">{user_https_m}</text>
  <text x="36" y="124" class="sublabel">{no_cookies}</text>
  <text x="36" y="139" class="sublabel">{tls_hsts}</text>
  <line x1="195" y1="156" x2="195" y2="178" class="connector"/>

  <!-- 02 STATIC HOST -->
  <text x="20"  y="200" class="num">02</text>
  <text x="48"  y="200" class="layer-title">{L_host}</text>
  <rect x="20" y="210" width="350" height="78" class="panel"/>
  <text x="36" y="232" class="label">{host_label}</text>
  <text x="36" y="248" class="sublabel">{headers}</text>
  <text x="36" y="263" class="sublabel">{coop} · {corp}</text>
  <text x="36" y="278" class="sublabel">{perms}</text>
  <line x1="195" y1="296" x2="195" y2="318" class="connector"/>

  <!-- 03 SITE FILES -->
  <text x="20"  y="340" class="num">03</text>
  <text x="48"  y="340" class="layer-title">{L_site}</text>
  <rect x="20" y="350" width="350" height="78" class="panel"/>
  <text x="36" y="372" class="label">{site_files}</text>
  <text x="36" y="388" class="sublabel">{site_sub_1}</text>
  <text x="36" y="403" class="sublabel">{site_sub_2}</text>
  <text x="36" y="418" class="sublabel">{site_sub_3}</text>
  <line x1="195" y1="436" x2="195" y2="458" class="connector"/>

  <!-- 04 OFFLINE -->
  <text x="20"  y="480" class="num">04</text>
  <text x="48"  y="480" class="layer-title">{L_offline}</text>
  <rect x="20" y="490" width="350" height="62" class="surface"/>
  <text x="36" y="512" class="label">{sw_local}</text>
  <text x="36" y="528" class="sublabel">{sw_local_sub}</text>
  <text x="36" y="543" class="sublabel">{sw_local_2}</text>
  <line x1="195" y1="560" x2="195" y2="582" class="connector"/>

  <!-- 05 TRUST — single oxblood dot is the only accent -->
  <text x="20"  y="604" class="num">05</text>
  <text x="48"  y="604" class="layer-title">{L_trust}</text>
  <rect x="20" y="616" width="350" height="78" class="panel"/>
  <circle cx="28" cy="635" r="3" class="accent-mark"/>
  <text x="40" y="638" class="label">{integrity}</text>
  <text x="40" y="654" class="sublabel">{integrity_sub}</text>
  <text x="36" y="673" class="label">{sig}</text>
  <text x="36" y="689" class="sublabel">{sig_sub_m}</text>
  <line x1="195" y1="702" x2="195" y2="724" class="connector"/>

  <!-- 06 ARCHIVE -->
  <text x="20"  y="746" class="num">06</text>
  <text x="48"  y="746" class="layer-title">{L_archive}</text>
  <rect x="20" y="756" width="350" height="62" class="surface"/>
  <text x="36" y="778" class="label">{archive_label}</text>
  <text x="36" y="794" class="sublabel">/integrity/releases/2026-02/</text>
  <text x="36" y="809" class="sublabel">/integrity/releases/2026-05-08/</text>

  <line x1="20" y1="848" x2="370" y2="848" class="rule"/>
  <text x="20" y="876" class="sublabel">{flow_short}</text>
</svg>
"""

import sys  # noqa: E402

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

ROOT = str(PUBLIC_DIR)
IMG_DIR = os.path.join(ROOT, "images", "architecture")
os.makedirs(IMG_DIR, exist_ok=True)

written = []
for lang in LANGS:
    d = DESKTOP.format(**L[lang])
    m = MOBILE.format(**L[lang])
    open(os.path.join(IMG_DIR, f"architecture.{lang}.svg"), "w", encoding="utf-8").write(d)
    open(os.path.join(IMG_DIR, f"architecture-mobile.{lang}.svg"), "w", encoding="utf-8").write(m)
    written.extend([f"architecture.{lang}.svg", f"architecture-mobile.{lang}.svg"])

# english copies are the no-JS defaults
open(os.path.join(IMG_DIR, "architecture.svg"), "w", encoding="utf-8").write(
    DESKTOP.format(**L["en"])
)
open(os.path.join(IMG_DIR, "architecture-mobile.svg"), "w", encoding="utf-8").write(
    MOBILE.format(**L["en"])
)
written.extend(["architecture.svg", "architecture-mobile.svg"])

print(f"✓ Wrote {len(written)} SVGs to {IMG_DIR}")
for f in written:
    print(f"  {f}")
