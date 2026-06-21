# Score Ledger — live-site observational audit

A lightweight, **local-only** validation score ledger for trentpower.fr. It
runs a set of checks against a small list of live URLs, stores timestamped
results in SQLite, and produces comparable Markdown + HTML reports over time.

It is deliberately **not** a deployment gate, not a public website feature, and
not a full observatory. It is a trusted scoring history: clean, comparable
evidence first.

Lives under `tools/score-ledger/`.

---

## Retention and coverage treatment (intentional)

Score-ledger **remains in this repository for now** — the decision is
deliberate. It documents and supports the repository's quality-score history,
and removing it would discard that trust evidence. No migration to
`private.trentpower.fr` is decided; the code stays here.

What is tracked vs local-only:

- **Code is tracked** in git (the CLI, `lib`, `db`, `compare`, `report`,
  `triage`, `validators/`, `config.yml`).
- **Data, reports, and keys are local-only** and gitignored (`data/`,
  `reports/`, `config.local.yml`) — see [Local-only data + reports](#local-only-data--reports-gitignored).

How coverage treats it:

- Score-ledger is **excluded from the `TEST COVERAGE` metric** (see
  [`docs/COVERAGE.md`](COVERAGE.md)). It is a live-site network audit tool that
  hits external services (W3C, SSL Labs, PageSpeed) against the deployed site, so
  unit-test coverage of its modules is not meaningful. The four coverage
  `--source` trees in `tools/quality/coverage.sh` do not include
  `tools/score-ledger/`.
- This is **not** a way to inflate the coverage number by hiding untested code.
  Its one repo-coupled seam — the signed-`TESTRESULTS.txt` export path — **is**
  unit-tested (`tools/quality/tests/test_score_ledger_export.py`). The rest is
  validated by running it against the live site and reading the reports, not by
  unit tests.

---

## Purpose — time-series scoring, not a verdict

For each run it records, per target URL:

- what was checked, when, and what value / status / count / timing came back;
- what changed versus the previous run (improved, declined, new, missing,
  stable);
- the specific observations behind each metric, with supporting evidence.

It stores **atomic facts** in a strict hierarchy:

```
run -> target -> tool_result -> metric -> observation -> evidence
```

**No single overall score is produced.** Raw measurements are preserved;
summaries are derived from them.

On top of the evidence layer there is a **decision layer (V2)**: an Action
Register that triages findings into impact / confidence / actionability with a
recommended next step, derived scorecards, headline trendlines, and a signed
`TESTRESULTS.txt` release attestation. The decision layer never mutates raw
observations — interpretation lives only on the derived `actions` rows.

---

## It tests the LIVE site — deploy first

The targets are the published URLs:

```
https://trentpower.fr/
https://trentpower.fr/en-au/
https://trentpower.fr/fr/
```

The ledger audits the **live** site over HTTPS. **Always deploy and let the
deploy propagate before running it** — it is a post-deploy step, never a
pre-deploy one. Running it before propagation audits the old bytes.

### Why it does not run on the production host

trentpower.fr is static Apache shared hosting: FTP/SFTP only, no SSH, no cron,
no daemon, no production database. The ledger runs **manually from the local
Linux environment** (the Raspberry Pi) against the live URLs. It writes only to
local SQLite and local report files. The public site stays static and
untouched.

---

## NOT a deploy gate

This is the load-bearing distinction:

- The ledger is **observational, never blocking.** Nothing in the build, gate,
  or deploy depends on its output. It is not a CI job — it is slow, Pi-bound,
  and tests the live site after the fact.
- A scorecard `status` of FAIL/REVIEW is a **report signal only.** It does not
  stop a deploy, and it is not consulted by `tools/quality/gate.py` (the blocking
  build gate) or `tools/quality/lint.py` (advisory).
- The build-time gate is the gate. The score ledger is the post-deploy
  observatory. Keep them mentally separate.

### Lighthouse performance is device noise — trust the rolling median

Lighthouse performance scores on the Raspberry Pi are noisy. A single-run dip
is **not** a regression. Every headline metric carries `previous`, `best`, and
`rolling_median` (last 5 runs) baselines so a one-off wobble is not mistaken
for a real decline. **Trust `rolling_median`, not a single run.** Configure
baselines under `comparison:` in `config.yml`.

---

## Local-only data + reports (gitignored)

- `data/` — the SQLite ledger. **Gitignored, never deployed.**
- `reports/` — generated Markdown + HTML reports. **Gitignored, never
  deployed.**
- `config.local.yml` — local overrides (e.g. `action_overrides`). Gitignored.

The score-ledger writes only to its own `reports/` (or `--out`). It never
writes into `public/` and never touches the release-archive generators.

---

## Install

Dependencies (already present on the Pi):

```bash
python3 -m pip install -r tools/score-ledger/requirements.txt
```

(`requests`, `PyYAML`, `beautifulsoup4`, `lxml`.)

## Run

```bash
python3 tools/score-ledger/score_ledger.py run
python3 tools/score-ledger/score_ledger.py run --label "Edition 2026-05-28"
python3 tools/score-ledger/score_ledger.py report --latest
python3 tools/score-ledger/score_ledger.py compare --latest
python3 tools/score-ledger/score_ledger.py history
python3 tools/score-ledger/score_ledger.py testresults --latest --edition 2026-05-28
python3 tools/score-ledger/score_ledger.py sign-testresults --file reports/TESTRESULTS.txt
python3 tools/score-ledger/score_ledger.py verify-testresults --file reports/TESTRESULTS.txt --sig reports/TESTRESULTS.txt.sig
```

`run` creates a timestamped run, stores all facts, compares against the
previous run, derives the Action Register, and writes the reports.

---

## Validators

All active:

- **availability** — status code, redirects, response time, content type/size.
- **headers** — CSP, HSTS, referrer-policy, permissions-policy,
  COOP/COEP/CORP, X-Content-Type-Options, frame protection.
- **metadata** — title, description, canonical, lang, viewport, OG tags,
  hreflang / JSON-LD counts.
- **structured_data** — local JSON-LD parse; schema types; person/website/image.
- **trust_files** — status/type/size/sha256/JSON validity for well-known and
  trust files (checked once at the site root).
- **privacy** — cookies, external/third-party resources, analytics/tracking
  hints.
- **links** — internal/external counts, broken internal links, redirects,
  mixed content (single page; no site-wide crawl).
- **lighthouse** — local Lighthouse CLI: performance/accessibility/
  best-practices/SEO, LCP/CLS/TBT/Speed Index, page weight, request count;
  failed audits become observations. Records `unavailable` (non-fatal) if the
  CLI or Chrome is missing.
- **html_w3c** — W3C Nu validator: error/warning/info counts + per-message
  observations. `unavailable` if unreachable.
- **css_w3c** — W3C Jigsaw validator: per-page CSS error/warning counts (each
  unique stylesheet validated once per run).
- **manual** — site-level placeholders for disabled external integrations.

Phase 3 site-specific trust tests: **csp_quality**, **seo_semantics** (root),
**hreflang**, **service_worker** (root), **content_anchors**, an
**accessibility second lens** (discrete axe categories from Lighthouse's
bundled axe-core), **runtime_privacy** (browser), and **offline** (browser).
The browser checks run in a sequential pass after Lighthouse via the
already-installed Playwright; if Playwright/Chromium is absent they record
`unavailable` and never abort. Toggle the whole pass with `checks.browser_pass`.

---

## TESTRESULTS.txt (signed release attestation)

`testresults` derives a plain-ASCII attestation from the latest run (never
hand-authored): targets, per-area PASS/REVIEW/FAIL summary, key open actions,
the not-a-guarantee caveat, and the signing fingerprint. `sign-testresults`
produces a detached `.sig` via `gpg --local-user <fingerprint>` (fingerprint
from `signing.fingerprint` in config, else derived from
`public/.well-known/pgp-key.asc`); `verify-testresults` checks it with a
throwaway keyring seeded only from the published key.

The score-ledger writes only to its own `reports/` (or `--out`) and **prints**
the steps to copy the pair into `public/integrity/releases/<edition>/` and
register it — it never writes into `public/` or touches the release-archive
generators itself.

---

## Reading the report

Reports land in `tools/score-ledger/reports/`:

- `latest.md` / `latest.html` — always the most recent run.
- `run-<id>.md` / `run-<id>.html` — one pair per run.

The report opens with an overview (metric counts by direction, tool status,
observation new/fixed/still-present), then top changes, an observations diff, a
per-category summary, a per-page summary, and a list of manual/unavailable
checks. The HTML report is self-contained: no external assets, no JavaScript,
no tracking. Direction markers are plain ASCII: `[+]` improved, `[-]` declined,
`[=]` unchanged, `[new]`, `[gone]`, `[~]` not comparable.

### How metric comparison works

The latest run is compared with the previous **finished** run. Each metric is
matched by `(page path, tool, category, metric name)`; the ledger records the
previous value, the numeric delta, and a direction. Direction is decided by the
metric's `comparison_mode` (pinned in `config.yml`):
`higher_better` / `lower_better` (signed delta), `boolean_pass`,
`grade_order` (A+ best), `exact_match` / `neutral` (any difference reported as a
value change but never labelled improved/declined, e.g. a hash rotation). A
metric that cannot resolve a mode is recorded `unavailable` rather than guessing.

### Observations vs metrics vs evidence

- A **metric** is one comparable value, e.g. `html.errors.count = 2`.
- An **observation** is one specific issue behind a metric, e.g. "duplicate id
  footer-edition, line 412". Observations carry a stable `fingerprint` so they
  track across runs as `new`, `still_present`, `fixed`, or `changed`.
- **Evidence** is the proof: source excerpt, selector, header, URL, or line
  number.

---

## Decision layer (V2)

- **Action Register** — significant metric regressions and a small set of
  important observation types are triaged into actions with
  impact / confidence / actionability, a suggested area, and a recommended next
  step. Conservative by default (e.g. a Lighthouse performance drop ≥ 10
  points, broken internal links, HTML errors). Defaults in `triage.py`;
  extend/override via `action_rules` / `noise_rules` in `config.yml`.
- **Known noise** — validator false positives (e.g. W3C Jigsaw rejecting
  modern CSS, bf-cache on a static site) are recorded as subordinate
  `known_noise` actions, visible but never urgent. Raw observations untouched.
- **Action status** carries across runs by a stable `action_key`. To silence
  one, add `action_overrides: {<action_key>: ignored}` to the gitignored
  `config.local.yml`.
- **Scorecards** — five derived PASS/REVIEW/FAIL cards (Publication Quality,
  Performance, Privacy, Security, Trust) with previous status and top driver.
  No single overall score is stored.
- **Trends** — the HTML report shows inline SVG sparklines (last 5 runs, no JS,
  no assets) plus previous / best / rolling-median context.

---

## External integrations

Four external services run once per run (site-level); results appear in the
report's **External integrations** section:

- **Mozilla Observatory** — security grade + score. No API key.
- **SSL Labs** — TLS grade (assessment polled to completion). No API key.
- **PageSpeed Insights** — Lighthouse from Google's infra. **Requires a free
  API key.**
- **WebPageTest** — first-view timings. **Requires a free API key.**

Provide keys via `config.yml` under `integration_settings`
(`pagespeed_api_key`, `webpagetest_api_key`) or env
(`PAGESPEED_API_KEY`, `WPT_API_KEY`). Without a key, that integration records
`unavailable` with a note — it never fails the run. Toggle integrations under
`integrations:`; a disabled one is recorded as a `manual` check with a
`source_url`, never silently omitted. Individual local checks toggle under
`checks:`.

The tool is polite: clear User-Agent, request timeouts, a delay between
external requests, no endless retries.

---

## Known limitations

- Comparison is latest-vs-previous only (no long trend lines yet).
- Link checking covers only the three target pages; no whole-site crawl.
- Privacy analytics/tracking detection is heuristic (host-substring based).
- CSS errors reflect Jigsaw `css3` strictness, not necessarily real defects:
  the `css3` profile is strict and flags modern CSS it does not recognise as
  errors, so `css.errors.count` can look high without real breakage. The ledger
  records Jigsaw's raw counts faithfully; change `css.profile` to adjust.
- External integrations are not automated; recorded as manual checks with a
  `source_url` to run by hand.

---

## Files

```
score_ledger.py     CLI orchestrator (thin)
lib.py              config, http, hashing, result builders, enums, registry
db.py               schema + the single insert choke point
compare.py          metric + observation comparison engine
report.py           Markdown + HTML report generation
config.yml          targets, checks, network, storage, metric registry
validators/         one module per check; manual.py covers disabled integrations
data/               SQLite ledger (gitignored)
reports/            generated reports (gitignored)
```
