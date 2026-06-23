# trentpower.fr — local developer commands.
#
# thin wrappers over the existing pipeline entry points. no logic lives
# here: each target is the same command CI runs, so "green locally" means
# the same thing as "green in Actions". see docs/RELEASE.md.
#
# every runner is wrapped in the terminal ceremony (tools/quality/make-ui.sh):
# the trentpower.fr wordmark on top, then a summary panel — or a full per-file
# table with DETAIL=full (e.g. `make test DETAIL=full`, `make gate DETAIL=full`).

PY := python3
DETAIL ?= summary

# base ref the changed-line ratchet diffs against in `make preflight`/`diff-coverage`;
# override for a preprod-targeted branch: `make preflight PREFLIGHT_BASE=origin/preprod`.
PREFLIGHT_BASE ?= origin/main

UI = DETAIL="$(DETAIL)" PREFLIGHT_BASE="$(PREFLIGHT_BASE)" bash tools/quality/make-ui.sh

.PHONY: help doctor preflight test test-fast coverage diff-coverage gate lint verify release-check integrity sbom privacy-check provenance-check claims policy

help: ## list the available targets (DETAIL=full → per-file table on test/gate/lint/coverage)
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sort | \
		awk -F':.*## ' '{printf "  make %-14s %s\n", $$1, $$2}'

doctor: ## check the local environment (full / partial / archive / blocked)
	@$(UI) doctor

test: ## run the unit + property suite (DETAIL=full for a per-file table)
	@$(UI) test

test-fast: ## run the fast unit tier with the seam guard (DETAIL=full for a table)
	@$(UI) test-fast

coverage: ## run the suite under coverage + enforce the floors (DETAIL=full for per-file)
	@$(UI) coverage

diff-coverage: ## gate coverage of changed lines vs PREFLIGHT_BASE (needs a prior `make coverage`)
	@$(UI) diff-coverage

preflight: ## run every locally-runnable CI check in order (green here ⇒ green in CI)
	@$(UI) preflight

gate: ## run the deploy-blocking gate (DETAIL=full for the full check table)
	@$(UI) gate

lint: ## run the advisory quality/editorial checks (DETAIL=full for the full table)
	@$(UI) lint

verify: ## run the full release gate + signature verification
	@$(UI) verify

privacy-check: ## run the privacy gates (storage keys, runtime contamination, trusted types)
	@$(UI) privacy-check

provenance-check: ## confirm every public supply-chain claim maps to a passing control
	@$(UI) provenance-check

claims: ## regenerate docs/CLAIMS.md from claims-map.yml, then run the parity gate
	@$(UI) claims

policy: ## run every public-promise gate (privacy + provenance + claims ledger)
	$(MAKE) privacy-check
	$(MAKE) provenance-check
	$(MAKE) claims

release-check: ## re-render from source and assert no drift (reproducibility)
	@$(UI) release-check

integrity: ## regenerate the public integrity manifest
	@$(UI) integrity

sbom: ## generate a CycloneDX SBOM of the build toolchain
	$(PY) -m cyclonedx_py requirements .github/requirements/build-check.txt \
		--output-reproducible --of JSON -o sbom.cdx.json
