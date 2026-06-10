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
"""

import re
import sys
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
from paths import PUBLIC_DIR, REPO_ROOT, TEMPLATES_DIR  # noqa: E402

# files in scope.
SCAN_FILES = [
    PUBLIC_DIR / "js" / "theme.js",
    PUBLIC_DIR / "sw-register.js",
    PUBLIC_DIR / "js" / "reveal.js",
    PUBLIC_DIR / "js" / "verify-modal.js",
    PUBLIC_DIR / "js" / "copy.js",
    PUBLIC_DIR / "js" / "fonts.js",
    PUBLIC_DIR / "js" / "overlay.js",
    PUBLIC_DIR / "sw.js",
    PUBLIC_DIR / "verify" / "verify.js",
    TEMPLATES_DIR / "theme.template.js",
    TEMPLATES_DIR / "sw-register.template.js",
    TEMPLATES_DIR / "reveal.template.js",
    TEMPLATES_DIR / "verify-modal.template.js",
    TEMPLATES_DIR / "copy.template.js",
    TEMPLATES_DIR / "fonts.template.js",
    TEMPLATES_DIR / "overlay.template.js",
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

# Regex-anchored allowlist, line by line: phrases that look like sinks
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


def _scan_file(p: Path) -> list[str]:
    if not p.is_file():
        return [f"FILE MISSING: {p.relative_to(REPO_ROOT)}"]
    text = p.read_text(encoding="utf-8")
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
                rel = p.relative_to(REPO_ROOT).as_posix()
                fails.append(f"{rel}:{line_num} [{label}] — {line.strip()[:100]}")
                break  # one finding per line
    return fails


# the runtime-i18n era declared a `tp-i18n` trusted-types policy. that
# era is over: the single script-url policy is `tp-app`. these files
# must not reintroduce the retired name.
RETIRED_POLICY = "tp-i18n"
RETIRED_SCAN = SCAN_FILES + [
    TEMPLATES_DIR / "source-view.template.js",
    PUBLIC_DIR / ".htaccess",
]


def main() -> int:
    fails: list[str] = []
    for p in SCAN_FILES:
        fails.extend(_scan_file(p))

    if fails:
        print(f"FAIL: {len(fails)} Trusted Types sink violation(s)", file=sys.stderr)
        for f in fails[:30]:
            print(f"  ✗ {f}", file=sys.stderr)
        if len(fails) > 30:
            print(f"  … and {len(fails) - 30} more", file=sys.stderr)
        print(file=sys.stderr)
        print("Wrap unsafe sinks via the tp-app policy:", file=sys.stderr)
        print("  script.src / register → trustedScriptURL(value)", file=sys.stderr)
        return 1

    # the retired `tp-i18n` policy name must be absent everywhere.
    stale = [
        p.relative_to(REPO_ROOT).as_posix()
        for p in RETIRED_SCAN
        if p.is_file() and RETIRED_POLICY in p.read_text(encoding="utf-8")
    ]
    if stale:
        print(
            f"FAIL: retired `{RETIRED_POLICY}` trusted-types policy still "
            f"referenced in {len(stale)} file(s):",
            file=sys.stderr,
        )
        for s in stale:
            print(f"  ✗ {s}", file=sys.stderr)
        return 1

    print(
        f"OK: Trusted Types — {len(SCAN_FILES)} JS file(s) clean of unsafe "
        f"sinks; retired `{RETIRED_POLICY}` policy absent"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
