# Policy as data, enforcement as code (no OPA/Conftest/rego)

The public claim→control bindings live as declarative data
(`policy-data/claims-map.yml`, schema-validated), but the enforcement that
decides whether each claim is true stays executable Python
(`tools/verify/validate_claims_parity.py`). We deliberately did **not** adopt
OPA/Conftest/rego or a Node policy layer, even though the originating brief asked
for "policy as code" in that shape.

## Considered Options

A rule engine (OPA/rego) evaluates data that has already been collected. Here the
hard work _is_ the collection — running gpg, parsing `release.yml`, checking files
on disk — which rego cannot do. A rule engine would add a layer without removing
any work, and binding it would invite the "policy theatre" the brief itself warns
against. So bindings became data; evidence collection and evaluation stayed code.

## Consequences

This is why a reader finds no rego/Conftest despite the "policy as code" framing:
the split is intentional. New claims are added by editing the YAML ledger; new
_kinds_ of evidence are added by writing a `control_*` function. The generated
`docs/CLAIMS.md` and the `claims_map_drift` gate keep the human view honest.
