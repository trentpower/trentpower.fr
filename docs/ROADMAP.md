# Roadmap

What this project intends to do — and not do — over the next year
(written 2026-06-12, revisited at least annually).

## Will do

- **Editions.** New editions continue on an irregular but ongoing
  cadence. Editions are additive: each new edition joins the ledger and
  every previous edition's frozen archive remains published and
  verifiable, permanently.
- **JavaScript consolidation.** Continue splitting the remaining
  monolithic client script into behaviour-scoped modules and deleting
  runtime-rendering code, per the "no hidden machinery" rule — the page
  must mean the same thing with JavaScript disabled.
- **Tooling remediation.** Finish the deferred consolidation items from
  the 2026-06 cleanup pass (remaining shared-helper extraction and the
  nested-@layer CSS wrinkle).
- **Quality gates.** Keep the enforced lint gate at zero findings and
  the test suite's statement coverage at or above its measured level;
  new tooling behaviour ships with tests, per the pull request template.
- **Security upkeep.** Weekly dependency review (Dependabot), scheduled
  Scorecard and CodeQL runs, same-day handling of advisories that touch
  committed dependency files, signed releases per edition.

## Will not do

- No CMS, no server-side runtime, no JavaScript frameworks. The site
  stays static, hand-built and inspectable.
- No analytics, trackers, cookies or third-party embeds. Ever.
- No comment system. Feedback goes through the channels in
  CONTRIBUTING.md.
- No external badge services or third-party security tooling beyond the
  GitHub-native stack already documented in docs/github-rulesets.md.
- No change to the authorship model: this remains a single-author
  publication. Governance is documented in GOVERNANCE.md, including
  what happens if the author stops.
