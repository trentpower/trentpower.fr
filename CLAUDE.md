# trentpower.fr — agent instructions

Static, bilingual, source-verifiable personal publication. Pure HTML/CSS/vanilla
JS, no build framework; a Python + Bash pipeline under `tools/` builds, gates,
signs, and verifies each edition. Start with [README.md](README.md) and
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Agent skills

Per-repo configuration consumed by the installed engineering skills
(`to-issues`, `triage`, `qa`, `to-prd`, `improve-codebase-architecture`,
`diagnosing-bugs`, `tdd`, …).

### Issue tracker

Issues live in this repo's GitHub Issues, via the `gh` CLI. See
`docs/agents/issue-tracker.md`.

### Triage labels

Canonical five-role vocabulary, label strings equal their role names. See
`docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root (created lazily
by `/domain-modeling`). See `docs/agents/domain.md`.
