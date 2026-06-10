#!/usr/bin/env python3
"""generate_tests_page.py — public test-results page.

Renders the signed TESTRESULTS.txt for the current edition into a
static, language-neutral page at public/tests/index.html. Test results
are signed, language-neutral artefacts (like the release archives), so
the page is built from the same native page system as Verify / Privacy /
the release record: the global page-kicker / page-title / page-lede shell,
security-section blocks, and the integrity-record-card / integrity-rg
record family. No bespoke report design language; content baked at build
time from the signed text file; no hidden machinery.

The single source of truth is the signed file at
public/integrity/releases/<edition>/TESTRESULTS.txt. Output is
deterministic (only values from the signed file + the edition string +
the build's asset_version), so re-running the build is byte-stable.

Runs after generate_release_record.py and before the integrity / SRI /
source-mirror stages, so the page is hashed, SRI-swept and mirrored like
any other public surface. Asset references are stamped with the current
asset_version (read from site-metadata.json); generate_sri.py then adds
the integrity attributes.
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

_HEADERS = {
    "Targets:",
    "Summary:",
    "Key observations:",
    "Report:",
    "Artefacts (SHA-256):",
    "Interpretation:",
    "Signed by:",
}

# summary status -> chip modifier. unknown statuses fall back to na.
_STATUS_CLASS = {"PASS": "pass", "REVIEW": "review", "FAIL": "fail", "NA": "na"}

# preferred lighthouse threshold — at or above is a clean per-target row.
_PERF_THRESHOLD = 90


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fingerprint_spaced(fpr: str) -> str:
    """group a bare 40-hex fingerprint into space-separated quads."""
    raw = fpr.replace(" ", "")
    return " ".join(raw[i : i + 4] for i in range(0, len(raw), 4))


# ─── parse ───────────────────────────────────────────────────────


def _parse(text: str) -> dict:
    lines = text.splitlines()
    meta: dict = {}
    sections: dict = {}
    cur = None
    for raw in lines[1:]:  # skip the "trentpower.fr testresults" title
        stripped = raw.strip()
        if stripped in _HEADERS:
            cur = stripped
            sections[cur] = []
            continue
        if cur is None:
            # header meta region (edition / run / generated / …)
            if ":" in raw and not raw.lstrip().startswith("-"):
                k, v = raw.split(":", 1)
                meta[k.strip()] = v.strip()
            continue
        sections[cur].append(raw)

    if "Summary:" not in sections or "Signed by:" not in sections:
        raise SystemExit(
            "generate_tests_page: TESTRESULTS.txt is missing a Summary "
            "or Signed by block — refusing to emit a half-empty page."
        )

    def items(name):
        return [ln[2:].strip() for ln in sections.get(name, []) if ln.strip().startswith("- ")]

    # summary (top-level categories; performance carries indented sub-targets)
    summary: list[dict] = []
    cur_item = None
    for ln in sections["Summary:"]:
        if ln.startswith("- "):
            cat, rest = (ln[2:].split(":", 1) + [""])[:2]
            parts = rest.strip().split(",", 1)
            status = parts[0].strip()
            detail = parts[1].strip() if len(parts) > 1 else ""
            cur_item = {
                "category": cat.strip(),
                "status": status,
                "detail": detail,
                "targets": [],
                "reason": "",
            }
            summary.append(cur_item)
        elif cur_item is not None and ln.lstrip().startswith("- "):
            t = ln.strip()[2:]
            path, _, score = t.partition(":")
            cur_item["targets"].append((path.strip(), score.strip()))
        elif cur_item is not None and ln.lstrip().lower().startswith("reason:"):
            cur_item["reason"] = ln.split(":", 1)[1].strip()

    # observations: "- [severity] text"
    observations = []
    for ln in items("Key observations:"):
        sev, text = "", ln
        if ln.startswith("[") and "]" in ln:
            sev, text = ln[1 : ln.index("]")], ln[ln.index("]") + 1 :].strip()
        observations.append((sev, text))

    # report / artefacts: "- key: value"
    def kv(name):
        out = []
        for ln in items(name):
            k, _, v = ln.partition(":")
            out.append((k.strip(), v.strip()))
        return out

    interp = " ".join(s.strip() for s in sections.get("Interpretation:", []) if s.strip())

    signed = [s.strip() for s in sections.get("Signed by:", []) if s.strip()]
    signer = signed[0] if signed else "Trent Power"
    fpr = ""
    for s in signed:
        if "fingerprint" in s.lower():
            fpr = s.split(":", 1)[1].strip()

    return {
        "meta": meta,
        "targets": items("Targets:"),
        "summary": summary,
        "observations": observations,
        "report": kv("Report:"),
        "artefacts": kv("Artefacts (SHA-256):"),
        "interpretation": interp,
        "signer": signer,
        "fingerprint": fpr,
    }


# ─── render ──────────────────────────────────────────────────────


def _counts(summary: list[dict]) -> tuple[int, int, int, list[str]]:
    n_pass = sum(1 for s in summary if s["status"] == "PASS")
    n_review = sum(1 for s in summary if s["status"] == "REVIEW")
    n_fail = sum(1 for s in summary if s["status"] == "FAIL")
    review_names = [s["category"] for s in summary if s["status"] == "REVIEW"]
    return n_pass, n_review, n_fail, review_names


def _diagnosis_statement(summary: list[dict]) -> str:
    """one calm sentence: state, then the pass/review/fail breakdown."""
    n_pass, n_review, n_fail, _ = _counts(summary)
    state = (
        "fully verified"
        if (n_fail == 0 and n_review == 0)
        else "healthy"
        if n_fail == 0
        else "under attention"
    )
    pass_c = f"{n_pass} {'check' if n_pass == 1 else 'checks'} pass"
    review_c = f"{n_review} {'remains' if n_review == 1 else 'remain'} under review"
    fail_c = (
        "no checks fail" if n_fail == 0 else f"{n_fail} {'check' if n_fail == 1 else 'checks'} fail"
    )
    return f"This edition is <em>{state}</em>: {pass_c}, {review_c}, and {fail_c}."


def _diagnosis_followup(summary: list[dict]) -> str:
    """second sentence: name the single review area, if there is one."""
    n_pass, n_review, n_fail, review_names = _counts(summary)
    if n_fail:
        names = " and ".join(s["category"] for s in summary if s["status"] == "FAIL")
        return f"{names} {'need' if n_fail > 1 else 'needs'} attention before release."
    if n_review == 1:
        return f"{review_names[0]} remains the only review area."
    if n_review > 1:
        return f"{' and '.join(review_names)} remain the review areas."
    return "Every area passes."


def _chip(status: str, label: str = "") -> str:
    cls = _STATUS_CLASS.get(status.upper(), "na")
    return f'<span class="tests-chip tests-chip--{cls}">{_esc(label or status)}</span>'


# external site validators — moved here from /local/. grouped editorial
# links that open (only when clicked) against the live site root; the
# {url}=https://trentpower.fr/ and {host}=trentpower.fr substitutions from
# the old /local/ renderer are baked in as static hrefs.
_VALIDATORS = [
    (
        "Standards",
        [
            ("HTML", "https://validator.w3.org/nu/?doc=https://trentpower.fr/"),
            (
                "CSS",
                "https://jigsaw.w3.org/css-validator/validator?uri=https://trentpower.fr/&profile=css3svg",
            ),
            ("Schema", "https://validator.schema.org/#url=https://trentpower.fr/"),
            (
                "Rich Results",
                "https://search.google.com/test/rich-results?url=https://trentpower.fr/",
            ),
        ],
    ),
    (
        "Performance",
        [
            ("PageSpeed Insights", "https://pagespeed.web.dev/report?url=https://trentpower.fr/"),
            ("WebPageTest", "https://www.webpagetest.org/?url=https://trentpower.fr/"),
            ("Webhint", "https://webhint.io/scanner/"),
        ],
    ),
    (
        "Trust",
        [
            (
                "Security Headers",
                "https://securityheaders.com/?q=https://trentpower.fr/&followRedirects=on",
            ),
            (
                "Mozilla Observatory",
                "https://developer.mozilla.org/en-US/observatory/analyze?host=trentpower.fr",
            ),
            ("SSL Labs", "https://www.ssllabs.com/ssltest/analyze.html?d=trentpower.fr&latest"),
            ("DNSSEC analyser", "https://dnssec-analyzer.verisignlabs.com/trentpower.fr"),
            ("HSTS preload", "https://hstspreload.org/?domain=trentpower.fr"),
        ],
    ),
    (
        "Search",
        [
            ("Robots reference", "https://en.wikipedia.org/wiki/Robots.txt"),
            (
                "Sitemap validator",
                "https://www.xml-sitemaps.com/validate-xml-sitemap.html?op=validate-xml-sitemap&go=1&sitemapurl=https%3A%2F%2Ftrentpower.fr%2Fsitemap.xml",
            ),
        ],
    ),
]


def _validators_html() -> str:
    groups = []
    for label, items in _VALIDATORS:
        lis = "\n".join(
            f'              <li><a href="{url.replace("&", "&amp;")}" '
            f'target="_blank" rel="noopener noreferrer">{_esc(name)}</a></li>'
            for name, url in items
        )
        groups.append(
            '          <div class="site-validators-group">\n'
            f'            <p class="site-validators-group__label">{_esc(label)}</p>\n'
            '            <ul class="site-validators-group__items">\n'
            f"{lis}\n"
            "            </ul>\n"
            "          </div>"
        )
    return "\n".join(groups)


def _render(ed: str, asset_version: str, data: dict) -> str:
    human = human_date(ed)
    m = data["meta"]
    v = f"?v={asset_version}"
    rel_dir = f"/integrity/releases/{ed}/"
    fpr_spaced = _fingerprint_spaced(data["fingerprint"])
    n_pass, n_review, n_fail, _ = _counts(data["summary"])

    # scorecards — small archival panels, each self-explanatory
    cards = []
    for s in data["summary"]:
        detail = s["detail"] or s["reason"] or ""
        cards.append(
            '          <div class="tests-card">\n'
            '            <div class="tests-card__top">\n'
            f'              <span class="tests-card__name">{_esc(s["category"])}</span>\n'
            f"              {_chip(s['status'])}\n"
            "            </div>\n"
            f'            <p class="tests-card__detail">{_esc(detail)}</p>\n'
            "          </div>"
        )
    cards_html = "\n".join(cards)

    tally_html = (
        f'<span class="tests-tally__item tests-tally__item--pass">{n_pass} Pass</span>'
        '<span class="tests-tally__sep" aria-hidden="true">·</span>'
        f'<span class="tests-tally__item tests-tally__item--review">{n_review} Review</span>'
        '<span class="tests-tally__sep" aria-hidden="true">·</span>'
        f'<span class="tests-tally__item tests-tally__item--fail">{n_fail} Fail</span>'
    )

    # performance by target
    perf = next((s for s in data["summary"] if s["targets"]), None)
    perf_section = ""
    if perf:
        rows = []
        for path, score in perf["targets"]:
            clean = score.isdigit() and int(score) >= _PERF_THRESHOLD
            word = "PASS" if clean else "REVIEW"
            rows.append(
                "            <tr>\n"
                f'              <th scope="row"><code>{_esc(path)}</code></th>\n'
                f'              <td class="tests-perf__score">{_esc(score)}</td>\n'
                f'              <td class="tests-perf__status">{_chip(word)}</td>\n'
                "            </tr>"
            )
        why = ""
        if perf["reason"]:
            r = perf["reason"]
            r = r[:1].upper() + r[1:]
            why = (
                f'        <p class="tests-why"><span class="tests-why__label">'
                f"Why review</span> {_esc(r)}</p>\n"
            )
        perf_section = f"""      <section class="security-section" aria-labelledby="tests-perf-h">
        <h2 class="security-section-heading" id="tests-perf-h">Performance by Target</h2>
        <p>Behind the performance line: the Lighthouse score recorded for each measured page, set against the preferred threshold.</p>
        <table class="tests-perf">
          <thead><tr><th scope="col">Target</th><th scope="col" class="tests-perf__score">Score</th><th scope="col">Status</th></tr></thead>
          <tbody>
{chr(10).join(rows)}
          </tbody>
        </table>
        <p class="tests-threshold">Preferred threshold: {_PERF_THRESHOLD}</p>
{why}      </section>
"""

    # what needs attention
    notes = []
    for sev, text in data["observations"]:
        sev_cls = sev.lower() if sev.lower() in ("high", "medium", "low") else "low"
        sev_label = sev.title() if sev else "Note"
        notes.append(
            '          <li class="tests-note">\n'
            f'            <span class="tests-sev tests-sev--{sev_cls}">{_esc(sev_label)}</span>\n'
            f'            <span class="tests-note__text">{_esc(text)}</span>\n'
            "          </li>"
        )
    attn_section = ""
    if notes:
        attn_section = f"""      <section class="security-section" aria-labelledby="tests-attn-h">
        <h2 class="security-section-heading" id="tests-attn-h">What Needs Attention</h2>
        <ul class="tests-notes">
{chr(10).join(notes)}
        </ul>
      </section>
"""

    # run provenance — native record rows
    run_items = [("Edition", ed)]
    for k in ("Run", "Environment", "Generated", "Git commit"):
        if m.get(k):
            run_items.append((k, m[k]))
    for k, val in data["report"]:
        if k.lower().startswith("ledger run"):
            continue
        run_items.append((k, val))
    run_rows = "\n".join(
        '            <div class="integrity-rg">\n'
        f'              <dt class="integrity-rg-label">{_esc(k)}</dt>\n'
        f'              <dd class="integrity-rg-value">{_esc(val)}</dd>\n'
        "            </div>"
        for k, val in run_items
    )

    art_card = ""
    if data["artefacts"]:
        art_rows = "\n".join(
            '            <div class="integrity-rg">\n'
            f'              <dt class="integrity-rg-label">{_esc(name)}</dt>\n'
            f'              <dd class="integrity-rg-value">{_esc(h)}</dd>\n'
            "            </div>"
            for name, h in data["artefacts"]
        )
        art_card = f"""        <div class="integrity-record-card">
          <p class="integrity-record-kicker">Artefacts</p>
          <h3 class="integrity-record-title">SHA-256</h3>
          <dl class="integrity-record-dl">
{art_rows}
          </dl>
        </div>
"""

    interp = _esc(data["interpretation"])

    return f"""<!doctype html>
<!--
  trentpower.fr · /tests/
  Signed test + verification snapshot · edition {ed}
  Renders the signed TESTRESULTS.txt for this edition. No analytics, no cookies, no external assets.
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
  <title>Test Results · {human} · Trent Power</title>
  <meta name="description" content="Signed test and verification snapshot for trentpower.fr, {human} edition.">
  <meta name="document-edition" content="{ed}">
  <meta name="robots" content="noindex, follow">
  <meta name="referrer" content="no-referrer">
  <link rel="canonical" href="https://trentpower.fr/tests/">

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
<body data-page="tests" data-layout="masthead" data-surface="record" data-masthead="brand-only" data-edition="{ed}">

<a href="#main" class="skip-link">Skip to content</a>

<!-- masthead -->
<header class="site-header" data-component="site-header">
  <div class="nav">
    <div class="nav-inner">
      <a class="nav-mark u-author" href="/" aria-label="Trent Power home"><span>Trent</span> <span>Power</span></a>
    </div>
  </div>
</header>

<main class="site tests-page" id="main" tabindex="-1">
  <div class="page">

    <!-- primary · statement -->
    <p class="page-kicker">Publication Test Record</p>
    <h1 class="page-title hero-stack">Test Results</h1>
    <div class="page-body">
      <p class="page-lede">{_diagnosis_statement(data["summary"])}</p>
      <p>{_diagnosis_followup(data["summary"])}</p>
      <p class="tests-tally" aria-label="Pass, review and fail counts">{tally_html}</p>

      <!-- layer 2 · interpretation — what the result means, then what to watch.
           the reader grasps the outcome before any score, metric or artefact;
           this is a signed publication record, not a CI dashboard. -->
      <section class="security-section" aria-labelledby="tests-interp-h">
        <h2 class="security-section-heading" id="tests-interp-h">Interpretation</h2>
        <p>{interp}</p>
      </section>

{attn_section}      <!-- layer 3 · evidence — per-area status, metrics, attestation, provenance -->
      <section class="security-section" aria-labelledby="tests-status-h">
        <h2 class="security-section-heading" id="tests-status-h">Status by Area</h2>
        <p>The verdict above, area by area: each card states how one part of the edition fared and why.</p>
        <div class="tests-scorecards">
{cards_html}
        </div>
      </section>

{perf_section}      <!-- attestation -->
      <section class="security-section" aria-labelledby="tests-attest-h">
        <h2 class="security-section-heading" id="tests-attest-h">Attestation</h2>
        <div class="integrity-record-card">
          <p class="integrity-record-kicker">Signed snapshot</p>
          <h3 class="integrity-record-title">TESTRESULTS.txt</h3>
          <p class="integrity-record-status">Detached PGP signature · Edition {ed}</p>
          <dl class="integrity-record-dl">
            <div class="integrity-rg integrity-rg--ruled">
              <dt class="integrity-rg-label">File</dt>
              <dd class="integrity-rg-value"><a class="integrity-rg-link" href="{rel_dir}TESTRESULTS.txt">TESTRESULTS.txt</a></dd>
            </div>
            <div class="integrity-rg">
              <dt class="integrity-rg-label">Signature</dt>
              <dd class="integrity-rg-value"><a class="integrity-rg-link" href="{rel_dir}TESTRESULTS.txt.sig">TESTRESULTS.txt.sig</a></dd>
              <dd class="integrity-rg-desc">Detached PGP signature</dd>
            </div>
            <div class="integrity-rg">
              <dt class="integrity-rg-label">Fingerprint</dt>
              <dd class="integrity-rg-value">{_esc(fpr_spaced)}</dd>
            </div>
          </dl>
        </div>
        <p class="tests-signed">Signed by <strong>{_esc(data["signer"])}</strong><br><span class="tests-fpr">{_esc(fpr_spaced)}</span></p>
        <details class="tests-verify">
          <summary>View verification command</summary>
          <p>Download the snapshot and its signature, then verify against the published public key.</p>
          <pre class="tests-cmd">curl -O https://trentpower.fr{rel_dir}TESTRESULTS.txt <span class="tests-cmd__op">&amp;&amp;</span>
curl -O https://trentpower.fr{rel_dir}TESTRESULTS.txt.sig <span class="tests-cmd__op">&amp;&amp;</span>
gpg --verify TESTRESULTS.txt.sig TESTRESULTS.txt</pre>
        </details>
      </section>

      <!-- run + artefacts -->
      <section class="security-section" aria-labelledby="tests-run-h">
        <h2 class="security-section-heading" id="tests-run-h">Run &amp; Artefacts</h2>
        <p>Where this record came from: the run that produced it and the signed files it can be checked against.</p>
        <div class="integrity-record-card">
          <p class="integrity-record-kicker">Provenance</p>
          <h3 class="integrity-record-title">Score ledger</h3>
          <dl class="integrity-record-dl">
{run_rows}
          </dl>
        </div>
{art_card}        <p class="tests-downloads">Open <a href="{rel_dir}TESTRESULTS.txt">TESTRESULTS.txt</a>, its <a href="{rel_dir}TESTRESULTS.txt.sig">signature</a>, or the full <a href="{rel_dir}">release archives</a>.</p>
      </section>

      <!-- validate this site · external validators, open only when chosen -->
      <section class="security-section" aria-labelledby="tests-validators-h">
        <h2 class="security-section-heading" id="tests-validators-h">Validate this site</h2>
        <p>External validators open only when chosen. Each opens in a new tab and checks the live site.</p>
        <div class="site-validators">
{_validators_html()}
        </div>
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

<!-- body · construction rail -->
<div class="construction-rail" data-construction-rail aria-hidden="true">
  <span class="construction-rail__stripe" aria-hidden="true"></span>
  <span class="construction-rail__label">
    <span class="construction-rail__dot" aria-hidden="true"></span>
    Under Construction
  </span>
  <span class="construction-rail__stripe" aria-hidden="true"></span>
</div>
</body>
</html>
"""


def main() -> int:
    ed = json.loads(IDENTITY_CANONICAL.read_text(encoding="utf-8"))["edition"]
    src = PUBLIC_DIR / "integrity" / "releases" / ed / "TESTRESULTS.txt"
    if not src.is_file():
        raise SystemExit(
            f"generate_tests_page: no TESTRESULTS.txt for edition {ed} "
            f"at {src} — run after generate_release_record.py with a signed "
            f"snapshot present."
        )

    meta = json.loads((PUBLIC_DIR / "site-metadata.json").read_text(encoding="utf-8"))
    asset_version = meta.get("asset_version", ed)

    data = _parse(src.read_text(encoding="utf-8"))
    out_dir = PUBLIC_DIR / "tests"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(_render(ed, asset_version, data), encoding="utf-8")
    print(f"OK: test-results page → tests/index.html (edition {ed})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
