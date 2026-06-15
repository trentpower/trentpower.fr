# trentpower.fr — local developer commands.
#
# thin wrappers over the existing pipeline entry points. no logic lives
# here: each target is the same command CI runs, so "green locally" means
# the same thing as "green in Actions". see docs/RELEASE.md.

PY := python3

.PHONY: help test gate lint verify release-check integrity sbom privacy-check provenance-check

help: ## list the available targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sort | \
		awk -F':.*## ' '{printf "  make %-14s %s\n", $$1, $$2}'

test: ## run the unit + property (hypothesis) test suite
	$(PY) -m unittest discover -s tools/quality/tests -p 'test_*.py' -v

gate: ## run the deploy-blocking gate (security + correctness checks)
	$(PY) tools/quality/gate.py

lint: ## run the advisory quality/editorial checks (never blocks deploy)
	$(PY) tools/quality/lint.py

verify: ## run the full release gate + signature verification
	$(PY) tools/verify/validate_release.py

privacy-check: ## run the privacy gates (storage keys, runtime contamination, trusted types)
	$(PY) tools/quality/validate_storage_keys.py
	$(PY) tools/quality/validate_no_runtime_contamination.py
	$(PY) tools/quality/validate_trusted_types.py

provenance-check: ## confirm every public supply-chain claim maps to a passing control
	$(PY) tools/verify/validate_claims_parity.py

release-check: ## re-render from source and assert no drift (reproducibility)
	bash tools/build/build.sh --check

integrity: ## regenerate the public integrity manifest
	$(PY) tools/build/generate_integrity.py

sbom: ## generate a CycloneDX SBOM of the build toolchain
	$(PY) -m cyclonedx_py requirements .github/requirements/build-check.txt \
		--output-reproducible --of JSON -o sbom.cdx.json
