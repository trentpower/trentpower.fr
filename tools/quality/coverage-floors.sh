# shellcheck shell=bash
# shellcheck disable=SC2034  # these vars are consumed by the scripts that SOURCE this file
# coverage-floors.sh — the SINGLE source of truth for the three coverage-surface
# floors. Sourced by coverage.sh (the enforcer) and build.sh (the ceremony), and
# written into .build/coverage/coverage-summary.json so tools/badges/sync_coverage.py
# can keep the floor numbers advertised in the docs in lock-step. The numbers live
# in exactly ONE place — raise them here as coverage climbs; never lower.
#
# Pure variable definitions: no side effects, safe to source anywhere.
# (measured ~97.7 / ~97.3 / ~96.0, so each keeps margin above its 95 floor)
SEAL_MIN=95  # convergence + seal — signing-critical
ADR_MIN=95   # ADR-0002 validators
BROAD_MIN=95 # broad quality-policy
