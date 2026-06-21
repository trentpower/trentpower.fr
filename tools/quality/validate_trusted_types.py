#!/usr/bin/env python3
"""tools/validate_trusted_types.py — Trusted Types build gate.

The site enforces `require-trusted-types-for 'script'` in the CSP. Any
runtime sink that produces a TrustedHTML or TrustedScriptURL (via
innerHTML/outerHTML/insertAdjacentHTML, script.src,
serviceWorker.register, dynamic import, etc.) must route through a
declared policy.

This validator scans every shipped JS file under public/ and the
runtime templates/, looking for unsafe sinks that aren't wrapped.
The acceptable patterns are:

  • `setTrustedHTML(el, value)`               — wraps innerHTML via policy
  • `el.innerHTML = ttPolicy.createHTML(...)` — direct policy use
  • `trustedScriptURL(value)`                 — wraps script-URL sinks
  • `*.register(trustedScriptURL(...))`       — SW register

Any other use of the listed sinks is flagged as a regression.

Exit 0 = clean; exit 1 = block.

Registered in tools/lib/checks.py (blocking tier); kept as a
standalone script so audit_trusted_types.py can run it ad-hoc.

Shape (deep module, small interface). The filesystem is the one injected seam —
`Repo(root)` — so the scan runs over a fixture repo with no monkeypatching.
`evaluate(repo)` is the pure compute path returning a Result; `main()` is the
only adapter that prints/exits. Byte-identical to the former inline scan over
the PUBLIC_DIR / TEMPLATES_DIR globals.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

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
from paths import REPO_ROOT  # noqa: E402
from repo import Repo  # noqa: E402  (shared filesystem evidence seam)

# files in scope — repo-root-relative posix paths resolved through the seam.
SCAN_FILES = [
    "public/js/theme.js",
    "public/sw-register.js",
    "public/js/reveal.js",
    "public/js/verify-modal.js",
    "public/js/copy.js",
    "public/js/fonts.js",
    "public/js/overlay.js",
    "public/sw.js",
    "public/verify/verify.js",
    "templates/theme.template.js",
    "templates/sw-register.template.js",
    "templates/reveal.template.js",
    "templates/verify-modal.template.js",
    "templates/copy.template.js",
    "templates/fonts.template.js",
    "templates/overlay.template.js",
]

# sink patterns. each matches an unsafe assignment; allowlists below
# cover lines that are demonstrably safe (wrapped in policy / inside
# a comment block).
SINK_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("innerHTML assignment", re.compile(r"\.innerHTML\s*=\s*(?!ttPolicy\.|policy\.)")),
    ("outerHTML assignment", re.compile(r"\.outerHTML\s*=\s*(?!ttPolicy\.|policy\.)")),
    ("insertAdjacentHTML call", re.compile(r"\.insertAdjacentHTML\s*\(")),
    (
        "script.src assignment",
        re.compile(r"\bscript\.src\s*=\s*(?!trustedScriptURL\(|ttPolicy\.createScriptURL\()"),
    ),
    ("dynamic createElement('script')", re.compile(r"createElement\(\s*['\"]script['\"]")),
    ("createContextualFragment", re.compile(r"\.createContextualFragment\s*\(")),
    ("eval", re.compile(r"\beval\s*\(")),
    (
        "setTimeout/setInterval string form",
        re.compile(r"\b(?:setTimeout|setInterval)\s*\(\s*['\"`]"),
    ),
    ("new Function", re.compile(r"new\s+Function\s*\(")),
    ("dynamic import", re.compile(r"(?<![A-Za-z_])import\s*\(")),
    ("new Worker(string)", re.compile(r"new\s+Worker\s*\(\s*['\"`]")),
    (
        "serviceWorker.register without policy",
        re.compile(r"\.register\s*\(\s*(?!trustedScriptURL\()['\"`]"),
    ),
]

# lines whose match is either a policy declaration (creating the
# policy itself), a wrapper-function definition, a comment, or a
# string literal explaining the sink. the validator skips these.
ALLOWLIST_SUBSTRINGS = (
    # lines that are part of the policy code itself.
    "createPolicy",
    "createHTML: function",
    "createScriptURL: _safeScriptURL",
    "setTrustedHTML",
    "trustedScriptURL",
    "ttPolicy.createHTML",
    "ttPolicy.createScriptURL",
    "// ",
    "* ",
    "*  ",  # in-comment matches
    "  // ",
    "   * ",
)

# regex-anchored allowlist, line by line: phrases that look like sinks
# but are documentation (e.g. comment text "use innerhtml") and the
# exact wrapped forms used in sw-register.template.js.
ALLOWLIST_LINE_RE = re.compile(
    r"(?:"
    r"^\s*//"  # whole-line comment
    r"|^\s*\*"  #   block-comment continuation
    r"|setTrustedHTML\("  # safe wrapper
    r"|trustedScriptURL\("  # safe wrapper
    r"|ttPolicy\s*\?"  # ternary fallback line
    r"|el\.innerHTML\s*=\s*ttPolicy"  # direct safe form
    r"|register\s*\(\s*trustedScriptURL\("  # safe sw register
    r")"
)

# the runtime-i18n era declared a `tp-i18n` trusted-types policy. that
# era is over: the single script-url policy is `tp-app`. these files
# must not reintroduce the retired name.
RETIRED_POLICY = "tp-i18n"
RETIRED_SCAN = SCAN_FILES + [
    "templates/source-view.template.js",
    "public/.htaccess",
]


@dataclass
class Result:
    # sink violations (file:line [label] — snippet) found in SCAN_FILES.
    fails: list[str] = field(default_factory=list)
    # files still referencing the retired `tp-i18n` policy name.
    stale: list[str] = field(default_factory=list)
    oks: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fails and not self.stale


def _scan_file(repo: Repo, rel: str) -> list[str]:
    if not repo.is_file(rel):
        return [f"FILE MISSING: {rel}"]
    text = repo.read(rel)
    fails: list[str] = []
    for line_num, line in enumerate(text.splitlines(), 1):
        # skip allowlisted lines wholesale.
        if ALLOWLIST_LINE_RE.search(line):
            continue
        # skip lines that mention policy / wrapper functions in any way.
        if any(s in line for s in ALLOWLIST_SUBSTRINGS):
            continue
        for label, pat in SINK_PATTERNS:
            if pat.search(line):
                fails.append(f"{rel}:{line_num} [{label}] — {line.strip()[:100]}")
                break  # one finding per line
    return fails


# ---------------------------------------------------------------------------
# evaluate — the compute interface. one call, one Result, over the injected
# Repo. this is the test surface; it never prints or exits.
# ---------------------------------------------------------------------------
def evaluate(repo: Repo) -> Result:
    r = Result()
    for rel in SCAN_FILES:
        r.fails.extend(_scan_file(repo, rel))

    if r.fails:
        return r

    # the retired `tp-i18n` policy name must be absent everywhere.
    r.stale = [
        rel for rel in RETIRED_SCAN if repo.is_file(rel) and RETIRED_POLICY in repo.read(rel)
    ]
    if r.stale:
        return r

    r.oks.append(
        f"OK: Trusted Types — {len(SCAN_FILES)} JS file(s) clean of unsafe "
        f"sinks; retired `{RETIRED_POLICY}` policy absent"
    )
    return r


# ---------------------------------------------------------------------------
# main — the side-effecting adapter. evaluates, renders the original stdout/
# stderr contract, returns the exit code. the only place output and exit live.
# ---------------------------------------------------------------------------
def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    r = evaluate(repo)

    if r.fails:
        fails = r.fails
        print(f"FAIL: {len(fails)} Trusted Types sink violation(s)", file=sys.stderr)
        for f in fails[:30]:
            print(f"  ✗ {f}", file=sys.stderr)
        if len(fails) > 30:
            print(f"  … and {len(fails) - 30} more", file=sys.stderr)
        print(file=sys.stderr)
        print("Wrap unsafe sinks via the tp-app policy:", file=sys.stderr)
        print("  script.src / register → trustedScriptURL(value)", file=sys.stderr)
        return 1

    if r.stale:
        print(
            f"FAIL: retired `{RETIRED_POLICY}` trusted-types policy still "
            f"referenced in {len(r.stale)} file(s):",
            file=sys.stderr,
        )
        for s in r.stale:
            print(f"  ✗ {s}", file=sys.stderr)
        return 1

    print(r.oks[0])
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
