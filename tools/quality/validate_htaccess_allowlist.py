#!/usr/bin/env python3
"""validate_htaccess_allowlist.py — simulate the .htaccess rewrite gate
in python and prove every public file passes the allow-list.

The validate_public_exposure.py gate proves manifest <-> disk <-> html
consistency. This script closes the third leg: manifest <-> .htaccess.
Parses the rewrite gate block from public/.htaccess, compiles every
RewriteRule pattern to a python regex, then evaluates each url under
public/ against the rules in source order, applying [f,l] (deny) and
[l] (allow) semantics. Any url that falls through to the final
fallback deny is a missing allow rule.

Exit 0 = every public file passes through an allow rule.
Exit 1 = at least one file would be denied by .htaccess.
"""

from __future__ import annotations

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
from paths import PUBLIC_DIR, TOOLS_DIR

HTACCESS = PUBLIC_DIR / ".htaccess"
MANIFEST_PATH = TOOLS_DIR / "config" / "public-exposure.json"

# the rewrite gate block sits between the BEGIN/END PUBLIC EXPOSURE
# markers emitted by tools/generate_htaccess.py. extract only the
# rules inside that range so the cache/header directives outside it
# do not confuse the parser.
GATE_OPEN = re.compile(r"#\s*BEGIN PUBLIC EXPOSURE")
GATE_CLOSE = re.compile(r"#\s*END PUBLIC EXPOSURE")

# matches " RewriteRule <pattern> <substitution> [<flags>]" with
# leading whitespace tolerated. captures pattern + flags. the
# substitution is always "-" in this gate (we never rewrite the url,
# only allow or deny). flags are required because we depend on [f,l]
# vs [l] to distinguish deny from allow.
RULE_RE = re.compile(
    r"""^\s*RewriteRule\s+(\S+)\s+-\s+\[([A-Z,]+)\]\s*$""",
    re.MULTILINE,
)


def load_gate() -> str:
    text = HTACCESS.read_text(encoding="utf-8")
    open_m = GATE_OPEN.search(text)
    close_m = GATE_CLOSE.search(text)
    if not open_m or not close_m:
        print("FAIL: could not locate the rewrite gate block in .htaccess")
        sys.exit(1)
    return text[open_m.end() : close_m.start()]


def parse_rules(gate_text: str) -> list[tuple[re.Pattern, str]]:
    rules: list[tuple[re.Pattern, str]] = []
    for m in RULE_RE.finditer(gate_text):
        pat_raw = m.group(1)
        flags = m.group(2)
        # skip rules nested behind comments (line starts with #).
        line_start = gate_text.rfind("\n", 0, m.start()) + 1
        if gate_text[line_start : m.start()].lstrip().startswith("#"):
            continue
        try:
            pat = re.compile(pat_raw)
        except re.error as e:
            print(f"FAIL: invalid regex in .htaccess: {pat_raw!r} ({e})")
            sys.exit(1)
        rules.append((pat, flags))
    return rules


def evaluate(url: str, rules: list[tuple[re.Pattern, str]]) -> str:
    # mod_rewrite in .htaccess context drops the leading slash from
    # the request URI before matching against RewriteRule patterns.
    rel = url.lstrip("/")
    for pat, flags in rules:
        if pat.search(rel):
            if "F" in flags.split(","):
                return "deny"
            if "L" in flags.split(","):
                return "allow"
    return "fallthrough"


def walk_public_urls(deploy_excluded: list[str]) -> list[str]:
    # mirror validate_public_exposure.py walking semantics.
    deploy_re = [re.compile(_glob_to_regex(g)) for g in deploy_excluded]
    urls: list[str] = []
    for fp in sorted(PUBLIC_DIR.rglob("*")):
        if not fp.is_file():
            continue
        rel = fp.relative_to(PUBLIC_DIR).as_posix()
        if rel == ".htaccess":
            continue
        url = "/" + rel
        if any(p.match(url) for p in deploy_re):
            continue
        urls.append(url)
    # also include the directory-form url for any index.html, so we
    # test that mod_dir's subrequest resolution would succeed.
    dir_urls: list[str] = []
    for u in urls:
        if u.endswith("/index.html"):
            dir_urls.append(u[: -len("index.html")])
    return urls + dir_urls


def _glob_to_regex(pattern: str) -> str:
    out: list[str] = []
    i = 0
    n = len(pattern)
    while i < n:
        c = pattern[i]
        if c == "*":
            if i + 1 < n and pattern[i + 1] == "*":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
            i += 1
            continue
        if c == "?":
            out.append("[^/]")
            i += 1
            continue
        if c in r".+()[]{}|^$\\":
            out.append("\\" + c)
            i += 1
            continue
        out.append(c)
        i += 1
    return "^" + "".join(out) + "$"


def load_deploy_excluded() -> list[str]:
    import json

    if not MANIFEST_PATH.is_file():
        return []
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return list(data.get("deploy_excluded_globs", []))


def main() -> int:
    gate = load_gate()
    rules = parse_rules(gate)
    if not rules:
        print("FAIL: no RewriteRule directives parsed from the gate block")
        return 1
    print(f"  parsed {len(rules)} RewriteRule directives from .htaccess")

    deploy_excluded = load_deploy_excluded()
    urls = walk_public_urls(deploy_excluded)

    denied: list[str] = []
    fallthrough: list[str] = []
    allowed = 0
    for url in urls:
        verdict = evaluate(url, rules)
        if verdict == "allow":
            allowed += 1
        elif verdict == "deny":
            denied.append(url)
        else:
            fallthrough.append(url)

    if denied:
        print(f"FAIL: {len(denied)} public file(s) are explicitly denied by the gate:")
        for u in denied[:50]:
            print(f"  DENIED: {u}")
        if len(denied) > 50:
            print(f"  ... and {len(denied) - 50} more")
        return 1

    if fallthrough:
        print(f"FAIL: {len(fallthrough)} public file(s) fall through to the final deny:")
        for u in fallthrough[:50]:
            print(f"  FALLTHROUGH: {u}")
        if len(fallthrough) > 50:
            print(f"  ... and {len(fallthrough) - 50} more")
        return 1

    print(f"OK: every public url passes through an allow rule ({allowed} urls)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
