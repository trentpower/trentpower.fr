#!/usr/bin/env python3
"""generate_htaccess.py — rewrite the generated regions of public/.htaccess.

Only the regions between BEGIN/END markers are touched. Everything
outside the markers is hand-authored and preserved byte-for-byte.

Markers managed:
  # BEGIN PUBLIC EXPOSURE ... # END PUBLIC EXPOSURE
      mod_rewrite deny + allow + final fallback. Source: htaccess_config.py
      Cross-checked against tools/public-exposure.json after the rewrite
      by validate_htaccess_allowlist.py.

  # BEGIN CSP ... # END CSP
      Global CSP header + /source/view/ CSP exception + sw.js CSP override.
      Source: htaccess_config.csp_global() / csp_source_view() / csp_service_worker().

Exits non-zero if either marker pair is missing, or if the rewrite
would leave the file syntactically suspect (an [F,L] before an [L]
inside the allow phase, etc.).
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys

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
import htaccess_config as cfg
from paths import PUBLIC_DIR

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
import routes as _routes  # noqa: E402

HTACCESS = PUBLIC_DIR / ".htaccess"

EXPOSURE_BEGIN = "# BEGIN PUBLIC EXPOSURE"
EXPOSURE_END = "# END PUBLIC EXPOSURE"
CSP_BEGIN = "# BEGIN CSP"
CSP_END = "# END CSP"


def _render_exposure_block(indent: str = "  ") -> str:
    """Compose the mod_rewrite gate body that lives between the markers.

    Layout (in source order; mod_rewrite evaluates top-down):
        phase 1: deny dangerous paths
        phase 2: deny dangerous extensions
        phase 3: deny build / source directories
        phase 3b: legacy single-tree URLs → 301 to their /en-au/ edition
        phase 3c: legacy dated asset URLs → 301 to their clean filename
        phase 4: allow rules, grouped by family
        phase 5: fallback deny — RewriteRule . - [F,L]
    """
    lines: list[str] = []
    lines.append(indent + "# phase 1 — deny dangerous paths")
    for pat in cfg.DENY_PATH_RULES:
        lines.append(f"{indent}RewriteRule {pat} - [F,L]")
    lines.append("")

    lines.append(indent + "# phase 2 — deny dangerous extensions")
    for pat in cfg.DENY_EXTENSION_RULES:
        lines.append(f"{indent}RewriteRule {pat} - [F,L]")
    lines.append("")

    lines.append(indent + "# phase 3 — deny build + source-tree directories")
    for pat in cfg.DENY_DIRECTORY_RULES:
        lines.append(f"{indent}RewriteRule {pat} - [F,L]")
    lines.append("")

    if cfg.LEGACY_REDIRECT_RULES:
        lines.append(
            indent + "# phase 3b — pre-cut-over single-tree URLs 301 to their /en/ edition"
        )
        for pat, target in cfg.LEGACY_REDIRECT_RULES:
            lines.append(f"{indent}RewriteRule {pat} {target} [R=301,L]")
        lines.append("")

    if cfg.LEGACY_VERSIONED_ASSET_REDIRECTS:
        lines.append(
            indent + "# phase 3c — legacy versioned-filename redirects · one-cycle transition for"
        )
        lines.append(indent + "# browsers caching HTML that still references the old dated URLs.")
        lines.append(indent + "# remove after the 2026-NN-NN edition once HTML caches turn over.")
        for pat, target in cfg.LEGACY_VERSIONED_ASSET_REDIRECTS:
            lines.append(f"{indent}RewriteRule {pat} {target} [R=301,L]")
        lines.append("")

    lines.append(indent + "# phase 4 — allow-list")
    for heading, rules in cfg.ALLOW_RULE_FAMILIES:
        lines.append(f"{indent}# {heading}")
        for pat in rules:
            lines.append(f"{indent}RewriteRule {pat} - [L]")
        lines.append("")

    lines.append(indent + "# phase 5 — fallback: anything unmatched returns 403")
    lines.append(f"{indent}RewriteRule . - [F,L]")
    return "\n".join(lines)


def _render_csp_block(indent: str = "  ") -> str:
    """Compose the CSP header block (global + source-view + sw.js)."""
    lines: list[str] = []
    lines.append(indent + "# global CSP — default-deny; inline script authorised by hash only.")
    lines.append(f'{indent}Header always set Content-Security-Policy "{cfg.csp_global()}"')
    lines.append("")

    lines.append(
        indent + "# source-reader exception — adds source reader inline hash + tp-source-view."
    )
    lines.append(indent + "# matches the neutral reader app and both bilingual reader pages.")
    lines.append(indent + "# SetEnvIf-based because LocationMatch is server-config-only.")
    _en_sv = _routes.route_path("source-view", "en").strip("/")
    _fr_sv = _routes.route_path("source-view", "fr").strip("/")
    lines.append(
        f'{indent}SetEnvIf Request_URI "^/({_en_sv}|{_fr_sv}|source/view)/" IS_SOURCE_VIEW=1'
    )
    lines.append(f"{indent}Header always unset Content-Security-Policy env=IS_SOURCE_VIEW")
    lines.append(
        f'{indent}Header always set Content-Security-Policy "{cfg.csp_source_view()}" env=IS_SOURCE_VIEW'
    )
    lines.append("")

    lines.append(indent + "# sw.js exception — workers need a narrower script-src 'self' only.")
    lines.append(indent + '<FilesMatch "^sw\\.js$">')
    lines.append(f"{indent}  Header always unset Content-Security-Policy")
    lines.append(
        f'{indent}  Header always set Content-Security-Policy "{cfg.csp_service_worker()}"'
    )
    lines.append(indent + "</FilesMatch>")
    return "\n".join(lines)


def _replace_marker_block(text: str, begin: str, end: str, body: str) -> str:
    """Replace everything between `begin` and `end` markers with `body`.

    Markers themselves are preserved. The line containing each marker
    is anchored to the start (modulo whitespace) of its line.
    """
    # the markers may sit at any indent inside an <IfModule> block, so
    # match the full line including its leading whitespace, then keep
    # that indent on the regenerated content.
    pat = re.compile(
        r"(?P<begin_indent>^[^\S\n]*)" + re.escape(begin) + r".*?\n"
        r"(?P<body>.*?)"
        r"^(?P<end_indent>[^\S\n]*)" + re.escape(end),
        re.DOTALL | re.MULTILINE,
    )
    m = pat.search(text)
    if not m:
        raise SystemExit(f"FAIL: could not locate marker pair {begin!r} ... {end!r} in .htaccess")
    begin_indent = m.group("begin_indent")
    end_indent = m.group("end_indent")
    replacement = f"{begin_indent}{begin}\n{body}\n{end_indent}{end}"
    return text[: m.start()] + replacement + text[m.end() :]


def _sanity_check(text: str) -> list[str]:
    """Lightweight pre-write sanity check. Fails fast on common mistakes."""
    issues: list[str] = []

    # 1. both marker pairs present and well-formed.
    for begin, end in [(EXPOSURE_BEGIN, EXPOSURE_END), (CSP_BEGIN, CSP_END)]:
        if text.count(begin) != 1 or text.count(end) != 1:
            issues.append(f"marker count != 1 for {begin!r}/{end!r}")

    # 2. the exposure block ends with a fallback deny.
    expo = re.search(
        re.escape(EXPOSURE_BEGIN) + r"(.*?)" + re.escape(EXPOSURE_END),
        text,
        re.DOTALL,
    )
    if expo and "RewriteRule . - [F,L]" not in expo.group(1):
        issues.append("exposure block missing fallback `RewriteRule . - [F,L]`")

    # 3. no allow-rule [l] appears AFTER the fallback [f,l].
    if expo:
        body = expo.group(1)
        fallback = body.rfind("RewriteRule . - [F,L]")
        if fallback != -1 and " [L]" in body[fallback:]:
            issues.append("an [L] rule sits after the fallback deny — unreachable")

    return issues


def _compose(disk_text: str) -> str:
    """Apply both marker rewrites to disk_text; return the in-memory result.
    Shared by the --write and --check paths."""
    text = _replace_marker_block(disk_text, EXPOSURE_BEGIN, EXPOSURE_END, _render_exposure_block())
    text = _replace_marker_block(text, CSP_BEGIN, CSP_END, _render_csp_block())
    return text


def _summary_line() -> str:
    n_allow = sum(len(rules) for _, rules in cfg.ALLOW_RULE_FAMILIES)
    n_deny = (
        len(cfg.DENY_PATH_RULES) + len(cfg.DENY_EXTENSION_RULES) + len(cfg.DENY_DIRECTORY_RULES)
    )
    return (
        f"{n_deny} deny rules, {n_allow} allow rules, "
        f"3 CSP headers (global + /source/view/ + sw.js)"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--write", action="store_true", help="rewrite the marker regions in place (default)"
    )
    mode.add_argument(
        "--check", action="store_true", help="exit non-zero if regeneration would change a byte"
    )
    args = parser.parse_args()
    # default is --write to preserve the historical no-arg contract
    # (tools/build.sh calls this script with no args).
    if not args.check:
        args.write = True

    if not HTACCESS.is_file():
        print(f"FAIL: {HTACCESS} not found", file=sys.stderr)
        return 1

    disk_bytes = HTACCESS.read_bytes()
    text = _compose(disk_bytes.decode("utf-8"))

    issues = _sanity_check(text)
    if issues:
        print("FAIL: refusing to act on .htaccess — sanity check failed:", file=sys.stderr)
        for i in issues:
            print(f"  - {i}", file=sys.stderr)
        return 1

    if args.check:
        if disk_bytes == text.encode("utf-8"):
            print("OK: .htaccess matches generator output")
            return 0
        diff = list(
            difflib.unified_diff(
                disk_bytes.decode("utf-8").splitlines(),
                text.splitlines(),
                fromfile=".htaccess (on disk)",
                tofile=".htaccess (would generate)",
                lineterm="",
            )
        )
        snippet = "\n  ".join(diff[:30])
        more = "" if len(diff) <= 30 else f"\n  ... ({len(diff) - 30} more diff lines)"
        print(
            f"FAIL: .htaccess drift — generator would change bytes\n  {snippet}{more}",
            file=sys.stderr,
        )
        return 1

    HTACCESS.write_text(text, encoding="utf-8")
    print(f"OK: .htaccess regenerated — {_summary_line()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
