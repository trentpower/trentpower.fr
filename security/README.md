# Security artefacts

Machine-readable security posture for the repository. These files are part of the
source repository, not the published site, and are never deployed to the host.

## `openvex.json` — the VEX

An [OpenVEX](https://openvex.dev) document recording the exploitability of
vulnerabilities that the dependency (SCA) scanner flags in the project's
dependencies. Its purpose: when a known CVE appears in a pinned dependency but
cannot affect a static publication with no runtime, that fact is stated here with a
reason, rather than left implicit.

`statements` is empty when no flagged vulnerability is currently being suppressed.
Each suppression added to [`osv-scanner.toml`](../osv-scanner.toml) has a matching
statement here, so nothing is ignored silently.

### Adding a statement

When the `sca` job ([../.github/workflows/pr-checks.yml](../.github/workflows/pr-checks.yml))
flags a vulnerability that does not affect the published bytes, add a statement:

```json
{
  "vulnerability": { "name": "CVE-YYYY-NNNNN" },
  "products": [{ "@id": "pkg:pypi/example@1.2.3" }],
  "status": "not_affected",
  "justification": "vulnerable_code_not_in_execute_path",
  "impact_statement": "Build-time only tool; not present in the published static site, which has no runtime."
}
```

Bump the document `version`, update the `timestamp`, and add the matching ignore
entry to `osv-scanner.toml`. Remediation thresholds and the suppression policy live
in [../docs/SECURITY-AND-PRIVACY.md](../docs/SECURITY-AND-PRIVACY.md) (Dependency
security).
