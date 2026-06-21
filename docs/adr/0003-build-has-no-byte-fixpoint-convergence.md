# The build's stage-03 has no byte-fixpoint; do not add a convergence-loop driver

Stage 03 of `tools/build/build.sh` ("prepare public bytes") reaches its published
state by running the byte-mutating generators a **fixed number of times**
(`generate_sri` ×3, `generate_verification_map` ×3, `generate_integrity` ×2,
`generate_file_metadata` ×4, `generate_source_view`/`_reader`/`provenance` ×2),
not by looping to a stable tree. An architecture review proposed replacing the
hand-unrolled re-runs with a `converge.py` that loops "until the public-tree hash
stops changing". **We tried it and rejected it: there is no byte-fixpoint to loop
to.**

## Considered Options

A loop-until-stable driver was prototyped (`Proc` seam + a whole-tree content-hash
snapshot between passes). On the real tree it never converged — at 5 passes the
`/source/*` mirrors + `verification-data.js` were still moving; at 10 passes 70
files were still churning, driven by `inject_source_sha_footer`. The cause is
**interlocking circular dependencies with no joint byte-fixpoint**:

- `integrity.json` → `verification-data.js` (embeds per-file hashes) → the
  `?v=<hash>` query in every HTML `<script src>` → HTML bytes → `integrity.json`.
- `inject_source_sha_footer` writes a per-page source-sha into the footer → HTML
  bytes → the page's `/source/*.txt` mirror → the sha the footer reads.
- the `/source/*.txt` mirrors are copies of HTML that the SRI/footer/`?v=` sweeps
  keep changing, so the mirror chases the HTML by one pass forever.

The build does not *resolve* these to byte-stability. It runs each generator
enough times to make the cross-references **internally consistent for the
validators**, and `validate_source_mirrors` **canonicalizes the residual**
(strips SRI + footer-hash differences before its byte-equality check). The signed
`integrity.json` is correct because stage 04 hashes whatever the final tree is —
not because the tree stopped moving. "Convergence" here means *validator-coherent*,
not *byte-stable*.

A true-fixpoint driver would therefore either never terminate or demand
redesigning the footer/mirror/`verification-data` feedback to be genuinely
idempotent — a large, high-risk change to the signing path for no correctness
gain (the validators already enforce coherence).

## Consequences

The unrolled stage-03 sequence stays. Instead of chasing a fixpoint that does not
exist, the two real risks the review surfaced are addressed by **static checks**,
no re-running of generators:

- **`tools/build/assert_seal_immutable.py`** pins the publication rule that *no
  generator may mutate public bytes between the stage-04 seal and the stage-07
  signature* — it snapshots the tree at seal and re-asserts byte-identity just
  before signing, refusing to sign a moved tree.
- **`tools/quality/validate_sri_coherence.py`** statically verifies every
  `integrity="sha384-…"` attribute matches the hash of the asset it references —
  catching the "added a step after the SRI sweep ⇒ stale SRI" bug class directly,
  without a convergence loop. (`integrity_manifest_freshness` already covers
  manifest↔disk.)

Future architecture reviews (including `/improve-codebase-architecture`) should
not re-propose a byte-fixpoint convergence driver for stage 03 without first
removing the circular `footer`/`mirror`/`verification-data` dependencies.
