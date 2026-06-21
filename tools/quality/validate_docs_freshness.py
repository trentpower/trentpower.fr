#!/usr/bin/env python3
"""validate_docs_freshness.py — make documentation freshness build-blocking.

trentpower.fr makes machine-checkable public claims (coverage %, badges, gates,
signing, integrity, byte convergence). Several are already gated against the
artifacts they describe: sync_coverage.py (the coverage figure + suite size),
validate_badges.py (badge SVG drift), validate_documentation.py (the rendered
public /documentation/ PDF). What nothing checked was the docs/*.md SOURCE — its
references to repo paths, the blessed command invocations it prints, and the
score-ledger exclusion it asserts. A rename or a stale claim in the markdown could
ship silently. This validator closes that gap.

Principle: if a document makes a machine-checkable claim, the pipeline checks it.

Checks (FAIL blocks the build, WARN is advisory):
  1. required docs exist                                              FAIL
  2. backticked repo-path references resolve to a tracked path       FAIL
  3. banned stale phrases (with a per-line <!-- stale-ok --> escape) FAIL
  4. commands.json paths exist; canonical-commands blocks match it   FAIL
  5. published coverage figure is in lock-step (skip-if-unmeasured)  FAIL / WARN
  6. score-ledger exclusion is a positive, cross-referenced claim    FAIL
  7. README.pdf source→PDF render proof is current                   WARN
  8. docs do not frame the pre-ADR-0002 one-big-main() shape as good WARN

Shape (deep module, ADR-0002). The interface is `main() -> int` plus the
OK/WARN/ERROR text contract. The environment is injected through three seams —
`Repo(root)` for the filesystem, `tracked` (the git-tracked file set) for "does
this path ship", and `coverage_probe` for the measured-coverage reading — so the
whole gate runs through `evaluate(repo, ctx, tracked, coverage_probe) -> Result`
over a fixture repo with no git, no .build tree and no monkeypatching. `load()`
reads the policy data; `evaluate()` is pure compute; `main()` is the only
side-effecting adapter (git, stdout, exit code).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(
    0,
    str(next(_a for _a in Path(__file__).resolve().parents if _a.name == "tools") / "lib"),
)
from paths import REPO_ROOT  # noqa: E402
from repo import Repo  # noqa: E402  (shared filesystem evidence seam)

import render_proof  # noqa: E402  (sibling — single source of the render-proof hashes)

# repo-relative policy data.
INVENTORY_REL = "metadata/docs/docs_inventory.json"
COMMANDS_REL = "metadata/docs/commands.json"

# only path references under these roots are existence-checked; everything else
# (CHANGELOG.md, .coveragerc, prose nouns) is out of scope by design.
ALLOWLIST_ROOTS = ("tools/", "docs/", "metadata/", ".github/", "public/")

# banned stale phrases (normalised: lower-cased, runs of whitespace collapsed).
# a doc that must quote one to negate it ends that line with <!-- stale-ok -->.
STALE_PHRASES = (
    "policy coverage",
    "quality coverage",
    "reports/coverage/",
    "tests/coverage live route",
    "hand-set coverage",
    "coverage is advisory",
)
STALE_OK = "<!-- stale-ok -->"

# the score-ledger exclusion must be stated POSITIVELY (an affirmative
# "removed/moved" is caught by the stale-phrase / link checks instead).
LEDGER_DECISION_RE = re.compile(r"(remains|stays|retained|kept)\s+in\s+(this|the)\s+reposit", re.I)

CANONICAL_MARKER = "<!-- canonical-commands -->"
FENCE_RE = re.compile(r"^(```|~~~)")
# a backticked inline token, single line (multi-line ``` fences never match).
BACKTICK_RE = re.compile(r"`([^`\n]+)`")
INLINE_COMMENT_RE = re.compile(r"\s+#.*$")

# language that frames the pre-ADR-0002 "one big main()" script shape as the
# preferred pattern. advisory — drift, not breakage.
ADR_LANG_RE = re.compile(r"\bone\s+big\s+main\b|\bmonolithic\s+main\b", re.I)


# ---------------------------------------------------------------------------
# Ctx / Result — the values that flow through the interface.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Ctx:
    inventory: dict
    commands: dict


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    warns: list[str] = field(default_factory=list)
    oks: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fails


# ---------------------------------------------------------------------------
# small pure helpers.
# ---------------------------------------------------------------------------
def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower()


def _command_values(commands: dict) -> list[str]:
    """the blessed invocations — every value except documentation (`_`) keys."""
    return [v for k, v in commands.items() if not k.startswith("_")]


def _strip_inline_comment(line: str) -> str:
    return INLINE_COMMENT_RE.sub("", line).strip()


def _path_tokens(value: str) -> list[str]:
    """allowlisted-root path tokens inside a string (a command or a sentence)."""
    out = []
    for tok in re.split(r"\s+", value):
        tok = tok.strip("`'\"").split("#")[0]
        if tok.startswith(ALLOWLIST_ROOTS):
            out.append(tok)
    return out


def _is_checkable_path(tok: str) -> bool:
    if not tok.startswith(ALLOWLIST_ROOTS):
        return False
    if tok.endswith("/"):  # a directory reference — not a tracked file
        return False
    if tok.startswith(".build/") or "/.build/" in tok:
        return False
    return not any(c in tok for c in "<>*?[]")


def _path_ships(tok: str, tracked: set[str]) -> bool:
    if tok in tracked:
        return True
    pref = tok.rstrip("/") + "/"  # a tracked directory
    return any(t.startswith(pref) for t in tracked)


def _fenced_blocks(text: str, marker_only: bool) -> list[list[str]]:
    """return the line-lists of fenced code blocks. if marker_only, only blocks
    immediately preceded (ignoring blanks) by the canonical-commands marker."""
    lines = text.split("\n")
    blocks: list[list[str]] = []
    i = 0
    last_nonblank = ""
    while i < len(lines):
        if FENCE_RE.match(lines[i].lstrip()):
            body: list[str] = []
            i += 1
            while i < len(lines) and not FENCE_RE.match(lines[i].lstrip()):
                body.append(lines[i])
                i += 1
            if not marker_only or last_nonblank.strip() == CANONICAL_MARKER:
                blocks.append(body)
            last_nonblank = "```"
            i += 1
            continue
        if lines[i].strip():
            last_nonblank = lines[i]
        i += 1
    return blocks


# ---------------------------------------------------------------------------
# checks — accumulate findings into the Result.
# ---------------------------------------------------------------------------
def check_required(repo: Repo, ctx: Ctx, r: Result) -> None:
    missing = [d for d in ctx.inventory.get("required", []) if not repo.is_file(d)]
    for d in missing:
        r.fails.append(f"required doc missing: {d}")
    if not missing:
        r.oks.append(f"required docs: {len(ctx.inventory.get('required', []))} present")


def check_tracked_paths(repo: Repo, md_files: list[str], tracked: set[str], r: Result) -> None:
    checked = 0
    for rel in md_files:
        text = repo.read(rel)
        for m in BACKTICK_RE.finditer(text):
            # a backtick span may be a bare path or a full command (`script.sh
            # --flag`); the path candidate is its first whitespace-delimited word.
            tok = m.group(1).strip().split()[0] if m.group(1).strip() else ""
            tok = tok.split("#")[0]
            if not _is_checkable_path(tok):
                continue
            checked += 1
            if not _path_ships(tok, tracked):
                line = text.count("\n", 0, m.start()) + 1
                r.fails.append(f"{rel}:{line} references `{tok}` — not a tracked path")
    r.oks.append(f"path references: {checked} backticked repo-paths resolve")


def check_stale_phrases(repo: Repo, md_files: list[str], r: Result) -> None:
    hits = 0
    for rel in md_files:
        for n, line in enumerate(repo.read(rel).split("\n"), 1):
            if line.rstrip().endswith(STALE_OK):
                continue
            norm = _norm(line)
            for ph in STALE_PHRASES:
                if ph in norm:
                    r.fails.append(f"{rel}:{n} stale phrase '{ph}' (add {STALE_OK} if intentional)")
                    hits += 1
    if hits == 0:
        r.oks.append("no banned stale phrases")


def check_commands(repo: Repo, ctx: Ctx, md_files: list[str], tracked: set[str], r: Result) -> None:
    values = _command_values(ctx.commands)
    if not values:
        r.fails.append(f"{COMMANDS_REL}: no canonical commands defined")
        return
    # (a) every canonical command's path tokens must ship.
    for v in values:
        for tok in _path_tokens(v):
            if _is_checkable_path(tok) and not _path_ships(tok, tracked):
                r.fails.append(f"{COMMANDS_REL}: command '{v}' references missing path `{tok}`")
    # (b) every line inside a canonical-commands block must be a blessed value.
    blessed = set(values)
    blocks = 0
    for rel in md_files:
        for body in _fenced_blocks(repo.read(rel), marker_only=True):
            blocks += 1
            for raw in body:
                cmd = _strip_inline_comment(raw)
                if not cmd or cmd.startswith("#"):
                    continue
                if cmd not in blessed:
                    r.fails.append(
                        f"{rel}: canonical-commands block has '{cmd}' "
                        f"— not a {COMMANDS_REL} value"
                    )
    r.oks.append(f"commands: {len(values)} canonical paths resolve, {blocks} marked block(s)")


def check_coverage(
    ctx: Ctx, coverage_probe: Callable[[], tuple[bool, list[str]]], r: Result
) -> None:
    flags = ctx.inventory.get("flags", {})
    if not any("coverage_critical" in v for v in flags.values()):
        return
    measured, drift = coverage_probe()
    if not measured:
        r.warns.append("coverage not measured this run — figure freshness not re-checked")
        return
    if drift:
        for d in drift:
            r.fails.append(f"coverage drift: {d}")
    else:
        r.oks.append("published coverage figure in lock-step with the measurement")


def check_score_ledger(repo: Repo, ctx: Ctx, r: Result) -> None:
    flags = ctx.inventory.get("flags", {})
    authority = [d for d, fs in flags.items() if "score_ledger_authority" in fs]
    if not authority:
        return
    # the authority doc must STATE the retention decision positively.
    ledger = next((d for d in authority if d.endswith("SCORE-LEDGER.md")), None)
    if ledger:
        if LEDGER_DECISION_RE.search(repo.read(ledger)):
            r.oks.append(f"{ledger}: states the retention decision positively")
        else:
            r.fails.append(
                f"{ledger}: missing a positive retention statement "
                "(e.g. 'remains in this repository')"
            )
    # the coverage doc must cross-reference the ledger doc.
    cov = next((d for d in authority if d.endswith("COVERAGE.md")), None)
    if cov and "SCORE-LEDGER.md" not in repo.read(cov):
        r.fails.append(f"{cov}: does not cross-reference SCORE-LEDGER.md")


def check_render_proof(repo: Repo, r: Result) -> None:
    proof_rel = render_proof.PROOF_REL
    if not repo.is_file(proof_rel):
        r.warns.append(f"{proof_rel} missing — run `python3 tools/quality/render_proof.py`")
        return
    try:
        recorded = json.loads(repo.read(proof_rel))
    except json.JSONDecodeError as e:
        r.warns.append(f"{proof_rel}: invalid JSON ({e})")
        return
    current = render_proof.compute(repo.root)
    diffs = [k for k in current if recorded.get(k) != current[k]]
    if diffs:
        r.warns.append(
            f"README.pdf render proof stale ({', '.join(diffs)}) — re-render and "
            "re-run render_proof.py if the PDF should reflect the source change"
        )
    else:
        r.oks.append("README.pdf render proof current")


def check_adr_language(repo: Repo, md_files: list[str], r: Result) -> None:
    for rel in md_files:
        text = repo.read(rel)
        m = ADR_LANG_RE.search(text)
        if m:
            line = text.count("\n", 0, m.start()) + 1
            r.warns.append(
                f"{rel}:{line} '{m.group(0)}' frames the pre-ADR-0002 script shape "
                "as preferred — see docs/adr/0002"
            )


# ---------------------------------------------------------------------------
# load — read the policy data. returns (ctx, errors); never prints/exits.
# ---------------------------------------------------------------------------
def load(repo: Repo) -> tuple[Ctx | None, list[str]]:
    if not repo.is_file(INVENTORY_REL):
        return None, [f"{INVENTORY_REL} not found"]
    if not repo.is_file(COMMANDS_REL):
        return None, [f"{COMMANDS_REL} not found"]
    try:
        inventory = json.loads(repo.read(INVENTORY_REL))
        commands = json.loads(repo.read(COMMANDS_REL))
    except json.JSONDecodeError as e:
        return None, [f"policy data invalid JSON ({e})"]
    return Ctx(inventory=inventory, commands=commands), []


# ---------------------------------------------------------------------------
# evaluate — the compute interface. one call, one Result, over the injected
# Repo + tracked set + coverage probe. this is the test surface.
# ---------------------------------------------------------------------------
def evaluate(
    repo: Repo,
    ctx: Ctx,
    tracked: set[str],
    coverage_probe: Callable[[], tuple[bool, list[str]]],
) -> Result:
    md_files = sorted(t for t in tracked if t.endswith(".md"))
    r = Result()
    check_required(repo, ctx, r)
    check_tracked_paths(repo, md_files, tracked, r)
    check_stale_phrases(repo, md_files, r)
    check_commands(repo, ctx, md_files, tracked, r)
    check_coverage(ctx, coverage_probe, r)
    check_score_ledger(repo, ctx, r)
    check_render_proof(repo, r)
    check_adr_language(repo, md_files, r)
    r.oks.append(f"documents consulted: {len(md_files)} tracked *.md")
    return r


# ---------------------------------------------------------------------------
# environment readers — used only by main(). kept out of evaluate() so the
# compute path takes no git / .build dependency.
# ---------------------------------------------------------------------------
def git_tracked(repo_root: Path) -> set[str]:
    out = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return {line for line in out.splitlines() if line}


def real_coverage_probe() -> tuple[bool, list[str]]:
    """(measured?, drift). skip-if-absent: a fresh checkout without a coverage
    summary is not a failure, it just means the figure was not re-checked."""
    sys.path.insert(0, str(REPO_ROOT / "tools" / "badges"))
    import sync_coverage

    if not sync_coverage.SUMMARY_PATH.is_file():
        return False, []
    return True, sync_coverage.check(sync_coverage.measured_pct())


# ---------------------------------------------------------------------------
# main — the side-effecting adapter.
# ---------------------------------------------------------------------------
def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    ctx, errors = load(repo)
    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        return 1

    tracked = git_tracked(repo_root)
    r = evaluate(repo, ctx, tracked, real_coverage_probe)

    print("DOC FRESHNESS")
    for line in r.oks:
        print(f"OK {line}")
    for line in r.warns:
        print(f"WARN {line}")
    for line in r.fails:
        print(f"ERROR {line}")

    if r.fails:
        print(f"RESULT: {len(r.fails)} error(s), {len(r.warns)} warning(s)")
        return 1
    print("RESULT: green" if not r.warns else f"RESULT: green, {len(r.warns)} warning(s)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
