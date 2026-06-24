#!/usr/bin/env python3
"""checks.py -- single registry of every deploy check, classified by severity.

The check *logic* lives elsewhere and is not duplicated here:
  - inline cross-cutting checks are functions in inline_checks.py
  - everything else is a validate_*.py sub-script under tools/

This module only declares, for each check, its id, human label, tier
(blocking vs advisory), category (SEC / COR / QUAL) and a one-line rationale,
in the original gate order. Two entry points consume the registry:

  tools/gate.py  runs Tier.BLOCKING  (deploy-blocking security + correctness)
  tools/lint.py  runs Tier.ADVISORY  (quality / editorial; never blocks deploy)

The blocking set preserves every security and correctness check the old
single mixed gate enforced (inline functions from inline_checks.py included);
only quality/editorial lint is demoted to advisory.
"""

from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum

sys.path.insert(
    0,
    str(
        next(
            _a
            for _a in __import__("pathlib").Path(__file__).resolve().parents
            if _a.name == "tools"
        )
        / "lib"
    ),
)
from paths import TOOLS_DIR as SCRIPTS  # noqa: E402

# the check registry reaches scripts across every responsibility pillar.
_PILLARS = ("build", "quality", "verify", "release", "badges", "lib")
for _sub in _PILLARS:
    sys.path.insert(0, str(SCRIPTS / _sub))
import inline_checks as pdc  # noqa: E402  (inline cross-cutting check functions)


class Tier(str, Enum):  # noqa: UP042
    BLOCKING = "blocking"
    ADVISORY = "advisory"


class Category(str, Enum):  # noqa: UP042
    SECURITY = "SEC"
    CORRECTNESS = "COR"
    QUALITY = "QUAL"


@dataclass(frozen=True)
class Check:
    id: str
    label: str
    tier: Tier
    category: Category
    rationale: str
    function: Callable[[], int] | None = None
    command: Sequence[str] | None = None
    # True for checks that depend on a fresh detached signature being present
    # (gpg verify, integrity.json.sig freshness). the pre-signing Publication
    # review pass omits exactly these; gate.py derives that set from this flag
    # via signature_check_ids() rather than hardcoding ids it cannot see drift in.
    requires_signature: bool = False


def _script(name: str, *args: str) -> list[str]:
    # validators and generators now live under responsibility pillars; resolve
    # a bare script name to whichever pillar holds it.
    for _sub in _PILLARS:
        cand = SCRIPTS / _sub / name
        if cand.exists():
            return [sys.executable, str(cand), *args]
    return [sys.executable, str(SCRIPTS / name), *args]


@dataclass(frozen=True)
class CheckResult:
    """One captured check outcome, ready to serialize into a report.

    Mirrors the per-check entry shape documented in
    docs/GATES-CHECKS-AND-QUALITY.md §5. ``affected_files`` ships empty for now --
    populating it needs validators to emit structured file lists (deferred).
    """

    id: str
    label: str
    tier: str
    category: str
    status: str  # "passed" | "failed"
    duration_ms: int
    rationale: str
    stdout: str = ""
    stderr: str = ""
    affected_files: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "tier": self.tier,
            "category": self.category,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "rationale": self.rationale,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "affected_files": list(self.affected_files),
        }


def run_check_captured(c: Check) -> CheckResult:
    """Execute one check, capturing its output and wall-clock duration.

    Nothing is streamed to the terminal -- the output is captured into the
    CheckResult so a caller can render it or fold it into a machine-readable
    report. ``command`` checks capture subprocess stdout/stderr; ``function``
    checks (the inline pdc.* ones that print) capture stdout via redirect_stdout.
    This is the only per-check executor; run_registry drives it in a loop.
    """
    start = time.monotonic()
    stdout = ""
    stderr = ""
    if c.function is not None:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = c.function()
        stdout = buf.getvalue()
    elif c.command is not None:
        proc = subprocess.run(list(c.command), cwd=pdc.ROOT, capture_output=True, text=True)
        rc = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr
    else:
        rc = 1
        stderr = f"check {c.id} has neither function nor command"
    duration_ms = int((time.monotonic() - start) * 1000)
    return CheckResult(
        id=c.id,
        label=c.label,
        tier=c.tier.value,
        category=c.category.value,
        status="passed" if rc == 0 else "failed",
        duration_ms=duration_ms,
        rationale=c.rationale,
        stdout=stdout,
        stderr=stderr,
    )


def run_registry(
    checks: list[Check],
    *,
    on_result: Callable[[int, int, CheckResult], None] | None = None,
    stop_on_fail: bool = False,
) -> list[CheckResult]:
    """Run a list of checks captured, in order, returning their CheckResults.

    The single loop gate.py and lint.py both share. Each check runs through
    run_check_captured (captured, never streamed); on_result(done, total, result)
    fires after each so a caller can render a live line/mark; stop_on_fail breaks
    after the first failure (gate's fail-fast default). Pure of presentation — it
    prints nothing and writes nothing, so it is unit-tested with synthetic Checks.
    """
    total = len(checks)
    results: list[CheckResult] = []
    for i, c in enumerate(checks, 1):
        r = run_check_captured(c)
        results.append(r)
        if on_result is not None:
            on_result(i, total, r)
        if stop_on_fail and r.status != "passed":
            break
    return results


def progress_line(done: int, total: int, result: CheckResult) -> str:
    """The one-line per-check render gate + lint print as a run streams."""
    mark = "OK" if result.status == "passed" else "X"
    return f"[{done}/{total}] {mark} {result.category} {result.label}"


# shorthands.
_B, _A = Tier.BLOCKING, Tier.ADVISORY
_SEC, _COR, _QUAL = Category.SECURITY, Category.CORRECTNESS, Category.QUALITY

# the registry, in the old single gate's original order. blocking checks run
# in this order in gate.py (preserving any implicit "earlier passed" assumptions).
REGISTRY: list[Check] = [
    Check(
        "edition",
        "validate_edition.py",
        _B,
        _COR,
        "no stale edition reference anywhere on the site",
        command=_script("validate_edition.py"),
    ),
    Check(
        "repository_hygiene",
        "validate_repository_hygiene.py (forbidden-artefact gate)",
        _B,
        _SEC,
        "no keys / .env / hidden / stale generated artefacts ship",
        command=_script("validate_repository_hygiene.py"),
    ),
    Check(
        "public_readiness",
        "validate_public_readiness.py (public-repo posture gate)",
        _B,
        _SEC,
        "public-repo posture holds: licences present, no private-claim drift, "
        "no tracked secrets or licensed binaries",
        command=_script("validate_public_readiness.py"),
    ),
    Check(
        "source_mirrors",
        "validate_source_mirrors.py",
        _B,
        _SEC,
        "every /source/ mirror byte-matches the live file it claims to mirror",
        command=_script("validate_source_mirrors.py"),
    ),
    Check(
        "file_sizes",
        "validate_file_sizes.py",
        _B,
        _COR,
        "recorded file sizes match disk (convergence honesty)",
        command=_script("validate_file_sizes.py"),
    ),
    Check(
        "dates",
        "validate_dates.py",
        _B,
        _COR,
        "no date drift across sitemap / json-ld / manifest / metadata",
        command=_script("validate_dates.py"),
    ),
    Check(
        "gpg",
        "gpg --verify integrity.json.sig integrity.json",
        _B,
        _SEC,
        "signature verifies against the published key in a clean temp keyring",
        function=pdc.check_gpg,
        requires_signature=True,
    ),
    Check(
        "integrity_manifest_freshness",
        "integrity manifest freshness",
        _B,
        _SEC,
        "every active public file is recorded in integrity.json with a matching hash",
        command=_script("validate_integrity_manifest.py"),
    ),
    Check(
        "integrity_sig_freshness",
        "integrity.json.sig freshness",
        _B,
        _SEC,
        "signature is not stale relative to the manifest it signs",
        command=_script("validate_integrity_sig.py"),
        requires_signature=True,
    ),
    Check(
        "verification_map_dates",
        "verification-map date freshness",
        _B,
        _COR,
        "every Verify record is validated today (UTC)",
        command=_script("validate_verification_map_dates.py"),
    ),
    Check(
        "verification_data_shape",
        "validate_verification_data.py",
        _B,
        _COR,
        "every Verify record is shaped, bounded and path-safe (allowlist firewall)",
        command=_script("validate_verification_data.py"),
    ),
    Check(
        "asset_version_coherence",
        "ASSET_VERSION coherence (HTML + sw.js + on-disk bundle)",
        _B,
        _COR,
        "asset version agrees across HTML, sw.js and the recomputed bundle hash",
        command=_script("validate_asset_version.py"),
    ),
    Check(
        "sri_coherence",
        "SRI coherence (integrity attrs vs referenced assets)",
        _B,
        _SEC,
        "every integrity sha384 attribute matches the hash of the asset it covers",
        command=_script("validate_sri_coherence.py"),
    ),
    Check(
        "no_dated_assets",
        "validate_no_dated_assets.py",
        _B,
        _COR,
        "clean asset filenames only; cache-busting lives in ?v=, not the name",
        command=_script("validate_no_dated_assets.py"),
    ),
    Check(
        "sw_precache",
        "service-worker precache resolves",
        _B,
        _COR,
        "every sw.js precache URL maps to a real file of a valid type",
        command=_script("validate_sw_precache.py"),
    ),
    Check(
        "local_path_leakage",
        "local-path leakage scan",
        _B,
        _SEC,
        "no /home/, Desktop/, htdocs/htdocs or server paths leak into public bytes",
        command=_script("validate_local_path_leakage.py"),
    ),
    Check(
        "hidden_and_archive_safety",
        "hidden artefact + archive content safety",
        _B,
        _SEC,
        "no hidden artefacts/keys; release ZIP free of fonts and stale stylesheets",
        command=_script("validate_hidden_artefacts.py"),
    ),
    Check(
        "frozen_archives_immutable",
        "frozen-archive immutability",
        _B,
        _SEC,
        "sealed release archives are byte-identical to their baseline",
        function=pdc.check_frozen_archives_immutable,
    ),
    Check(
        "archive_storage_policy",
        "archive storage policy (server-canonical)",
        _B,
        _SEC,
        "no archive binaries committed to git — historical archives live on the server",
        command=_script("validate_archive_storage_policy.py"),
    ),
    Check(
        "images",
        "validate_images.py",
        _B,
        _COR,
        "declared images exist with valid dimensions/formats",
        command=_script("validate_images.py"),
    ),
    Check(
        "no_orphan_images",
        "validate_no_orphan_images.py",
        _A,
        _QUAL,
        "no unreferenced images shipped",
        command=_script("validate_no_orphan_images.py"),
    ),
    Check(
        "signing_status",
        "validate_signing_status.py",
        _B,
        _SEC,
        "the site's 'signed' trust claims match reality",
        command=_script("validate_signing_status.py"),
    ),
    Check(
        "claims_parity",
        "validate_claims_parity.py",
        _B,
        _SEC,
        "every public SLSA/Sigstore/Rekor/PGP/SBOM claim maps to a passing automated control",
        command=_script("validate_claims_parity.py"),
    ),
    Check(
        "claims_map_drift",
        "generate_claims_md.py --check (drift gate)",
        _B,
        _COR,
        "generated docs/CLAIMS.md has no drift from policy-data/claims-map.yml",
        command=_script("generate_claims_md.py", "--check"),
    ),
    Check(
        "site_metadata",
        "validate_site_metadata.py",
        _B,
        _COR,
        "canonical site-metadata schema is well-formed",
        command=_script("validate_site_metadata.py"),
    ),
    Check(
        "archive_text_casing",
        "validate_archive_text_casing.py",
        _A,
        _QUAL,
        "ZIP orientation/casing convention",
        command=_script("validate_archive_text_casing.py"),
    ),
    Check(
        "language_consistency",
        "validate_language_consistency.py",
        _A,
        _QUAL,
        "authorship-language consistency",
        command=_script("validate_language_consistency.py"),
    ),
    Check(
        "git_metadata",
        "validate_git_metadata.py",
        _B,
        _SEC,
        "no AI/attribution trailers; git metadata policy holds",
        command=_script("validate_git_metadata.py"),
    ),
    Check(
        "trusted_types",
        "validate_trusted_types.py",
        _B,
        _SEC,
        "Trusted Types / CSP posture holds (XSS hardening)",
        command=_script("validate_trusted_types.py"),
    ),
    Check(
        "schema_graph",
        "validate_schema_graph.py",
        _A,
        _QUAL,
        "JSON-LD @graph coherence (SEO/GEO). NOTE: broken JSON-LD should be promoted to "
        "blocking when this merges into validate_html in PR3",
        command=_script("validate_schema_graph.py"),
    ),
    Check(
        "lighthouse_invariants",
        "validate_lighthouse_invariants.py",
        _A,
        _QUAL,
        "static invariants protecting the Lighthouse score",
        command=_script("validate_lighthouse_invariants.py"),
    ),
    Check(
        "fonts",
        "validate_fonts.py",
        _B,
        _COR,
        "declared fonts exist",
        command=_script("validate_fonts.py"),
    ),
    Check(
        "public_comment_hygiene",
        "validate_public_comment_hygiene.py",
        _A,
        _QUAL,
        "no machinery references in deployed comments. NOTE: if it asserts any hard secret-leak "
        "rule, split that assertion back to blocking in PR3",
        command=_script("validate_public_comment_hygiene.py"),
    ),
    Check(
        "source_mirror_readability",
        "validate_source_mirror_readability.py",
        _A,
        _QUAL,
        "/source/ assets are served as readable text (byte-match itself is blocking, above)",
        command=_script("validate_source_mirror_readability.py"),
    ),
    Check(
        "no_runtime_contamination",
        "validate_no_runtime_contamination.py",
        _B,
        _SEC,
        "no third-party runtime / network calls injected",
        command=_script("validate_no_runtime_contamination.py"),
    ),
    Check(
        "storage_keys",
        "validate_storage_keys.py",
        _B,
        _SEC,
        "every browser-storage key in the live surface is on the documented "
        "local.js allowlist (no undeclared localStorage/sessionStorage keys)",
        command=_script("validate_storage_keys.py"),
    ),
    Check(
        "html_correctness",
        "validate_html_correctness.py",
        _B,
        _COR,
        "no structural HTML defects (parse-clean)",
        command=_script("validate_html_correctness.py"),
    ),
    Check(
        "css_architecture",
        "validate_css_architecture.py",
        _A,
        _QUAL,
        "cascade-layer contract (@layer rules, !important budget)",
        command=_script("validate_css_architecture.py"),
    ),
    Check(
        "nav_regression",
        "validate_nav_regression.py",
        _A,
        _QUAL,
        "masthead-only header shape didn't regress",
        command=_script("validate_nav_regression.py"),
    ),
    Check(
        "home_anchors",
        "validate_home_anchors.py",
        _A,
        _QUAL,
        "homepage anchor model intact",
        command=_script("validate_home_anchors.py"),
    ),
    Check(
        "bilingual_html",
        "validate_bilingual_html.py",
        _B,
        _COR,
        "per-page lang/canonical/hreflang + no runtime-i18n residue",
        command=_script("validate_bilingual_html.py"),
    ),
    Check(
        "page_provenance",
        "validate_page_provenance.py",
        _B,
        _COR,
        "every active page carries one coherent provenance record "
        "(tp-page-record + comment), no local-path leaks",
        command=_script("validate_page_provenance.py"),
    ),
    Check(
        "translation_state",
        "validate_translation_state.py",
        _A,
        _QUAL,
        "every content/fr/ page declares translation freshness",
        command=_script("validate_translation_state.py"),
    ),
    Check(
        "lowercase_comments",
        "validate_lowercase_comments.py",
        _A,
        _QUAL,
        "CSS/source comment prose is lowercase",
        command=_script("validate_lowercase_comments.py"),
    ),
    Check(
        "lang_gate",
        "validate_lang_gate.py",
        _B,
        _COR,
        "the / language vestibule is static, self-canonical, no auto-redirect",
        command=_script("validate_lang_gate.py"),
    ),
    Check(
        "public_exposure",
        "validate_public_exposure.py",
        _B,
        _SEC,
        "the public-exposure allow-list covers exactly the real public routes",
        command=_script("validate_public_exposure.py"),
    ),
    Check(
        "htaccess_allowlist",
        "validate_htaccess_allowlist.py",
        _B,
        _SEC,
        "simulate the .htaccess rewrite gate -- only intended URLs are reachable",
        command=_script("validate_htaccess_allowlist.py"),
    ),
    Check(
        "htaccess_drift",
        "generate_htaccess.py --check (drift gate)",
        _B,
        _SEC,
        "generated .htaccess regions have no uncommitted drift",
        command=_script("generate_htaccess.py", "--check"),
    ),
    Check(
        "htaccess_audit",
        "audit_htaccess.py",
        _B,
        _SEC,
        "focused .htaccess + CSP-freshness audit",
        command=_script("audit_htaccess.py"),
    ),
    Check(
        "deny_parity",
        "validate_deny_parity.py",
        _B,
        _SEC,
        "the .htaccess and manifest denied-extension lists agree (no silent drift)",
        command=_script("validate_deny_parity.py"),
    ),
    Check(
        "changelog_freshness",
        "changelog freshness",
        _B,
        _COR,
        "edition is not newer than the topmost changelog entry",
        command=_script("validate_changelog.py"),
    ),
    Check(
        "routes_json_drift",
        "generate_routes_json.py --check (drift gate)",
        _B,
        _COR,
        "generated content/routes.json has no drift from routes.yml",
        command=_script("generate_routes_json.py", "--check"),
    ),
    Check(
        "content_schemas",
        "validate_content_schemas.py",
        _B,
        _COR,
        "content validates against its schema and routes.json references resolve",
        command=_script("validate_content_schemas.py"),
    ),
    Check(
        "documentation",
        "validate_documentation.py",
        _B,
        _SEC,
        "published /documentation/ pdf is layout-clean, free of corrected stale "
        "claims, and the landing page advertises its real hash",
        command=_script("validate_documentation.py"),
    ),
    Check(
        "local_badges",
        "validate_badges.py",
        _B,
        _COR,
        "trust-mark SVGs are fresh against badges.json, self-contained, and no "
        "governance file references an external badge service",
        command=_script("validate_badges.py"),
    ),
    Check(
        "docs_freshness",
        "validate_docs_freshness.py",
        _B,
        _COR,
        "documentation source makes no stale machine-checkable claim — repo-path "
        "references resolve, the coverage figure is in lock-step, canonical "
        "commands match metadata/docs/commands.json, the score-ledger exclusion "
        "is stated positively",
        command=_script("validate_docs_freshness.py"),
    ),
    Check(
        "docs_links",
        "validate_docs_links.py",
        _B,
        _COR,
        "every relative link and embedded image in the tracked markdown resolves "
        "to a file that ships",
        command=_script("validate_docs_links.py"),
    ),
]


def blocking() -> list[Check]:
    return [c for c in REGISTRY if c.tier is Tier.BLOCKING]


def advisory() -> list[Check]:
    return [c for c in REGISTRY if c.tier is Tier.ADVISORY]


# ── registry queries ────────────────────────────────────────────────────────
# the registry is the single source of truth for what a check IS — its tier and
# whether it depends on a fresh signature. consumers ask through these functions
# instead of re-deriving the facts by parsing this file's source text
# (validate_claims_parity once regex-matched `Check("gpg", …, _B)`; gate.py once
# hardcoded the signature-skip ids). small surface on purpose.
_BY_ID = {c.id: c for c in REGISTRY}


def is_blocking(check_id: str) -> bool:
    """Whether a check with this id is registered in the BLOCKING tier. A missing
    id returns False, so a check that was removed or renamed fails any meta-check
    that asserts it must be blocking."""
    c = _BY_ID.get(check_id)
    return c is not None and c.tier is Tier.BLOCKING


def signature_check_ids() -> tuple[str, ...]:
    """Ids of the checks that depend on a fresh detached signature — the set the
    pre-signing Publication Review pass omits. Derived from the registry, in
    registry order, so a new signature-dependent check is covered by flagging it,
    not by editing a second list in gate.py."""
    return tuple(c.id for c in REGISTRY if c.requires_signature)
