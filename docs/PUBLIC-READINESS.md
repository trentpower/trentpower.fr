# Public-readiness — policy & checklist

This repository builds a static, bilingual publication (authored editions live
under `/en-au/` + `/fr/`; `/` is the language gate). It is a **public GitHub
repo**. This document is the policy + checklist that keeps private operational
state, secrets and machine-local artefacts out of the published history.

The companion references are
[`BUILD-AND-DEPLOYMENT.md`](./BUILD-AND-DEPLOYMENT.md) (what the build produces
and the CI/secret model) and
[`GATES-CHECKS-AND-QUALITY.md`](./GATES-CHECKS-AND-QUALITY.md) (the deploy gate +
check registry).

---

## 0. Public-release status

**2026-06-10 — released public.** The decisions of record:

- **Licensing** is dual: code under MIT ([`LICENSE`](../LICENSE)), authored
  content under CC BY-SA 4.0 ([`CONTENT-RIGHTS.md`](../CONTENT-RIGHTS.md));
  [`NOTICE.md`](../NOTICE.md) is the map.
- **Licensed typefaces** (Klim Signifier/Söhne) are untracked from the tree
  going forward and declared in `metadata/repo-exclusions.json`; a fresh
  checkout restores them with `tools/build/fetch_licensed_fonts.py`, verified
  against the signed `integrity.json`. They remain in pre-release git history —
  an accepted trade-off taken instead of a second history rewrite.
- **Internal process records** (the authorship-trail audit reports) are
  untracked and stay local.
- The full-history secret scan runs via `tools/quality/secret_scan.py`
  (gitleaks engine, `scan_git_history.py` fallback); the machine report lands
  at `reports/checks/last-secret-scan.json`, and the blocking
  `public_readiness` gate (see §6) holds the posture on every build.

---

## 1. What must NEVER be committed

These are operational secrets and private surfaces. **All are already covered by
`.gitignore`** — this section records _why_, so the protection is never weakened
by accident.

| Category                | Examples / patterns                                                                                              | Why it must stay out                                                                 |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| **Private keys**        | `id_ed25519`, `id_rsa`, `*.asc` (GPG private/exported keys), `*.totp_key`, `*-key.txt`, GCP service-account JSON | A leaked deploy key, signing key or service-account credential is a full compromise. |
| **Server config**       | `SERVER.md`, `*.nginx`                                                                                           | Reveals host topology, paths and operational layout of the live server.              |
| **The `private/` tree** | `private/`, `console_data/`                                                                                      | The private console + its runtime data are a separate, non-public surface.           |
| **Private docs**        | `docs/private/`, `docs/audits/`, `docs/AUDIT-*.md`                                                               | Internal audits and notes that are not part of the public record.                    |
| **Local secrets / env** | `.env`, `.env.*`, `.gate_credentials`, `config.local.php`                                                        | Local-only secret material; must never enter history.                                |
| **Databases**           | `*.sqlite`, `*.db`                                                                                               | May embed private operational state.                                                 |

> Note on `*.asc`: the **published** PGP key is served at
> `/.well-known/pgp-key.asc` (public, intentional). A _private_ exported key would
> also carry an `.asc` extension — keep any private `.asc` out, and never commit
> exported secret keyrings.

---

## 2. What belongs in `.gitignore`

Beyond the secrets above, the ignore file also excludes machine-local working
artefacts so they never pollute the public tree:

- **Editor / scratch backups** — `*.bak`, `*.orig`, `*.tmp`.
- **Local review/working reports under `reports/`** — `reports/*.md`,
  `reports/*.txt`, `reports/*.pdf` (build traces, changelog drafts, audit PDFs,
  the public-readiness inventory + cleanup report, the two authorship-trail
  audit `.txt` files — kept locally, allow-listed by
  `validate_git_metadata.py` when present, never published).
- **Machine-readable check reports** — `reports/checks/*.json` (runtime
  artefacts carrying a real wall-clock timestamp; the dir is kept via
  `reports/checks/.gitkeep`).
- **Terminal build logs** — `reports/build/*.log` (the `.gitkeep`
  placeholder is re-included).
- **Caches** — `__pycache__/`, `*.pyc`, `.mypy_cache/`, `.pytest_cache/`.
- **Node tooling** — `node_modules/` (dev quality tooling, never shipped).
- **Build scratch space** — `.build/`, `build/`, `release/`.
- **Operator-local snapshots** — `_rollback_*/`, `_archives/`, `_licences/`.
- **Forbidden public artefacts (defence-in-depth)** — a `public/**/…` block
  mirrors the build gate: no `.DS_Store`, `Thumbs.db`, `*.swp`, `*.sqlite`,
  `*.db`, `*.bak`, `*.tmp`, `*.log`, `.env*`, keys, `.htpasswd`, or `package*.json`
  inside the deployed tree.

---

## 3. How to run a public-readiness audit

Run these from the repo root before flipping the repo public. None of them
modify anything.

**a. Grep for secret patterns and local absolute paths.** The blocking
`local_path_leakage` gate already covers the _deployed_ bytes, but audit the
_whole repo_ (docs, tools, configs) before going public:

```sh
# local absolute paths (allow only intentional doc examples)
grep -rIn -E '/home/[a-z]+/|/var/www/|/var/lib/|Desktop/|htdocs/' \
  --exclude-dir=.git --exclude-dir=node_modules .

# secret-shaped material
grep -rIn -E 'BEGIN (OPENSSH|RSA|PGP|EC) PRIVATE KEY|service_account|BETTY_TOKEN|password\s*=|secret\s*=' \
  --exclude-dir=.git --exclude-dir=node_modules .
```

**b. Confirm `git status` is clean** (nothing staged/modified you did not
intend):

```sh
git status --short
```

**c. Confirm no tracked backup/scratch files slipped in:**

```sh
git ls-files | grep -E '\.(bak|orig|tmp)$'   # expect: no output
```

**d. Confirm release archives still verify** — sealed editions must remain
byte-identical to their baseline (the `frozen_archives_immutable` gate), and the
in-archive `verify.sh` must pass:

```sh
python3 tools/quality/gate.py --all          # includes frozen_archives_immutable + gpg
# plus, per the release archive's own check tool:
bash <release-archive>/verify.sh     # in-archive verifier, where present
```

**e. Scan the full git HISTORY, not just the working tree.** The gate and the
greps above see only the current checkout. A secret committed and later deleted
still lives in the git objects and is exposed the instant the repo goes public.

```sh
python3 tools/verify/scan_git_history.py    # advisory: secret/private-key/local-path tells across all history
```

Every finding must be triaged. A genuine leak (an exported private key, an
`auth.sqlite`, a `.totp_key`, a `config.local.php`) means the history is
**not** safe to publish as-is: rewrite it with `git filter-repo` / BFG, **and
treat any leaked key or credential as compromised — rotate it** (the published
fingerprint, the SFTP password, any token), because rewriting history does not
un-leak what was already pushed.

**f. Licence scan.** Confirm every redistributed third-party asset is licensed
for redistribution. Proprietary fonts (Klim Type Foundry `.woff2`) are
deliberately excluded from release archives and listed in each edition's
`EXCLUDED_FILES.json`; verify nothing new (images, snippets, vendored code) was
added without a compatible licence before flipping public.

---

## 4. Pre-public checklist

Tick every box before making the repository public:

- [ ] `git status` is clean — no unintended staged or modified files.
- [ ] `.gitignore` excludes all local/private state (§1, §2) and nothing private
      is tracked.
- [ ] No private keys or secrets are committed (`id_ed25519`, `*.asc` private
      keys, GCP service-account JSON, `.env*`, `config.local.php`,
      `.gate_credentials`).
- [ ] `python3 tools/verify/scan_git_history.py` is clean (or every finding triaged,
      history rewritten, and any leaked credential rotated).
- [ ] No local absolute paths (`/home/…`, server paths) in the repo _except_
      intentional documentation examples.
- [ ] No stale review packs or one-off migration scripts left behind.
- [ ] Docs reflect the current architecture (two-tier gate via `tools/quality/gate.py` +
      `tools/quality/lint.py`, drawing on the registry in `tools/lib/checks.py`
      and the inline checks in `tools/quality/inline_checks.py`).
- [ ] `README.md` is accurate.
- [ ] `bash tools/build/build.sh --check` runs.
- [ ] `python3 tools/quality/gate.py --all` passes (the full blocking gate).
- [ ] `python3 tools/quality/lint.py` is clean (advisory tier).
- [ ] Release verification works (`frozen_archives_immutable` + in-archive
      `verify.sh`).
- [ ] Retained generated files and historical archives are _intentional_ — not
      accidental leftovers.
- [ ] Score-ledger data and reports are not committed (local-only tooling).
- [ ] Security automation reviewed: Dependabot alerts and update PRs triaged,
      CodeQL has no unresolved high/critical alerts, latest OpenSSF Scorecard
      run reviewed in the Security tab (accepted low readings are documented
      in `GITHUB-RULESETS.md`).
- [ ] Deployment secrets are _documented but not exposed_ — `DEPLOYMENT.md`
      describes the SFTP/GPG/CI secret model; the secret values themselves live
      only in CI/host config.

---

## 5. Notes

- The `.gitignore` already encodes this policy; treat any _removal_ of an ignore
  rule as a security change and re-run the §3 audit.
- The deploy gate (`gate.py`) enforces the _public-bytes_ subset of this policy on
  every build (`repository_hygiene`, `local_path_leakage`,
  `hidden_and_archive_safety`, `frozen_archives_immutable`). This document covers
  the wider repo — docs, tooling, operator notes — that the gate does not scan.

---

## 6. The blocking `public_readiness` gate

Since the public release, `tools/quality/validate_public_readiness.py` runs in
the blocking tier on every build. Unlike its siblings it deliberately scopes to
the **repository root**, not `public/`: licence files present, README free of
private-repo claims, no tracked dependency trees or licensed binaries, the
font exclusions consistent with `metadata/repo-exclusions.json`, the internal
process records untracked. The release ceremony additionally demands a fresh,
clean full-history secret scan (`--full` mode). Declared facts live in
`tools/config/public-release.json`.
